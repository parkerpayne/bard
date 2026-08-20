<script setup lang="ts">
/**
 * Everything ever imported, newest first. Playing a row queues the whole
 * library from that point, so the list keeps going on its own.
 */
import { computed, onMounted, ref } from 'vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';
import Popover from 'primevue/popover';
import { useConfirm } from 'primevue/useconfirm';
import { api, type Track } from '@/lib/api';
import { notify } from '@/lib/notify';
import { player } from '@/lib/player';
import { libraryLoaded, libraryTracks, playlists, refreshLibrary, refreshPlaylists } from '@/lib/store';
import { pluralize } from '@/lib/format';
import EmptyState from '@/components/EmptyState.vue';
import TrackRow from '@/components/TrackRow.vue';

const confirm = useConfirm();
const { current } = player;

const url = ref('');
const importing = ref(false);
const message = ref<{ text: string; tone: 'ok' | 'bad' | 'busy' } | null>(null);

const addTarget = ref<Track | null>(null);
const addPopover = ref<InstanceType<typeof Popover> | null>(null);

onMounted(() => {
  void refreshLibrary();
  if (!playlists.value.length) void refreshPlaylists();
});

async function importUrl() {
  const value = url.value.trim();
  if (!value || importing.value) return;

  importing.value = true;
  message.value = {
    // A playlist URL means yt-dlp walks every entry; say so before the wait.
    text: value.includes('list=') ? 'Fetching playlist — this can take a moment…' : 'Fetching track info…',
    tone: 'busy',
  };

  const result = await api.importUrl(value);
  if (result.ok) {
    url.value = '';
    message.value = {
      text:
        result.imported === 1
          ? `Imported: ${result.track.title}`
          : `Imported ${result.imported} tracks${result.skipped ? ` (${result.skipped} unavailable)` : ''}`,
      tone: 'ok',
    };
    await refreshLibrary();
  } else {
    message.value = { text: result.message || 'Import failed.', tone: 'bad' };
  }
  importing.value = false;
}

function play(track: Track) {
  player.playLibrary(libraryTracks.value, track.id);
}

function openAddMenu(event: Event, track: Track) {
  addTarget.value = track;
  addPopover.value?.show(event);
}

/**
 * Top up the list only once the overlay is mounted. Starting the fetch before
 * the popover opens races it: the response lands mid-transition and Vue tries
 * to patch a panel that is not in the DOM yet.
 */
function refreshOnShow() {
  if (!playlists.value.length) void refreshPlaylists();
}

async function addToPlaylist(playlistId: number, name: string) {
  const track = addTarget.value;
  addPopover.value?.hide();
  if (!track) return;
  const result = await api.addTracks(playlistId, [track.id]);
  if (result.ok) {
    notify.success(`Added to ${name}`);
    await refreshPlaylists();
  } else {
    notify.error('Could not add', result.message);
  }
}

function removeTrack(track: Track) {
  confirm.require({
    header: 'Remove from library?',
    message: `"${track.title}" will also be removed from every playlist it is on.`,
    acceptLabel: 'Remove',
    rejectLabel: 'Cancel',
    acceptProps: { severity: 'danger' },
    rejectProps: { severity: 'secondary', variant: 'text' },
    accept: async () => {
      const result = await api.deleteTrack(track.id);
      if (result.ok) {
        notify.success('Removed from library');
        await Promise.all([refreshLibrary(), refreshPlaylists()]);
      } else {
        notify.error('Could not remove', result.message);
      }
    },
  });
}

const countLabel = computed(() => pluralize(libraryTracks.value.length, 'track'));
</script>

<template>
  <section>
    <h1 class="page-title">Library</h1>
    <p class="page-sub">{{ libraryLoaded ? countLabel : 'Loading…' }} imported from YouTube</p>

    <div class="importer">
      <InputText
        v-model="url"
        type="url"
        placeholder="Paste a YouTube video or playlist URL…"
        autocomplete="off"
        spellcheck="false"
        :disabled="importing"
        @keydown.enter="importUrl"
      />
      <Button
        :label="importing ? 'Importing…' : 'Import'"
        :loading="importing"
        :disabled="!url.trim()"
        @click="importUrl"
      />
    </div>

    <p v-if="message" class="message" :class="message.tone">{{ message.text }}</p>

    <div v-if="libraryTracks.length" class="list">
      <TrackRow
        v-for="(track, i) in libraryTracks"
        :key="track.id"
        :track="track"
        :index="i + 1"
        :playing="current?.id === track.id"
        @activate="play(track)"
      >
        <Button
          icon="pi pi-plus"
          severity="secondary"
          variant="text"
          rounded
          size="small"
          aria-label="Add to playlist"
          v-tooltip.top="'Add to playlist'"
          @click.stop="openAddMenu($event, track)"
        />
        <Button
          icon="pi pi-trash"
          severity="danger"
          variant="text"
          rounded
          size="small"
          aria-label="Remove from library"
          v-tooltip.top="'Remove from library'"
          @click.stop="removeTrack(track)"
        />
      </TrackRow>
    </div>

    <EmptyState
      v-else-if="libraryLoaded"
      icon="pi pi-database"
      title="Library is empty"
      hint="Paste a YouTube video or playlist URL above to import."
    />

    <Popover ref="addPopover" @show="refreshOnShow">
      <div class="add-menu">
        <div class="section-label heading">Add to playlist</div>
        <button
          v-for="playlist in playlists"
          :key="playlist.id"
          class="add-item truncate"
          @click="addToPlaylist(playlist.id, playlist.name)"
        >
          {{ playlist.name }}
        </button>
        <p v-if="!playlists.length" class="add-none">No playlists yet — create one first.</p>
      </div>
    </Popover>
  </section>
</template>

<style scoped>
.importer {
  display: flex;
  gap: 8px;
  max-width: 560px;
  margin-top: 22px;
}

.importer :deep(input) {
  flex: 1;
}

.message {
  font-size: 12.5px;
  margin-top: 10px;
  min-height: 18px;
}

.message.ok {
  color: var(--accent);
}

.message.bad {
  color: var(--danger);
}

.message.busy {
  color: var(--fg-muted);
}

.list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 18px;
}

.add-menu {
  min-width: 200px;
  max-width: 280px;
  max-height: 300px;
  overflow-y: auto;
}

.heading {
  padding: 2px 8px 6px;
}

.add-item {
  display: block;
  width: 100%;
  padding: 8px;
  border: none;
  border-radius: 6px;
  background: none;
  color: var(--fg-muted);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.add-item:hover {
  background: rgba(255, 255, 255, 0.07);
  color: var(--fg);
}

.add-none {
  padding: 8px;
  font-size: 12px;
  color: var(--fg-dim);
}

@media (max-width: 760px) {
  .importer {
    flex-direction: column;
    max-width: none;
  }
}
</style>
