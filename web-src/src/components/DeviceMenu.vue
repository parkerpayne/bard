<script setup lang="ts">
/**
 * Where the audio comes out: this tab, or the bot in a Discord voice channel.
 * The bot picks the channel itself (the busiest one with people in it), so this
 * offers the two destinations and shows which channel that would be.
 */
import { ref } from 'vue';
import Popover from 'primevue/popover';
import { player } from '@/lib/player';

// Pulled out as top-level bindings so the template auto-unwraps them; refs
// reached through the `player` object would need .value everywhere.
const { device } = player;

const popover = ref<InstanceType<typeof Popover> | null>(null);
const busy = ref(false);

function toggle(event: Event) {
  popover.value?.toggle(event);
}

/**
 * Who is sitting in a voice channel changes without us, so the list is
 * refreshed every time this opens — but only once the overlay is actually in
 * the DOM. Kicking the fetch off before that races the open: it resolves
 * mid-transition, re-renders the panel, and Vue patches into a container that
 * does not exist yet.
 */
function refreshOnShow() {
  void player.fetchDevices();
}

async function choose(type: 'browser' | 'voice') {
  busy.value = true;
  await player.selectDevice(type);
  busy.value = false;
  popover.value?.hide();
}
</script>

<template>
  <div class="picker">
    <button
      class="trigger"
      :class="{ voice: device === 'voice' }"
      :title="player.voiceMeta()"
      aria-haspopup="true"
      @click="toggle"
    >
      <i :class="device === 'voice' ? 'pi pi-discord' : 'pi pi-desktop'" />
      <span class="label">{{ device === 'voice' ? 'Discord' : 'Browser' }}</span>
      <i class="pi pi-chevron-down caret" />
    </button>

    <Popover ref="popover" @show="refreshOnShow">
      <div class="menu">
        <div class="section-label heading">Play on</div>

        <button
          class="option"
          :class="{ active: device === 'browser' }"
          :disabled="busy"
          @click="choose('browser')"
        >
          <i class="pi pi-desktop" />
          <span class="info">
            <span class="name">Browser</span>
            <span class="meta">This tab</span>
          </span>
          <i v-if="device === 'browser'" class="pi pi-check tick" />
        </button>

        <button
          class="option"
          :class="{ active: device === 'voice' }"
          :disabled="busy"
          @click="choose('voice')"
        >
          <i class="pi pi-discord" />
          <span class="info">
            <span class="name">Discord</span>
            <span class="meta truncate">{{ player.voiceMeta() }}</span>
          </span>
          <i v-if="device === 'voice'" class="pi pi-check tick" />
        </button>
      </div>
    </Popover>
  </div>
</template>

<style scoped>
.trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  background: none;
  color: var(--fg-muted);
  font-size: 12px;
  font-weight: 640;
  cursor: pointer;
  transition: color 0.12s, border-color 0.12s;
}

.trigger:hover {
  color: var(--fg);
  border-color: var(--fg-muted);
}

.trigger.voice {
  color: var(--accent);
  border-color: var(--accent);
}

.caret {
  font-size: 9px;
}

.menu {
  min-width: 236px;
}

.heading {
  padding: 2px 8px 6px;
}

.option {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 8px;
  border: none;
  border-radius: 8px;
  background: none;
  color: var(--fg-muted);
  cursor: pointer;
  text-align: left;
}

.option:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.07);
}

.option:disabled {
  cursor: progress;
  opacity: 0.7;
}

.option.active {
  color: var(--accent);
}

.info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.name {
  font-size: 13px;
  font-weight: 640;
  color: var(--fg);
}

.option.active .name {
  color: var(--accent);
}

.meta {
  font-size: 11.5px;
  color: var(--fg-muted);
}

.tick {
  font-size: 12px;
}

@media (max-width: 760px) {
  .trigger {
    padding: 9px 11px;
  }

  .label {
    display: none;
  }
}
</style>
