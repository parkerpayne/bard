/**
 * The bot's HTTP surface, typed.
 *
 * Every call goes through `request()` for one reason: when the session cookie
 * expires the server answers 401, and the only useful response is to send the
 * browser to /login rather than let the UI quietly render empty data.
 */

export interface Track {
  id: number;
  youtube_id: string;
  title: string;
  duration_sec: number | null;
  thumbnail_url: string | null;
}

export interface PlaylistTrack extends Track {
  position: number;
}

export interface Playlist {
  id: number;
  name: string;
  cover_path: string | null;
  tags: string | null;
  track_count?: number;
}

export interface PlaylistDetail extends Playlist {
  tracks: PlaylistTrack[];
}

export interface Device {
  type: 'browser' | 'voice';
  label: string;
  /** "Guild · channel" — only voice devices carry it. */
  channel?: string;
  channel_id: number | null;
  members: number;
}

export interface ServerState {
  playing: boolean;
  paused: boolean;
  shuffled: boolean;
  volume: number;
  playlist_id: number | null;
  position_sec: number;
  device: 'browser' | 'voice';
  connected: boolean;
  voice_channel_id: number | null;
  current: Track | null;
  queue: Track[];
}

export interface Hotkey {
  playlist_id: number;
  /** An Electron accelerator, e.g. "Control+Alt+1". */
  accelerator: string;
  playlist_name?: string;
}

export type ApiResult<T = Record<string, unknown>> =
  | ({ ok: true } & T)
  | { ok: false; message: string };

export async function rawFetch(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(path, init);
  if (response.status === 401) {
    const next = encodeURIComponent(location.pathname + location.search);
    location.replace('/login?next=' + next);
  }
  return response;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<ApiResult<T>> {
  try {
    const init: RequestInit = { method };
    if (body !== undefined) {
      init.headers = { 'Content-Type': 'application/json' };
      init.body = JSON.stringify(body);
    }
    const response = await rawFetch(path, init);
    const data = await response.json().catch(() => ({}));
    if (response.ok) return { ok: true, ...(data as T) };
    return { ok: false, message: (data as { message?: string }).message || `HTTP ${response.status}` };
  } catch {
    return { ok: false, message: 'Network error' };
  }
}

/** GET that returns the parsed body, or null when anything at all goes wrong. */
async function getJson<T>(path: string): Promise<T | null> {
  try {
    const response = await rawFetch(path);
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export const api = {
  nowPlaying: () => getJson<ServerState>('/api/now-playing'),
  devices: () => getJson<{ devices: Device[] }>('/api/devices'),

  play: (playlistId: number, trackId: number | null, shuffled: boolean) =>
    request<{ track_count: number }>('POST', '/api/play', {
      playlist_id: playlistId,
      track_id: trackId,
      shuffled,
    }),
  pause: () => request('POST', '/api/pause', {}),
  resume: () => request('POST', '/api/resume', {}),
  stop: () => request('POST', '/api/stop', {}),
  skip: () => request('POST', '/api/skip', {}),
  previous: () => request('POST', '/api/previous', {}),
  shuffle: (shuffled: boolean) => request('POST', '/api/shuffle', { shuffled }),
  volume: (volume: number) => request('POST', '/api/volume', { volume }),
  setDevice: (device: 'browser' | 'voice', channelId: number | null) =>
    request('POST', '/api/device', { device, channel_id: channelId }),

  libraryTracks: () => getJson<Track[]>('/api/library/tracks'),
  importUrl: (url: string) =>
    request<{ track: Track; tracks: Track[]; imported: number; skipped: number }>(
      'POST',
      '/api/library/import',
      { url },
    ),
  deleteTrack: (trackId: number) => request('DELETE', `/api/library/tracks/${trackId}`),

  playlists: () => getJson<{ playlists: Playlist[] }>('/api/playlists'),
  playlist: (id: number) => getJson<PlaylistDetail>(`/api/playlists/${id}`),
  createPlaylist: (name: string, tags: string) =>
    request<{ playlist: Playlist }>('POST', '/api/playlists', { name, tags }),
  updatePlaylist: (id: number, name: string, tags: string) =>
    request<{ playlist: Playlist }>('PUT', `/api/playlists/${id}`, { name, tags }),
  deletePlaylist: (id: number) => request('DELETE', `/api/playlists/${id}`),
  addTracks: (id: number, trackIds: number[]) =>
    request<{ added: number }>('POST', `/api/playlists/${id}/tracks`, { track_ids: trackIds }),
  removeTrack: (id: number, trackId: number) =>
    request('DELETE', `/api/playlists/${id}/tracks/${trackId}`),

  async uploadCover(id: number, file: File): Promise<ApiResult<{ cover_path: string }>> {
    const form = new FormData();
    form.append('cover', file);
    try {
      const response = await rawFetch(`/api/playlists/${id}/cover`, { method: 'POST', body: form });
      const data = await response.json().catch(() => ({}));
      if (response.ok) return { ok: true, ...(data as { cover_path: string }) };
      return { ok: false, message: (data as { message?: string }).message || 'Could not upload cover' };
    } catch {
      return { ok: false, message: 'Upload failed' };
    }
  },

  hotkeys: () => getJson<{ hotkeys: Hotkey[] }>('/api/hotkeys'),
  setHotkey: (playlistId: number, accelerator: string) =>
    request<{ accelerator: string }>('PUT', `/api/hotkeys/${playlistId}`, { accelerator }),
  clearHotkey: (playlistId: number) => request('DELETE', `/api/hotkeys/${playlistId}`),
  /** Server-side play/pause toggle for one playlist — see the desktop app. */
  triggerHotkey: (playlistId: number) =>
    request<{ action: 'playing' | 'paused' | 'resumed' }>('POST', '/api/hotkeys/trigger', {
      playlist_id: playlistId,
    }),

  logout: () => request<{ redirect: string }>('POST', '/api/logout', {}),
};

export const audioUrl = (trackId: number) => `/api/audio/${trackId}`;
export const coverUrl = (playlist: Pick<Playlist, 'cover_path'>) =>
  playlist.cover_path ? `/covers/${encodeURIComponent(playlist.cover_path)}` : null;
