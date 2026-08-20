/**
 * Bard desktop shell.
 *
 * The whole reason this exists is globalShortcut: a page in a browser cannot
 * claim a key combination that fires while another application has focus, and
 * the main process can. Everything else here is in service of that — the
 * window is the ordinary web UI, loaded from the bot.
 */
import {
  app,
  BrowserWindow,
  globalShortcut,
  ipcMain,
  Menu,
  nativeImage,
  shell,
  Tray,
} from 'electron';
import path from 'node:path';
import { load, normaliseServerUrl, save, type Config } from './config';
import { createHotkeys, type Binding } from './hotkeys';

let config: Config = { serverUrl: null };
let win: BrowserWindow | null = null;
let tray: Tray | null = null;
/** Set when the user picks Quit, so 'close' stops meaning "hide". */
let quitting = false;

// Wayland does not let an application grab keys directly; Chromium has to ask
// the compositor through xdg-desktop-portal, and that path is behind a feature
// flag. Harmless where it is not used — on X11/XWayland, which is what Electron
// picks by default here, keys are grabbed directly and this changes nothing.
// Where the compositor ships no GlobalShortcuts portal backend (wlroots, some
// others) shortcuts may still register and never fire; that is a compositor
// limitation, not something the app can work around.
if (process.platform === 'linux') {
  app.commandLine.appendSwitch('enable-features', 'GlobalShortcutsPortal');
}

// One instance only: two copies would fight over the same accelerators, and
// the second would simply fail to register them.
if (!app.requestSingleInstanceLock()) {
  app.quit();
}

app.on('second-instance', () => reveal());

// ── Window ────────────────────────────────────────────────────────────────

function createWindow(): void {
  win = new BrowserWindow({
    width: 1180,
    height: 820,
    minWidth: 380,
    minHeight: 480,
    show: false,
    backgroundColor: '#070a08',
    autoHideMenuBar: true,
    title: 'Bard Music',
    icon: trayImage(),
    webPreferences: {
      preload: path.join(
        __dirname,
        config.serverUrl ? 'preload.js' : 'setup-preload.js',
      ),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      // The preload reads this and refuses to expose anything unless the page
      // it landed in really is this origin.
      additionalArguments: config.serverUrl ? [`--bard-origin=${config.serverUrl}`] : [],
    },
  });

  win.once('ready-to-show', () => win?.show());

  // Closing the window must not stop the shortcuts — that is the app's whole
  // job. It goes to the tray instead, and Quit is explicit.
  win.on('close', (event) => {
    if (quitting) return;
    event.preventDefault();
    win?.hide();
  });

  win.on('closed', () => {
    win = null;
  });

  // Keep the window on the bot and send everything else to the real browser.
  win.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: 'deny' };
  });

  win.webContents.on('will-navigate', (event, url) => {
    const allowed = config.serverUrl;
    if (allowed && new URL(url).origin !== allowed) {
      event.preventDefault();
      void shell.openExternal(url);
    }
  });

  void loadUi();
}

function loadUi(): Promise<void> {
  if (!win) return Promise.resolve();
  if (!config.serverUrl) {
    return win.loadFile(path.join(__dirname, '..', 'static', 'setup.html'));
  }
  return win.loadURL(config.serverUrl).catch(() => {
    // Unreachable server: fall back to the setup page rather than a Chromium
    // error page the user cannot do anything with.
    return win?.loadFile(path.join(__dirname, '..', 'static', 'setup.html'));
  });
}

function reveal(): void {
  if (!win) {
    createWindow();
    return;
  }
  if (!win.isVisible()) win.show();
  if (win.isMinimized()) win.restore();
  win.focus();
}

// ── Tray ──────────────────────────────────────────────────────────────────

/** The app icon: a lyre, drawn small enough to read in a system tray. */
function trayImage() {
  return nativeImage.createFromPath(path.join(__dirname, '..', 'static', 'tray.png'));
}

function createTray(): void {
  tray = new Tray(trayImage());
  tray.setToolTip('Bard Music');
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: 'Show Bard', click: reveal },
      { type: 'separator' },
      {
        label: 'Change server…',
        click: () => {
          config = { serverUrl: null };
          save(config);
          rebuildWindow();
        },
      },
      { type: 'separator' },
      {
        label: 'Quit',
        click: () => {
          quitting = true;
          app.quit();
        },
      },
    ]),
  );
  tray.on('click', reveal);
}

function rebuildWindow(): void {
  hotkeys.clear();
  const old = win;
  win = null;
  old?.destroy();
  createWindow();
}

// ── Shortcuts ─────────────────────────────────────────────────────────────

const hotkeys = createHotkeys({
  sendToRenderer(playlistId) {
    if (!win || win.isDestroyed()) return false;
    win.webContents.send('hotkey:pressed', playlistId);
    return true;
  },

  /**
   * The session's cookie jar is the one the user logged in with, so this call
   * carries the same authentication the UI does — there is no second
   * credential to store anywhere.
   */
  async triggerOnServer(playlistId) {
    if (!config.serverUrl || !win) return true;
    try {
      const response = await win.webContents.session.fetch(
        `${config.serverUrl}/api/hotkeys/trigger`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ playlist_id: playlistId }),
          credentials: 'include',
        },
      );
      return response.status !== 401;
    } catch {
      // Server unreachable. Nothing useful to do from a hotkey press.
      return true;
    }
  },

  onUnauthorized() {
    // The session expired; showing the window lands the user on /login.
    reveal();
  },
});

// ── IPC ───────────────────────────────────────────────────────────────────

ipcMain.handle('hotkeys:sync', (_event, next: Binding[]) => {
  // The renderer is remote content; treat anything it sends as untrusted.
  const clean = Array.isArray(next)
    ? next.filter(
        (b) => typeof b?.playlist_id === 'number' && typeof b?.accelerator === 'string',
      )
    : [];
  return hotkeys.sync(clean);
});

ipcMain.on('device:set', (_event, next: unknown) => hotkeys.setDevice(next));

ipcMain.handle('setup:get', () => config.serverUrl);

ipcMain.handle('setup:save', (_event, raw: unknown) => {
  const url = normaliseServerUrl(String(raw ?? ''));
  if (!url) return { ok: false, message: 'That does not look like an address.' };
  config = { serverUrl: url };
  save(config);
  rebuildWindow();
  return { ok: true };
});

// ── Lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(() => {
  config = load();
  createWindow();
  createTray();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
    else reveal();
  });
});

// Every platform: closing the last window leaves the shell running in the
// tray, because the shortcuts are the point and they need a live process.
app.on('window-all-closed', () => {});

app.on('before-quit', () => {
  quitting = true;
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

