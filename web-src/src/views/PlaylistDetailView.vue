<script setup lang="ts">
/**
 * One playlist: its cover and name, its tracks, and the library picker for
 * adding more. Every mutation re-fetches the playlist rather than patching the
 * local copy — positions are the server's business, and a wrong local guess
 * shows up as tracks in the wrong order.
 */
import { computed, ref, watch } from 'vue';
import Button from 'primevue/button';
import IconField from 'primevue/iconfield';
import InputIcon from 'primevue/inputicon';
import InputText from 'primevue/inputtext';
import { useConfirm } from 'primevue/useconfirm';
import { api, coverUrl, type PlaylistDetail, type Track } from '@/lib/api';
import { notify } from '@/lib/notify';
import { player } from '@/lib/player';
import { showTab } from '@/lib/router';
import { parseTags, pluralize } from '@/lib/format';
import { libraryTracks, refreshLibrary, refreshPlaylists } from '@/lib/store';
import CoverArt from '@/components/CoverArt.vue';
import IconShuffle from '@/components/IconShuffle.vue';
import TrackRow from '@/components/TrackRow.vue';

const props = defineProps<{ id: number }>();

const confirm = useConfirm();
const { current } = player;

const playlist = ref<PlaylistDetail | null>(null);
const loading = ref(true);
const missing = ref(false);

const editing = ref(false);
const editName = ref('');
const editTags = ref('');

const adding = ref(false);
const addSearch = ref('');
const pendingAdd = ref<number | null>(null);

const coverInput = ref<HTMLInputElement | null>(null);
const uploading = ref(false);

async function load() {
  loading.value = true;
  const [detail] = await Promise.all([api.playlist(props.id), refreshLibrary()]);
  loading.value = false;
  if (!detail) {
    missing.value = true;
    playlist.value = null;
    return;
  }
  missing.value = false;
  playlist.value = detail;
  editName.value = detail.name;
  editTags.value = detail.tags ?? '';
}

watch(() => props.id, load, { immediate: true });

const tags = computed(() => parseTags(playlist.value?.tags));
const tracks = computed<Track[]>(() => playlist.value?.tracks ?? []);

/** The library minus what is already here — the only thing worth offering. */
const addable = computed(() => {
  const present = new Set(tracks.value.map((t) => t.id));
  const query = addSearch.value.trim().toLowerCase();
  return libraryTracks.value.filter(
    (track) =>
      !present.has(track.id) && (!query || track.title.toLowerCase().includes(query)),
  );
});

function play(startTrackId: number | null, shuffle: boolean) {
  void player.playPlaylist(props.id, startTrackId, shuffle);
}

function toggleEdit() {
  editing.value = !editing.value;
  if (editing.value && playlist.value) {
    editName.value = playlist.value.name;
    editTags.value = playlist.value.tags ?? '';
  }
}

async function save() {
  const name = editName.value.trim();
  if (!name) return;
  const result = await api.updatePlaylist(props.id, name, editTags.value.trim());
  if (!result.ok) {
    notify.error('Could not save', result.message);
    return;
  }
  editing.value = false;
  await Promise.all([load(), refreshPlaylists()]);
  notify.success('Saved');
}

function remove() {
  const name = playlist.value?.name ?? 'this playlist';
  confirm.require({
    header: 'Delete playlist?',
    message: `"${name}" will be gone for good. The tracks stay in your library.`,
    acceptLabel: 'Delete',
    rejectLabel: 'Cancel',
    acceptProps: { severity: 'danger' },
    rejectProps: { severity: 'secondary', variant: 'text' },
    accept: async () => {
      const result = await api.deletePlaylist(props.id);
      if (!result.ok) {
        notify.error('Could not delete', result.message);
        return;
      }
      await refreshPlaylists();
      notify.success('Playlist deleted');
      showTab('playlists');
    },
  });
}

async function removeTrack(track: Track) {
  const result = await api.removeTrack(props.id, track.id);
  if (!result.ok) {
    notify.error('Could not remove', result.message);
    return;
  }
  await Promise.all([load(), refreshPlaylists()]);
}

async function addTrack(track: Track) {
  pendingAdd.value = track.id;
  const result = await api.addTracks(props.id, [track.id]);
  pendingAdd.value = null;
  if (!result.ok) {
    notify.error('Could not add', result.message);
    return;
  }
  await Promise.all([load(), refreshPlaylists()]);
}

async function uploadCover(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  uploading.value = true;
  const result = await api.uploadCover(props.id, file);
  uploading.value = false;
  // Clear it, or picking the same file twice fires no change event.
  if (coverInput.value) coverInput.value.value = '';
  if (!result.ok) {
    notify.error('Could not upload cover', result.message);
    return;
  }
  await Promise.all([load(), refreshPlaylists()]);
}
</script>

