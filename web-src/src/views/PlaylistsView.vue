<script setup lang="ts">
/**
 * The playlist grid, with search and tag filtering. Tags come from one
 * space/comma separated string per playlist, so the chip bar is derived from
 * the collection rather than stored anywhere.
 */
import { computed, onMounted, ref } from 'vue';
import Button from 'primevue/button';
import IconField from 'primevue/iconfield';
import InputIcon from 'primevue/inputicon';
import InputText from 'primevue/inputtext';
import { api, coverUrl } from '@/lib/api';
import { notify } from '@/lib/notify';
import { player } from '@/lib/player';
import { openPlaylist } from '@/lib/router';
import { parseTags, pluralize } from '@/lib/format';
import { playlists, playlistsLoaded, refreshPlaylists } from '@/lib/store';
import CoverArt from '@/components/CoverArt.vue';
import EmptyState from '@/components/EmptyState.vue';

const search = ref('');
const activeTags = ref<string[]>([]);

const creating = ref(false);
const newName = ref('');
const newTags = ref('');
const saving = ref(false);

onMounted(() => {
  void refreshPlaylists();
});

const allTags = computed(() =>
  [...new Set(playlists.value.flatMap((p) => parseTags(p.tags)))].sort(),
);

const filtered = computed(() => {
  const query = search.value.trim().toLowerCase();
  return playlists.value.filter((playlist) => {
    if (query) {
      const haystack = `${playlist.name} ${playlist.tags ?? ''}`.toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    // Chips narrow: a playlist has to carry every selected tag.
    const tags = new Set(parseTags(playlist.tags));
    return activeTags.value.every((tag) => tags.has(tag));
  });
});

const isFiltering = computed(() => !!search.value.trim() || activeTags.value.length > 0);

function toggleTag(tag: string) {
  activeTags.value = activeTags.value.includes(tag)
    ? activeTags.value.filter((t) => t !== tag)
    : [...activeTags.value, tag];
}

function openCreate() {
  creating.value = !creating.value;
  if (!creating.value) {
    newName.value = '';
    newTags.value = '';
  }
}

async function create() {
  const name = newName.value.trim();
  if (!name || saving.value) return;
  saving.value = true;
  const result = await api.createPlaylist(name, newTags.value.trim());
  saving.value = false;
  if (!result.ok) {
    notify.error('Could not create playlist', result.message);
    return;
  }
  newName.value = '';
  newTags.value = '';
  creating.value = false;
  await refreshPlaylists();
  notify.success(`Created "${name}"`);
}
</script>

<template>
  <section>
    <header class="head">
      <div>
        <h1 class="page-title">Playlists</h1>
        <p class="page-sub">{{ pluralize(playlists.length, 'playlist') }}</p>
      </div>
      <Button
        :icon="creating ? 'pi pi-times' : 'pi pi-plus'"
        :label="creating ? 'Cancel' : 'New playlist'"
        :severity="creating ? 'secondary' : undefined"
        :variant="creating ? 'outlined' : undefined"
        size="small"
        @click="openCreate"
      />
    </header>

    <div v-if="creating" class="create">
      <InputText v-model="newName" placeholder="Playlist name" autocomplete="off" autofocus @keydown.enter="create" />
      <InputText
        v-model="newTags"
        placeholder="Tags (e.g. epic battle ambient)"
        autocomplete="off"
        @keydown.enter="create"
      />
      <Button label="Create" size="small" :disabled="!newName.trim()" :loading="saving" @click="create" />
    </div>

    <div class="filters">
      <IconField class="search">
        <InputIcon class="pi pi-search" />
        <InputText v-model="search" placeholder="Search playlists…" autocomplete="off" />
      </IconField>

      <div v-if="allTags.length" class="tags">
        <button
          v-for="tag in allTags"
          :key="tag"
          class="chip"
          :class="{ on: activeTags.includes(tag) }"
          :aria-pressed="activeTags.includes(tag)"
          @click="toggleTag(tag)"
        >
          {{ tag }}
        </button>
        <button v-if="activeTags.length" class="chip clear" @click="activeTags = []">clear</button>
      </div>
    </div>

    <div v-if="filtered.length" class="grid">
      <article
        v-for="playlist in filtered"
        :key="playlist.id"
        class="card"
        tabindex="0"
        role="button"
        @click="openPlaylist(playlist.id)"
        @keydown.enter.prevent="openPlaylist(playlist.id)"
      >
        <div class="art">
          <CoverArt :src="coverUrl(playlist)" :seed="playlist.name" :glyph="34" />
          <!-- Straight off the grid: shuffle on, no detour through the detail view. -->
          <button
            class="go"
            :title="`Shuffle play ${playlist.name}`"
            :aria-label="`Shuffle play ${playlist.name}`"
            @click.stop="player.playPlaylist(playlist.id, null, true)"
          >
            <i class="pi pi-play" />
          </button>
        </div>
        <h2 class="name truncate">{{ playlist.name }}</h2>
        <p class="count">{{ pluralize(playlist.track_count ?? 0, 'track') }}</p>
        <div v-if="parseTags(playlist.tags).length" class="card-tags">
          <span v-for="tag in parseTags(playlist.tags)" :key="tag">{{ tag }}</span>
        </div>
      </article>
    </div>

    <EmptyState
      v-else-if="playlistsLoaded"
      icon="pi pi-list"
      :title="isFiltering ? 'No matches' : 'No playlists yet'"
      :hint="isFiltering ? 'Try a different search or tag.' : 'Create one to start grouping tracks.'"
    />
  </section>
</template>

<style scoped>
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.create {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 460px;
  margin-top: 18px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--line);
  border-radius: var(--radius-panel);
}

