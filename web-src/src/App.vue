<script setup lang="ts">
/**
 * The shell: rail, one view, player bar. Routing is by hash (lib/router), so
 * the whole app is still the single HTML file the bot serves at "/".
 */
import { computed, onMounted, onBeforeUnmount } from 'vue';
import ConfirmDialog from 'primevue/confirmdialog';
import Toast from 'primevue/toast';
import { useToast } from 'primevue/usetoast';
import { currentRoute } from '@/lib/router';
import { setNotifier } from '@/lib/notify';
import { player } from '@/lib/player';
import { initDesktop, warnIfRejected } from '@/lib/desktop';
import NavRail from '@/components/NavRail.vue';
import PlayerBar from '@/components/PlayerBar.vue';
import LibraryView from '@/views/LibraryView.vue';
import PlaylistDetailView from '@/views/PlaylistDetailView.vue';
import PlaylistsView from '@/views/PlaylistsView.vue';
import SettingsView from '@/views/SettingsView.vue';

const toast = useToast();
// Hand the plain modules a way to talk: notify() is called from lib/player,
// which has no component to inject the service into.
setNotifier((message) => toast.add(message));

const view = computed(() => {
  if (currentRoute.value.tab === 'library') return LibraryView;
  if (currentRoute.value.tab === 'settings') return SettingsView;
  return currentRoute.value.playlistId === null ? PlaylistsView : PlaylistDetailView;
});

function onKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null;
  // Never steal a key from something the user is typing into.
  if (target?.closest('input, textarea, [contenteditable="true"]')) return;
  if (event.metaKey || event.ctrlKey || event.altKey) return;

  if (event.code === 'Space') {
    event.preventDefault();
    void player.togglePlay();
  } else if (event.shiftKey && event.code === 'ArrowRight') {
    void player.next();
  } else if (event.shiftKey && event.code === 'ArrowLeft') {
    void player.previous();
  }
}

onMounted(() => {
  player.init();
  // No-op in a plain browser; in the Electron shell it registers the global
  // shortcuts and starts listening for presses.
  initDesktop();
  setTimeout(warnIfRejected, 1500);
  window.addEventListener('keydown', onKeydown);
});

onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown));
</script>

<template>
  <div class="shell">
    <NavRail />
    <main class="stage">
      <!-- Keyed on the route so switching playlists remounts rather than
           leaving the previous one's scroll position and open panels behind. -->
      <component
        :is="view"
        :key="`${currentRoute.tab}:${currentRoute.playlistId ?? ''}`"
        v-bind="currentRoute.playlistId !== null ? { id: currentRoute.playlistId } : {}"
      />
    </main>
    <PlayerBar />

    <Toast position="top-right" />
    <ConfirmDialog />
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-areas: 'rail stage' 'bar bar';
  grid-template-columns: var(--rail-w) minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr) var(--bar-h);
  height: 100dvh;
  position: relative;
  z-index: 1;
}

.stage {
  grid-area: stage;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 28px 26px 32px;
}

@media (max-width: 760px) {
  .shell {
    grid-template-areas: 'stage' 'bar' 'rail';
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) var(--bar-h) auto;
  }

  .stage {
    padding: 18px 14px 12px;
    -webkit-overflow-scrolling: touch;
  }
}
</style>
