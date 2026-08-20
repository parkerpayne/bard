/**
 * Registration and press routing, kept clear of the app lifecycle so the
 * decisions here can be exercised without booting a window.
 */
import { globalShortcut } from 'electron';

export interface Binding {
  playlist_id: number;
  accelerator: string;
}

export interface SyncResult {
  registered: string[];
  failed: string[];
}

export interface HotkeyDeps {
  /** Deliver a press to the renderer, which owns browser playback. */
  sendToRenderer(playlistId: number): boolean;
  /** Ask the server to toggle. Resolves false when the session has expired. */
  triggerOnServer(playlistId: number): Promise<boolean>;
  /** Called when the server says the login is gone, so the UI can show /login. */
  onUnauthorized(): void;
}

export function createHotkeys(deps: HotkeyDeps) {
  let device: 'browser' | 'voice' = 'browser';
  let bindings: Binding[] = [];

  function press(playlistId: number): void {
    // Browser playback is an <audio> element in the renderer; only it can
    // toggle that. Everything else goes to the server, so a press still works
    // with the window hidden in the tray.
    if (device === 'browser' && deps.sendToRenderer(playlistId)) return;
    void deps.triggerOnServer(playlistId).then((ok) => {
      if (!ok) deps.onUnauthorized();
    });
  }

  return {
    /**
     * Replace every registration. Reports what the OS refused instead of
     * failing quietly — a combination another application already owns simply
     * never fires, which is indistinguishable from a bug unless we say so.
     */
    sync(next: Binding[]): SyncResult {
      globalShortcut.unregisterAll();
      bindings = [];
      const registered: string[] = [];
      const failed: string[] = [];

      for (const binding of next) {
        let ok = false;
        try {
          ok = globalShortcut.register(binding.accelerator, () => press(binding.playlist_id));
        } catch {
          // Electron throws — it does not return false — on an accelerator it
          // cannot parse. The server validates these, but a hand-edited
          // database must not take the app down.
          ok = false;
        }
        (ok ? registered : failed).push(binding.accelerator);
        if (ok) bindings.push(binding);
      }
      return { registered, failed };
    },

    setDevice(next: unknown): void {
      device = next === 'voice' ? 'voice' : 'browser';
    },

    clear(): void {
      globalShortcut.unregisterAll();
      bindings = [];
    },

    /** Test seam: fire a binding without involving the OS. */
    press,
    get device() {
      return device;
    },
    get bindings(): readonly Binding[] {
      return bindings;
    },
  };
}
