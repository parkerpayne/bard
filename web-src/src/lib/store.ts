/**
 * The two collections every view reads from. Kept in one place so that adding a
 * track in the library and seeing the playlist counts update does not depend on
 * which component happened to fetch last.
 */
import { ref } from 'vue';
import { api, type Playlist, type Track } from './api';

export const playlists = ref<Playlist[]>([]);
export const libraryTracks = ref<Track[]>([]);
export const playlistsLoaded = ref(false);
export const libraryLoaded = ref(false);

export async function refreshPlaylists(): Promise<void> {
  const data = await api.playlists();
  if (data) playlists.value = data.playlists ?? [];
  playlistsLoaded.value = true;
}

export async function refreshLibrary(): Promise<void> {
  const data = await api.libraryTracks();
  if (data) libraryTracks.value = data;
  libraryLoaded.value = true;
}
