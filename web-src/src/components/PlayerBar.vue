<script setup lang="ts">
/**
 * Transport for whichever device is driving playback. Everything here reads
 * from lib/player, which already hides the browser/voice split — the one place
 * the difference shows through is seeking, which voice cannot do.
 */
import { computed, ref } from 'vue';
import Slider from 'primevue/slider';
import { player } from '@/lib/player';
import { playlists } from '@/lib/store';
import { formatDuration } from '@/lib/format';
import CoverArt from './CoverArt.vue';
import DeviceMenu from './DeviceMenu.vue';
import IconShuffle from './IconShuffle.vue';

const {
  current, isPlaying, position, duration, canSeek, shuffled, volume, playlistId, queue,
} = player;

const scrub = ref<HTMLElement | null>(null);

const progressPct = computed(() =>
  duration.value ? Math.min(100, (position.value / duration.value) * 100) : 0,
);

/** The line under the title: where this is coming from, not who made it. */
const subtitle = computed(() => {
  if (!current.value) return '';
  const source = playlists.value.find((p) => p.id === playlistId.value);
  const where = player.device.value === 'voice' ? 'Discord' : 'Browser';
  return source ? `${source.name} · ${where}` : where;
});

const volumeIcon = computed(() => {
  if (volume.value <= 0) return 'pi pi-volume-off';
  return volume.value < 0.5 ? 'pi pi-volume-down' : 'pi pi-volume-up';
});

/** Volume is a model, not an event stream — the setter also persists it. */
const volumePct = computed({
  get: () => Math.round(volume.value * 100),
  set: (value: number) => player.setVolume(value / 100),
});

function seekFromPointer(event: PointerEvent) {
  const track = scrub.value;
  if (!track || !canSeek.value) return;
  const box = track.getBoundingClientRect();
  const ratio = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
  player.seekTo(ratio * duration.value);
}

function nudge(seconds: number) {
  if (canSeek.value) player.seekTo(position.value + seconds);
}
</script>

<template>
  <footer class="bar">
    <div class="now">
      <CoverArt
        :src="current?.thumbnail_url ?? null"
        :seed="current?.title ?? ''"
        size="var(--art)"
        radius="6px"
        :glyph="20"
      />
      <div class="meta">
        <div class="title truncate">{{ current?.title ?? 'Nothing playing' }}</div>
        <div class="sub truncate">{{ subtitle }}</div>
      </div>
    </div>

    <div class="transport">
      <div class="buttons">
        <button
          class="ctrl side"
          :class="{ on: shuffled }"
          :aria-pressed="shuffled"
          title="Shuffle"
          @click="player.setShuffled(!shuffled)"
        >
          <IconShuffle :size="16" />
        </button>
        <button class="ctrl prev" title="Previous" @click="player.previous()">
          <i class="pi pi-step-backward" />
        </button>
        <button
          class="ctrl play"
          :title="isPlaying ? 'Pause' : 'Play'"
          :disabled="!current"
          @click="player.togglePlay()"
        >
          <i :class="isPlaying ? 'pi pi-pause' : 'pi pi-play'" />
        </button>
        <button class="ctrl" title="Next" @click="player.next()">
          <i class="pi pi-step-forward" />
        </button>
        <button
          class="ctrl side"
          title="Stop"
          :disabled="!current && !queue.length"
          @click="player.stop()"
        >
          <i class="pi pi-stop" />
        </button>
      </div>

      <div class="scrubber">
        <span class="time tabular">{{ formatDuration(position) }}</span>
        <div
          ref="scrub"
          class="track"
          :class="{ seekable: canSeek }"
          role="slider"
          :tabindex="canSeek ? 0 : -1"
          :aria-valuemin="0"
          :aria-valuemax="Math.round(duration)"
          :aria-valuenow="Math.round(position)"
          :aria-valuetext="formatDuration(position)"
          aria-label="Seek"
          @pointerdown="seekFromPointer"
          @keydown.left.prevent="nudge(-5)"
          @keydown.right.prevent="nudge(5)"
        >
          <div class="fill" :style="{ width: progressPct + '%' }" />
        </div>
        <span class="time tabular">{{ formatDuration(duration) }}</span>
      </div>
    </div>

    <div class="right">
      <div class="volume">
        <i :class="volumeIcon" />
        <Slider v-model="volumePct" class="vol" :min="0" :max="100" aria-label="Volume" />
      </div>
      <DeviceMenu />
    </div>
  </footer>
</template>

<style scoped>
.bar {
  --art: 54px;
  grid-area: bar;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  background: var(--ink-100);
  border-top: 1px solid var(--line);
}

.now {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.meta {
  min-width: 0;
}

.title {
  font-size: 13px;
  font-weight: 640;
}

.sub {
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 1px;
}

.transport {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.buttons {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ctrl {
  display: grid;
  place-items: center;
  padding: 5px;
  border: none;
  border-radius: 50%;
  background: none;
  color: var(--fg-muted);
  font-size: 15px;
  cursor: pointer;
  transition: color 0.12s, transform 0.12s;
}

.ctrl:hover:not(:disabled) {
  color: var(--fg);
}

.ctrl:disabled {
  opacity: 0.35;
  cursor: default;
}

.ctrl.on {
  color: var(--accent);
}

.play {
  width: 34px;
  height: 34px;
  padding: 0;
  background: var(--fg);
  color: var(--ink-000);
  font-size: 13px;
}

.play:hover:not(:disabled) {
  color: var(--ink-000);
  transform: scale(1.06);
}

.scrubber {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  max-width: 520px;
}

.time {
  font-size: 11px;
  color: var(--fg-muted);
  min-width: 34px;
  text-align: center;
}

.track {
  flex: 1;
  height: 4px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
}

.track.seekable {
  cursor: pointer;
}

.fill {
  height: 100%;
  border-radius: inherit;
  background: var(--fg-muted);
  transition: width 0.25s linear;
}

.track.seekable:hover .fill,
.track.seekable:focus-visible .fill {
  background: var(--accent);
}

.right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.volume {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--fg-dim);
}

.vol {
  width: 84px;
}

@media (max-width: 760px) {
  .bar {
    --art: 42px;
    grid-template-columns: auto minmax(0, 1fr) auto;
    padding: 0 10px;
    gap: 10px;
    position: relative;
  }

  /* Shuffle and stop live on the playlist screens; the bar keeps
     prev-play-next so every target stays thumb-sized. */
  .side {
    display: none;
  }

  .ctrl {
    padding: 8px;
  }

  .play {
    width: 40px;
    height: 40px;
    padding: 0;
  }

  .transport {
    flex-direction: row;
    gap: 0;
  }

  /* Progress becomes a hairline across the top of the bar. */
  .scrubber {
    position: absolute;
    inset: 0 0 auto 0;
    gap: 0;
    pointer-events: none;
  }

  .time {
    display: none;
  }

  .track {
    height: 2px;
    border-radius: 0;
  }

  .fill {
    border-radius: 0;
  }

  /* The phone has volume keys. */
  .volume {
    display: none;
  }
}

@media (max-width: 380px) {
  .prev {
    display: none;
  }
}
</style>