.create :deep(.p-button) {
  align-self: flex-start;
}

.filters {
  margin: 20px 0 18px;
}

.search {
  display: block;
  max-width: 330px;
}

.search :deep(input) {
  width: 100%;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.chip {
  padding: 4px 12px;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  background: none;
  color: var(--fg-muted);
  font-size: 12px;
  font-weight: 640;
  cursor: pointer;
  transition: color 0.12s, border-color 0.12s, background 0.12s;
}

.chip:hover {
  color: var(--fg);
  border-color: var(--fg-muted);
}

.chip.on {
  background: var(--accent);
  border-color: var(--accent);
  color: #000;
}

.chip.clear {
  border-style: dashed;
  font-style: italic;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(164px, 1fr));
  gap: 16px;
}

.card {
  padding: 12px;
  border-radius: var(--radius-card);
  background: rgba(255, 255, 255, 0.04);
  cursor: pointer;
  transition: background 0.15s;
}

.card:hover,
.card:focus-visible {
  background: rgba(255, 255, 255, 0.08);
}

.art {
  position: relative;
  aspect-ratio: 1;
  margin-bottom: 10px;
}

.go {
  position: absolute;
  right: 8px;
  bottom: 8px;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 50%;
  background: var(--accent);
  color: #000;
  font-size: 14px;
  cursor: pointer;
  opacity: 0;
  transform: translateY(6px);
  box-shadow: var(--shadow-lift);
  transition: opacity 0.15s, transform 0.15s, background 0.12s;
}

.card:hover .go,
.card:focus-within .go {
  opacity: 1;
  transform: translateY(0);
}

.go:hover {
  background: var(--accent-hi);
}

.name {
  font-size: 13px;
  font-weight: 650;
}

.count {
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 2px;
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 7px;
}

.card-tags span {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.35);
  color: var(--fg-dim);
  font-size: 11px;
}

@media (hover: none) {
  .go {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 760px) {
  .grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
  }

  .card {
    padding: 10px;
  }

  .go {
    width: 34px;
    height: 34px;
    right: 6px;
    bottom: 6px;
  }
}
</style>
