/**
 * The seam between the web app and the Electron shell.
 *
 * Everything here degrades to "not running in the desktop app": the same build
 * is served to an ordinary browser, where `window.bard` simply does not exist
 * and the hotkey settings explain why they cannot take effect.
 */
import { ref, watch } from 'vue';
import { api } from './api';
import { notify } from './notify';
import { player } from './player';

/** Injected by electron/preload.ts via contextBridge. */
export interface DesktopBridge {
  readonly version: string;
  /** Push the current bindings at the main process, which owns registration. */
  syncHotkeys(hotkeys: { playlist_id: number; accelerator: string }[]): Promise<{
    registered: string[];
    failed: string[];
  }>;
  /** Fired when a registered accelerator is pressed. */
  onHotkey(handler: (playlistId: number) => void): void;
  /** Which device the shell should route presses to, so it can decide alone. */
  setDevice(device: 'browser' | 'voice'): void;
}

declare global {
  interface Window {
    bard?: DesktopBridge;
  }
}

export const bridge = window.bard ?? null;
export const isDesktop = bridge !== null;

/** Accelerators the shell could not register — usually another app has them. */
export const rejected = ref<string[]>([]);

/**
 * Hand the shell the current bindings. Safe to call from a browser, where it
 * does nothing.
 */
export async function syncHotkeys(): Promise<void> {
  if (!bridge) return;
  const data = await api.hotkeys();
  if (!data) return;
  const result = await bridge.syncHotkeys(
    data.hotkeys.map((h) => ({ playlist_id: h.playlist_id, accelerator: h.accelerator })),
  );
  rejected.value = result.failed;
}

/**
 * Browser-device playback lives in this renderer, so the shell cannot do it
 * alone — it forwards the press here and we run the same toggle the UI would.
 */
function toggleLocally(playlistId: number): void {
  const isCurrent = player.playlistId.value === playlistId;
  if (isCurrent && player.current.value) {
    void player.togglePlay();
    return;
  }
  void player.playPlaylist(playlistId);
}

let wired = false;

export function initDesktop(): void {
  if (!bridge || wired) return;
  wired = true;

  bridge.onHotkey((playlistId) => {
    // The shell only forwards a press when the device is "browser"; anything
    // else it sends straight to the server so playback does not depend on this
    // window being alive.
    toggleLocally(playlistId);
  });

  // Keep the shell's routing decision in step with the picker in the player
  // bar. The shell has to know, because a press that arrives while nothing is
  // listening should still reach the bot.
  watch(player.device, (device) => bridge.setDevice(device), { immediate: true });

  void syncHotkeys();
}

/** Surface a shell-side failure once, rather than silently doing nothing. */
export function warnIfRejected(): void {
  if (rejected.value.length) {
    notify.error(
      'Some shortcuts could not be registered',
      `${rejected.value.join(', ')} — another application already holds them.`,
    );
  }
}
