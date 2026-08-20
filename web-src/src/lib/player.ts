/**
 * Playback engine.
 *
 * Two independent players exist: this browser tab, and the bot sitting in a
 * Discord voice channel. `device` says which one the user is driving, and each
 * owns its own queue — the poll below must never overwrite the browser's queue
 * with the bot's, or local playback stops dead after the first track.
 */
import { computed, reactive, ref } from 'vue';
import { api, audioUrl, type Device, type ServerState, type Track } from './api';
import { notify } from './notify';
import { shuffleInPlace, store } from './format';

const LS = { device: 'bard.device', shuffle: 'bard.shuffle', volume: 'bard.volume' };
const POLL_MS = 3000;
const VOICE_TICK_MS = 250;

const IDLE_SERVER: ServerState = {
  playing: false,
  paused: false,
  shuffled: false,
  volume: 0.5,
  playlist_id: null,
  position_sec: 0,
  device: 'browser',
  connected: false,
  voice_channel_id: null,
  current: null,
  queue: [],
};

const audio = new Audio();
audio.preload = 'none';

const device = ref<'browser' | 'voice'>(store.get(LS.device) === 'voice' ? 'voice' : 'browser');
const shuffled = ref(store.get(LS.shuffle) === '1');
const savedVolume = Number.parseFloat(store.get(LS.volume) ?? '');
const volume = ref(Number.isNaN(savedVolume) ? 1 : savedVolume);
audio.volume = volume.value;

const server = ref<ServerState>({ ...IDLE_SERVER });
const devices = ref<Device[]>([]);

/** The tab's own queue. `order` indexes into `tracks`; `pos` walks `order`. */
const local = reactive({
  tracks: [] as Track[],
  order: [] as number[],
  pos: 0,
  playlistId: null as number | null,
});

const audioPaused = ref(true);
const browserPosition = ref(0);
const browserDuration = ref(0);
const voicePosition = ref(0);

function localCurrent(): Track | null {
  if (!local.order.length) return null;
  const index = local.order[local.pos % local.order.length];
  return local.tracks[index] ?? null;
}

const current = computed<Track | null>(() =>
  device.value === 'voice' ? server.value.current : localCurrent(),
);

const queue = computed<Track[]>(() =>
  device.value === 'voice'
    ? server.value.queue ?? []
    : local.order.map((i) => local.tracks[i]).filter(Boolean),
);

const playlistId = computed<number | null>(() =>
  device.value === 'voice' ? server.value.playlist_id : local.playlistId,
);

const isPlaying = computed<boolean>(() =>
  device.value === 'voice'
    ? server.value.playing && !server.value.paused
    : !!current.value && !audioPaused.value,
);

const position = computed<number>(() =>
  device.value === 'voice' ? voicePosition.value : browserPosition.value,
);

const duration = computed<number>(() => {
  if (device.value === 'voice') return current.value?.duration_sec ?? 0;
  return browserDuration.value || current.value?.duration_sec || 0;
});

/** Voice playback cannot be seeked or scrubbed — the bot streams, it does not serve. */
const canSeek = computed<boolean>(() => device.value === 'browser' && browserDuration.value > 0);

const voiceConnected = computed<boolean>(() => server.value.connected);

// ── Local queue ───────────────────────────────────────────────────────────

function localSetQueue(tracks: Track[], forPlaylist: number | null, startTrackId?: number | null) {
  local.tracks = tracks.slice();
  local.playlistId = forPlaylist;
  local.order = tracks.map((_, i) => i);
  if (shuffled.value) shuffleInPlace(local.order);
  local.pos = 0;
  if (startTrackId != null) {
    const queueIndex = tracks.findIndex((t) => t.id === startTrackId);
    const orderPos = local.order.indexOf(queueIndex);
    if (orderPos > 0) {
      // Rotate so the clicked track plays first and the rest follow in the
      // order already decided (shuffled or sequential).
      local.order = local.order.slice(orderPos).concat(local.order.slice(0, orderPos));
    }
  }
}

function localStep(delta: number): Track | null {
  if (!local.order.length) return null;
  local.pos += delta;
  if (local.pos >= local.order.length) {
    local.pos = 0;
    if (shuffled.value) shuffleInPlace(local.order); // fresh order each pass
  } else if (local.pos < 0) {
    local.pos = local.order.length - 1;
  }
  return localCurrent();
}

function loadBrowserTrack(track: Track | null) {
  if (!track) return;
  audio.src = audioUrl(track.id);
  audio.load();
  void audio.play().catch(() => {});
  setMediaSession(track);
}

