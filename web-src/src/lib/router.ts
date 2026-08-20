/**
 * Hash routing, hand-rolled.
 *
 * The bot serves exactly one HTML file at "/", so history routes would 404 on
 * reload; the hash keeps deep links and the browser Back button working without
 * asking anything of the server.
 */
import { computed, ref } from 'vue';

export type TabName = 'playlists' | 'library' | 'settings';

export interface Route {
  tab: TabName;
  playlistId: number | null;
}

const TABS: TabName[] = ['playlists', 'library', 'settings'];

function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  const tab = (TABS as string[]).includes(parts[0]) ? (parts[0] as TabName) : 'playlists';
  const id = tab === 'playlists' && parts[1] ? Number.parseInt(parts[1], 10) : Number.NaN;
  return { tab, playlistId: Number.isNaN(id) ? null : id };
}

const route = ref<Route>(parse(location.hash));

window.addEventListener('hashchange', () => {
  route.value = parse(location.hash);
});

export function navigate(path: string): void {
  const target = path.startsWith('#') ? path : `#${path}`;
  if (location.hash === target) route.value = parse(target);
  else location.hash = target;
}

export const currentRoute = computed(() => route.value);
export const showTab = (tab: TabName) => navigate(`/${tab}`);
export const openPlaylist = (id: number) => navigate(`/playlists/${id}`);
