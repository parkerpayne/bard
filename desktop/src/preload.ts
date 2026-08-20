/**
 * The bridge the web app sees as `window.bard`.
 *
 * The renderer loads the bot over HTTP, so this is a preload attached to
 * remote content. It exposes three named channels and nothing else — no
 * ipcRenderer, no Node — and only when the page really is the configured
 * server, so a page that somehow got loaded from anywhere else gets an
 * ordinary browser with no shell privileges at all.
 */
import { contextBridge, ipcRenderer } from 'electron';

interface Binding {
  playlist_id: number;
  accelerator: string;
}

const ORIGIN_FLAG = '--bard-origin=';
const expected = process.argv.find((a) => a.startsWith(ORIGIN_FLAG))?.slice(ORIGIN_FLAG.length);

if (expected && location.origin === expected) {
  contextBridge.exposeInMainWorld('bard', {
    version: process.versions.electron,

    syncHotkeys: (hotkeys: Binding[]): Promise<{ registered: string[]; failed: string[] }> =>
      ipcRenderer.invoke('hotkeys:sync', hotkeys),

    onHotkey: (handler: (playlistId: number) => void): void => {
      // The event object is deliberately not forwarded: it carries a sender
      // the page has no business touching.
      ipcRenderer.on('hotkey:pressed', (_event, playlistId: number) => handler(playlistId));
    },

    setDevice: (device: 'browser' | 'voice'): void => {
      ipcRenderer.send('device:set', device);
    },
  });
}