function setMediaSession(track: Track) {
  if (!('mediaSession' in navigator)) return;
  navigator.mediaSession.metadata = new MediaMetadata({
    title: track.title,
    artwork: track.thumbnail_url ? [{ src: track.thumbnail_url }] : [],
  });
  navigator.mediaSession.setActionHandler('play', () => {
    void audio.play();
  });
  navigator.mediaSession.setActionHandler('pause', () => audio.pause());
  navigator.mediaSession.setActionHandler('nexttrack', () => void next());
  navigator.mediaSession.setActionHandler('previoustrack', () => void previous());
}

audio.addEventListener('timeupdate', () => {
  browserPosition.value = audio.currentTime || 0;
  if (Number.isFinite(audio.duration)) browserDuration.value = audio.duration;
});
audio.addEventListener('durationchange', () => {
  browserDuration.value = Number.isFinite(audio.duration) ? audio.duration : 0;
});
audio.addEventListener('play', () => {
  audioPaused.value = false;
});
audio.addEventListener('pause', () => {
  audioPaused.value = true;
});
audio.addEventListener('ended', () => {
  if (device.value === 'browser') void next();
});
audio.addEventListener('error', () => {
  const track = localCurrent();
  if (device.value !== 'browser' || !track) return;
  notify.error('Playback failed', `Could not play "${track.title}" — skipping`);
  setTimeout(() => void next(), 400);
});

// ── Voice position interpolation ──────────────────────────────────────────
// Voice has no client-side clock, so interpolate between polls.

let voiceTimer: number | null = null;
const voiceRef = { position: 0, at: 0, duration: 0 };

function startVoiceInterpolation(from: number, trackDuration: number) {
  voiceRef.position = from;
  voiceRef.at = Date.now();
  voiceRef.duration = trackDuration || 0;
  voicePosition.value = from;
  if (voiceTimer !== null) return;
  voiceTimer = window.setInterval(() => {
    const elapsed = (Date.now() - voiceRef.at) / 1000;
    const next = voiceRef.position + elapsed;
    voicePosition.value = voiceRef.duration ? Math.min(next, voiceRef.duration) : next;
  }, VOICE_TICK_MS);
}

function stopVoiceInterpolation() {
  if (voiceTimer !== null) {
    window.clearInterval(voiceTimer);
    voiceTimer = null;
  }
}

// ── Polling ───────────────────────────────────────────────────────────────

async function poll(): Promise<void> {
  const state = await api.nowPlaying();
  if (!state) return;
  server.value = state;

  // Someone started playback from Discord (/music play) while this tab was
  // idle — follow along instead of showing a stale "nothing playing".
  if (state.device === 'voice' && device.value === 'browser' && audio.paused && !localCurrent()) {
    setDevice('voice');
  }
  // The bot dropped out of voice (left, or was stopped) — fall back to this tab.
  if (device.value === 'voice' && !state.connected) {
    setDevice('browser');
  }
  if (device.value === 'voice') {
    shuffled.value = !!state.shuffled;
    if (state.playing && !state.paused && state.current) {
      startVoiceInterpolation(state.position_sec || 0, state.current.duration_sec || 0);
    } else {
      stopVoiceInterpolation();
      voicePosition.value = state.position_sec || 0;
    }
  } else {
    stopVoiceInterpolation();
  }
}

function setDevice(next: 'browser' | 'voice') {
  device.value = next;
  store.set(LS.device, next);
}

// ── Controls ──────────────────────────────────────────────────────────────

async function next(): Promise<void> {
  if (device.value === 'browser') {
    loadBrowserTrack(localStep(1));
  } else {
    await api.skip();
    await poll();
  }
}

async function previous(): Promise<void> {
  if (device.value === 'browser') {
    if (audio.currentTime > 3) {
      audio.currentTime = 0;
      return;
    }
    loadBrowserTrack(localStep(-1));
  } else {
    await api.previous();
    await poll();
  }
}

async function togglePlay(): Promise<void> {
  if (device.value === 'browser') {
    if (!localCurrent()) return;
    if (audio.paused) void audio.play().catch(() => {});
    else audio.pause();
  } else {
    if (isPlaying.value) await api.pause();
    else await api.resume();
    await poll();
  }
}

async function stop(): Promise<void> {
  if (device.value === 'browser') {
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    local.tracks = [];
    local.order = [];
    local.pos = 0;
    local.playlistId = null;
    browserPosition.value = 0;
    browserDuration.value = 0;
  } else {
    await api.stop();
    await poll();
  }
}

async function setShuffled(value: boolean): Promise<void> {
  shuffled.value = value;
  store.set(LS.shuffle, value ? '1' : '0');
  if (device.value === 'browser') {
    // Keep playing what is playing, reshuffle everything around it.
    const track = localCurrent();
    localSetQueue(local.tracks, local.playlistId, track ? track.id : null);
  } else {
    await api.shuffle(value);
    await poll();
  }
  notify.info(value ? 'Shuffle on' : 'Shuffle off');
}

