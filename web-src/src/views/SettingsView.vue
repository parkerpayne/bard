<script setup lang="ts">
/**
 * The device choice, spelled out. The player bar has the same switch in a
 * popover; this is where the difference between the two destinations gets
 * explained rather than implied.
 */
import { computed, onMounted, ref } from 'vue';
import Button from 'primevue/button';
import Message from 'primevue/message';
import { api, type Hotkey } from '@/lib/api';
import { notify } from '@/lib/notify';
import { player } from '@/lib/player';
import { isDesktop, rejected, syncHotkeys } from '@/lib/desktop';
import { playlists, refreshPlaylists } from '@/lib/store';
import HotkeyRecorder from '@/components/HotkeyRecorder.vue';

const { device, voiceConnected } = player;
const busy = ref<'browser' | 'voice' | null>(null);

const hotkeys = ref<Hotkey[]>([]);
const hotkeysLoaded = ref(false);
const savingFor = ref<number | null>(null);

onMounted(async () => {
  void player.fetchDevices();
  if (!playlists.value.length) void refreshPlaylists();
  await loadHotkeys();
});

async function loadHotkeys() {
  const data = await api.hotkeys();
  if (data) hotkeys.value = data.hotkeys;
  hotkeysLoaded.value = true;
}

const boundTo = (playlistId: number) =>
  hotkeys.value.find((h) => h.playlist_id === playlistId)?.accelerator ?? null;

async function bind(playlistId: number, accelerator: string) {
  savingFor.value = playlistId;
  const result = await api.setHotkey(playlistId, accelerator);
  savingFor.value = null;
  if (!result.ok) {
    notify.error('Could not set that shortcut', result.message);
    return;
  }
  await loadHotkeys();
  // The shell owns registration; tell it the set changed.
  await syncHotkeys();
  notify.success(`Shortcut set to ${accelerator}`);
}

async function unbind(playlistId: number) {
  savingFor.value = playlistId;
  const result = await api.clearHotkey(playlistId);
  savingFor.value = null;
  if (!result.ok) {
    notify.error('Could not clear that shortcut', result.message);
    return;
  }
  await loadHotkeys();
  await syncHotkeys();
}

const target = computed(() => player.autoVoiceTarget());

async function choose(type: 'browser' | 'voice') {
  busy.value = type;
  if (type === 'voice') await player.fetchDevices();
  await player.selectDevice(type);
  busy.value = null;
}

async function signOut() {
  await api.logout();
  location.replace('/login');
}
</script>

<template>
  <section>
    <h1 class="page-title">Settings</h1>
    <p class="page-sub">Where playback comes out, and who is signed in.</p>

    <div class="cards">
      <article class="card" :class="{ on: device === 'browser' }">
        <i class="pi pi-desktop" />
        <div class="body">
          <h2>Browser</h2>
          <p>Streams the audio into this tab. Seeking and scrubbing work here.</p>
        </div>
        <Button
          :label="device === 'browser' ? 'In use' : 'Use browser'"
          :disabled="device === 'browser'"
          :loading="busy === 'browser'"
          size="small"
          @click="choose('browser')"
        />
      </article>

      <article class="card" :class="{ on: device === 'voice' }">
        <i class="pi pi-discord" />
        <div class="body">
          <h2>Discord</h2>
          <p>{{ player.voiceMeta() }}</p>
          <p v-if="!target && device !== 'voice'" class="warn">
            The bot joins whichever voice channel has people in it, so someone has to be
            in one first.
          </p>
        </div>
        <Button
          :label="device === 'voice' ? 'In use' : 'Use Discord'"
          :disabled="device === 'voice'"
          :loading="busy === 'voice'"
          size="small"
          @click="choose('voice')"
        />
      </article>
    </div>

    <p class="status">
      <template v-if="device === 'voice'">
        Playing through the bot{{ voiceConnected ? '' : ' — not connected yet' }}.
      </template>
      <template v-else>Playing in this browser tab.</template>
    </p>

    <h2 class="section-head">Playlist shortcuts</h2>
    <p class="section-note">
      Global keyboard shortcuts that start a playlist — press once to play it, again to
      pause, again to resume. They fire anywhere on the machine, not just in this window.
    </p>

    <Message v-if="!isDesktop" severity="warn" :closable="false" class="notice">
      Shortcuts are registered by the desktop app. You can set them here in any browser,
      but they will only fire while the Bard desktop app is running.
    </Message>
    <Message v-else-if="rejected.length" severity="error" :closable="false" class="notice">
      The desktop app could not register {{ rejected.join(', ') }} — another application
      already holds {{ rejected.length === 1 ? 'it' : 'them' }}. Pick a different combination.
    </Message>

    <div v-if="playlists.length" class="binds">
      <div v-for="playlist in playlists" :key="playlist.id" class="bind">
        <span class="bind-name truncate">{{ playlist.name }}</span>
        <HotkeyRecorder
          :model-value="boundTo(playlist.id)"
          :disabled="savingFor === playlist.id"
          @save="bind(playlist.id, $event)"
          @clear="unbind(playlist.id)"
        />
      </div>
    </div>
    <p v-else-if="hotkeysLoaded" class="section-note">
      Create a playlist first — shortcuts are bound to playlists.
    </p>

    <h2 class="section-head">Session</h2>
    <Button label="Sign out" icon="pi pi-sign-out" severity="secondary" variant="outlined" size="small" @click="signOut" />
  </section>
</template>

<style scoped>
.cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 560px;
  margin-top: 22px;
}

.card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius-panel);
  background: rgba(255, 255, 255, 0.04);
}

.card.on {
  border-color: var(--accent);
}

.card > i {
  font-size: 20px;
  color: var(--fg-dim);
}

.card.on > i {
  color: var(--accent);
}

.body {
  flex: 1;
  min-width: 0;
}

.body h2 {
  font-size: 14px;
  font-weight: 650;
}

.body p {
  font-size: 12px;
  color: var(--fg-muted);
  margin-top: 3px;
}

.warn {
  color: var(--fg-dim) !important;
}

.status {
  font-size: 12px;
  color: var(--fg-muted);
  margin-top: 14px;
}

.section-note {
  font-size: 12px;
  color: var(--fg-muted);
  max-width: 560px;
  margin-bottom: 12px;
}

.notice {
  max-width: 560px;
  margin-bottom: 14px;
}

.binds {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 560px;
}

.bind {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-card);
  background: rgba(255, 255, 255, 0.04);
}

.bind-name {
  font-size: 13px;
  font-weight: 640;
}

.section-head {
  font-size: 14px;
  font-weight: 700;
  padding-bottom: 8px;
  margin: 28px 0 12px;
  border-bottom: 1px solid var(--line);
  max-width: 560px;
}

@media (max-width: 760px) {
  .card {
    flex-wrap: wrap;
  }
}
</style>
