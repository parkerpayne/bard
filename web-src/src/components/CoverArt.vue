<script setup lang="ts">
/**
 * A playlist or track image, with a stand-in for the very common case of not
 * having one. The stand-in is tinted by a hash of the name so a cover-less
 * playlist still has its own identity — kept dark and desaturated so a wall of
 * them stays quiet next to the accent.
 */
import { computed } from 'vue';
import { hueFor } from '@/lib/format';
import BardMark from './BardMark.vue';

const props = withDefaults(
  defineProps<{
    src?: string | null;
    seed?: string;
    /** Any CSS length; the art is always square. */
    size?: string;
    radius?: string;
    glyph?: number;
  }>(),
  { src: null, seed: '', size: '100%', radius: '6px', glyph: 0 },
);

// The hash spans the whole colour wheel; fold it into the green-to-teal
// stretch so a wall of cover-less playlists reads as a family rather than as
// a paint chart next to the accent.
const hue = computed(() => 96 + (hueFor(props.seed || 'bard') % 84));
const fallback = computed(
  () => `linear-gradient(150deg, hsl(${hue.value} 24% 21%), hsl(${hue.value} 20% 11%))`,
);
/** Default the glyph to a bit under half the box when the box has a fixed size. */
const glyphSize = computed(() => props.glyph || 22);
</script>

<template>
  <div class="cover" :style="{ width: size, height: size, borderRadius: radius }">
    <img v-if="src" :src="src" alt="" loading="lazy" decoding="async" />
    <div v-else class="ph" :style="{ background: fallback }">
      <BardMark :size="glyphSize" />
    </div>
  </div>
</template>

<style scoped>
.cover {
  flex: none;
  overflow: hidden;
  background: var(--ink-300);
}

.cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.ph {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: rgba(255, 255, 255, 0.34);
}
</style>
