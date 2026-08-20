<script setup lang="ts">
/**
 * One track line — used by the library, a playlist's tracks, and the
 * add-tracks picker. The trailing controls differ in each, so they arrive as a
 * slot rather than as three sets of props.
 */
import type { Track } from '@/lib/api';
import { formatDuration } from '@/lib/format';
import CoverArt from './CoverArt.vue';

withDefaults(
  defineProps<{
    track: Track;
    /** 1-based; omitted where the list has no meaningful order. */
    index?: number | null;
    playing?: boolean;
    /** Rows that start playback look clickable; the picker's rows do not. */
    clickable?: boolean;
  }>(),
  { index: null, playing: false, clickable: true },
);

defineEmits<{ activate: [] }>();
</script>

<template>
  <div
    class="row"
    :class="{ playing, clickable }"
    :tabindex="clickable ? 0 : undefined"
    :role="clickable ? 'button' : undefined"
    @click="clickable && $emit('activate')"
    @keydown.enter.prevent="clickable && $emit('activate')"
    @keydown.space.prevent="clickable && $emit('activate')"
  >
    <!-- Always present, sometimes blank: keeps the numbered list and the
         un-numbered add-picker on the same column grid. -->
    <span class="num tabular">
      <i v-if="playing" class="pi pi-volume-up" />
      <template v-else-if="index !== null">{{ index }}</template>
    </span>
    <CoverArt
      :src="track.thumbnail_url"
      :seed="track.title"
      size="42px"
      radius="5px"
      :glyph="17"
    />
    <div class="title truncate">{{ track.title }}</div>
    <span class="dur tabular">{{ formatDuration(track.duration_sec) }}</span>
    <div class="actions"><slot /></div>
  </div>
</template>

<style scoped>
.row {
  display: grid;
  grid-template-columns: 26px 42px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 12px;
  padding: 6px 10px;
  border-radius: 8px;
  transition: background 0.12s;
}

.row.clickable {
  cursor: pointer;
}

.row:hover,
.row:focus-visible {
  background: rgba(255, 255, 255, 0.05);
}

.num {
  font-size: 12px;
  color: var(--fg-dim);
  text-align: right;
}

.playing .num {
  color: var(--accent);
}

.title {
  font-size: 13.5px;
  font-weight: 500;
}

.playing .title {
  color: var(--accent);
}

.dur {
  font-size: 12px;
  color: var(--fg-muted);
}

/* Hover-reveal, but never hide something a keyboard user has focused. */
.actions {
  display: flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.12s;
}

.row:hover .actions,
.row:focus-within .actions {
  opacity: 1;
}

/* Nothing reveals on hover on a touchscreen. */
@media (hover: none) {
  .actions {
    opacity: 1;
  }
}

@media (max-width: 760px) {
  .row {
    grid-template-columns: 42px minmax(0, 1fr) auto auto;
    gap: 10px;
    padding: 6px 4px;
  }

  .num {
    display: none;
  }
}
</style>