function seekTo(seconds: number): void {
  if (device.value !== 'browser' || !browserDuration.value) return;
  audio.currentTime = Math.max(0, Math.min(seconds, browserDuration.value));
  browserPosition.value = audio.currentTime;
}

let volumeTimer: number | null = null;
function setVolume(value: number): void {
  const clamped = Math.max(0, Math.min(1, value));
  volume.value = clamped;
  audio.volume = clamped;
  store.set(LS.volume, String(clamped));
  if (device.value === 'voice') {
    // Debounced: the bot re-mixes the stream on every change.
    if (volumeTimer !== null) window.clearTimeout(volumeTimer);
    volumeTimer = window.setTimeout(() => void api.volume(clamped), 200);
  }
}

// ── Devices ───────────────────────────────────────────────────────────────

async function fetchDevices(): Promise<void> {
  const data = await api.devices();
  if (data) devices.value = data.devices ?? [];
}

/**
 * Which channel the bot would join: the busiest one with people in it. This
 * mirrors the server's own auto-detect, so the hint matches what happens.
 */
function autoVoiceTarget(): Device | null {
  const occupied = devices.value.filter((d) => d.type === 'voice' && d.members > 0);
  if (!occupied.length) return null;
  return occupied.reduce((best, d) => (d.members > best.members ? d : best));
}

function voiceMeta(): string {
  if (device.value === 'voice') {
    const channel = devices.value.find((d) => d.channel_id === server.value.voice_channel_id);
    return channel ? `Playing in ${channel.channel || channel.label}` : 'Playing in voice';
  }
  const target = autoVoiceTarget();
  if (target) return `Joins ${target.channel || target.label} · ${target.members} in call`;
  return 'Nobody is in a voice channel yet';
}

async function selectDevice(type: 'browser' | 'voice'): Promise<boolean> {
  if (type === 'browser') {
    await api.setDevice('browser', null);
    setDevice('browser');
    notify.info('Playing in this browser');
    return true;
  }
  const result = await api.setDevice('voice', null);
  if (!result.ok) {
    notify.error('Could not switch device', result.message);
    return false;
  }
  audio.pause();
  audio.removeAttribute('src');
  audio.load();
  setDevice('voice');
  await api.shuffle(shuffled.value);
  await poll();
  notify.success('Playing in Discord voice');
  return true;
}

// ── Starting playback ─────────────────────────────────────────────────────

function playTracks(tracks: Track[], forPlaylist: number | null, startTrackId?: number | null) {
  if (!tracks.length) return;
  setDevice('browser');
  localSetQueue(tracks, forPlaylist, startTrackId ?? null);
  loadBrowserTrack(localCurrent());
}

async function playPlaylist(
  id: number,
  startTrackId: number | null = null,
  shuffle?: boolean,
): Promise<void> {
  if (shuffle !== undefined && shuffle !== shuffled.value) {
    shuffled.value = shuffle;
    store.set(LS.shuffle, shuffle ? '1' : '0');
  }

  if (device.value === 'voice') {
    const result = await api.play(id, startTrackId, shuffled.value);
    if (!result.ok) {
      notify.error('Could not start playback', result.message);
      return;
    }
    await poll();
    return;
  }

  const detail = await api.playlist(id);
  if (!detail) {
    notify.error('Could not load playlist');
    return;
  }
  if (!detail.tracks.length) {
    notify.error('That playlist is empty');
    return;
  }
  playTracks(detail.tracks, id, startTrackId);
}

/** The bot plays playlists, not the raw library, so voice cannot preview one. */
function playLibrary(tracks: Track[], startTrackId: number): void {
  if (device.value !== 'browser') {
    notify.info('Switch to Browser to preview library tracks');
    return;
  }
  playTracks(tracks, null, startTrackId);
}

let pollTimer: number | null = null;

function init(): void {
  void fetchDevices();
  void poll();
  if (pollTimer === null) pollTimer = window.setInterval(() => void poll(), POLL_MS);
}

export const player = {
  // state
  device,
  devices,
  shuffled,
  volume,
  current,
  queue,
  playlistId,
  isPlaying,
  position,
  duration,
  canSeek,
  voiceConnected,
  serverState: server,
  // actions
  init,
  poll,
  fetchDevices,
  next,
  previous,
  togglePlay,
  stop,
  setShuffled,
  seekTo,
  setVolume,
  selectDevice,
  autoVoiceTarget,
  voiceMeta,
  playPlaylist,
  playTracks,
  playLibrary,
};