<template>
  <section>
    <Button
      icon="pi pi-arrow-left"
      label="Playlists"
      severity="secondary"
      variant="text"
      size="small"
      class="back"
      @click="showTab('playlists')"
    />

    <p v-if="loading && !playlist" class="status">Loading…</p>
    <p v-else-if="missing" class="status">That playlist is gone.</p>

    <template v-else-if="playlist">
      <header class="hero">
        <div class="cover">
          <CoverArt :src="coverUrl(playlist)" :seed="playlist.name" size="var(--art)" :glyph="46" />
          <button class="recover" :disabled="uploading" @click="coverInput?.click()">
            <i :class="uploading ? 'pi pi-spin pi-spinner' : 'pi pi-image'" />
            {{ uploading ? 'Uploading…' : 'Change cover' }}
          </button>
          <input
            ref="coverInput"
            type="file"
            accept="image/*"
            hidden
            @change="uploadCover"
          />
        </div>

        <div class="about">
          <span class="section-label">Playlist</span>
          <h1 class="name">{{ playlist.name }}</h1>
          <div v-if="tags.length" class="tags">
            <span v-for="tag in tags" :key="tag">{{ tag }}</span>
          </div>
          <p class="count">{{ pluralize(tracks.length, 'track') }}</p>

          <div class="actions">
            <Button :disabled="!tracks.length" @click="play(null, true)">
              <IconShuffle :size="14" />
              <span>Shuffle play</span>
            </Button>
            <Button
              label="Play in order"
              severity="secondary"
              variant="outlined"
              size="small"
              :disabled="!tracks.length"
              @click="play(null, false)"
            />
            <Button
              :label="editing ? 'Close' : 'Edit'"
              icon="pi pi-pencil"
              severity="secondary"
              variant="text"
              size="small"
              @click="toggleEdit"
            />
            <Button
              label="Delete"
              icon="pi pi-trash"
              severity="danger"
              variant="text"
              size="small"
              @click="remove"
            />
          </div>
        </div>
      </header>

      <div v-if="editing" class="edit">
        <InputText v-model="editName" placeholder="Playlist name" autofocus @keydown.enter="save" />
        <InputText v-model="editTags" placeholder="Tags (e.g. epic battle ambient)" @keydown.enter="save" />
        <Button label="Save" size="small" :disabled="!editName.trim()" @click="save" />
      </div>

      <h2 class="section-head">Tracks</h2>
      <div v-if="tracks.length" class="list">
        <TrackRow
          v-for="(track, i) in tracks"
          :key="track.id"
          :track="track"
          :index="i + 1"
          :playing="current?.id === track.id"
          @activate="play(track.id, false)"
        >
          <Button
            icon="pi pi-times"
            severity="danger"
            variant="text"
            rounded
            size="small"
            aria-label="Remove from playlist"
            v-tooltip.top="'Remove from playlist'"
            @click.stop="removeTrack(track)"
          />
        </TrackRow>
      </div>
      <p v-else class="status">No tracks yet — add some below.</p>

      <button class="adder" :class="{ open: adding }" @click="adding = !adding">
        <i class="pi pi-chevron-right" />
        Add tracks
      </button>

      <div v-if="adding" class="add-panel">
        <IconField class="search">
          <InputIcon class="pi pi-search" />
          <InputText v-model="addSearch" placeholder="Search library…" autocomplete="off" />
        </IconField>

        <div v-if="addable.length" class="list">
          <TrackRow
            v-for="track in addable"
            :key="track.id"
            :track="track"
            :clickable="false"
          >
            <Button
              icon="pi pi-plus"
              severity="secondary"
              variant="text"
              rounded
              size="small"
              :loading="pendingAdd === track.id"
              aria-label="Add to playlist"
              v-tooltip.top="'Add to playlist'"
              @click="addTrack(track)"
            />
          </TrackRow>
        </div>
        <p v-else class="status">
          {{ addSearch.trim() ? 'Nothing in the library matches that.' : 'Every library track is already here.' }}
        </p>
      </div>
    </template>
  </section>
</template>

<style scoped>
.back {
  margin-bottom: 18px;
}

.status {
  color: var(--fg-dim);
  font-size: 13px;
  padding: 14px 0;
}

.hero {
  display: flex;
  align-items: flex-end;
  gap: 24px;
  margin-bottom: 26px;
}

.cover {
  --art: 160px;
  position: relative;
  flex: none;
}

.recover {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: none;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 11.5px;
  font-weight: 640;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s;
}

.recover i {
  font-size: 17px;
}

.cover:hover .recover,
.recover:focus-visible {
  opacity: 1;
}

.about {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.name {
  font-size: 36px;
  font-weight: 800;
  letter-spacing: -1px;
  line-height: 1.1;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.tags span {
  padding: 2px 9px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.07);
  color: var(--fg-muted);
  font-size: 11.5px;
}

.count {
  font-size: 12px;
  color: var(--fg-muted);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}

.edit {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 460px;
  margin-bottom: 24px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--line);
  border-radius: var(--radius-panel);
}

.edit :deep(.p-button) {
  align-self: flex-start;
}

.section-head {
  font-size: 14px;
  font-weight: 700;
  padding-bottom: 8px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--line);
}

.list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.adder {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding: 10px 0;
  border: none;
  background: none;
  color: var(--fg-muted);
  font-size: 14px;
  font-weight: 640;
  cursor: pointer;
  transition: color 0.12s;
}

.adder:hover {
  color: var(--fg);
}

.adder i {
  font-size: 12px;
  transition: transform 0.15s;
}

.adder.open i {
  transform: rotate(90deg);
}

.add-panel {
  margin-top: 4px;
}

.search {
  display: block;
  max-width: 380px;
  margin-bottom: 10px;
}

.search :deep(input) {
  width: 100%;
}

/* Hover never happens on a touchscreen; keep the affordance on screen. */
@media (hover: none) {
  .recover {
    opacity: 1;
    background: rgba(0, 0, 0, 0.38);
  }
}

@media (max-width: 760px) {
  .hero {
    flex-direction: column;
    align-items: flex-start;
    gap: 14px;
  }

  .cover {
    --art: 128px;
  }

  .name {
    font-size: 26px;
  }
}
</style>
