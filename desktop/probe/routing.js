/**
 * Full loop, real Electron, hidden window:
 *   renderer -> bard.syncHotkeys -> globalShortcut registration
 *   press -> routed to the renderer (browser) or the server (voice)
 *   renderer receives hotkey:pressed through the real preload
 */
const { app, BrowserWindow, globalShortcut, ipcMain } = require('electron');
const path = require('node:path');
const { createHotkeys } = require('../dist/hotkeys.js');

const ORIGIN = 'http://127.0.0.1:5198';
const out = [];
const rec = (k, v) => out.push([k, v]);

app.commandLine.appendSwitch('disable-gpu');

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    show: false,
    webPreferences: {
      preload: path.join(__dirname, '..', 'dist', 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      additionalArguments: [`--bard-origin=${ORIGIN}`],
    },
  });

  const sent = [];
  const triggered = [];
  let unauthorized = 0;
  let serverOk = true;

  const hotkeys = createHotkeys({
    sendToRenderer(id) {
      if (win.isDestroyed()) return false;
      sent.push(id);
      win.webContents.send('hotkey:pressed', id);
      return true;
    },
    async triggerOnServer(id) { triggered.push(id); return serverOk; },
    onUnauthorized() { unauthorized += 1; },
  });

  // Same handler body as main.ts, so the renderer->main hop is exercised too.
  ipcMain.handle('hotkeys:sync', (_e, next) => {
    const clean = Array.isArray(next)
      ? next.filter((b) => typeof b?.playlist_id === 'number' && typeof b?.accelerator === 'string')
      : [];
    return hotkeys.sync(clean);
  });
  ipcMain.on('device:set', (_e, next) => hotkeys.setDevice(next));

  await win.loadURL(ORIGIN + '/login');
  await win.webContents.executeJavaScript(`
    fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:'bard',password:'pw'})}).then(r=>r.status)`);

  // Have the renderer collect presses that arrive through the real bridge.
  await win.webContents.executeJavaScript(`
    window.__got = [];
    window.bard.onHotkey((id) => window.__got.push(id));
    true;`);

  // --- registration, driven from the page like the app does ---------------
  const result = await win.webContents.executeJavaScript(`
    window.bard.syncHotkeys([
      {playlist_id: 2, accelerator: 'Control+Alt+F8'},
      {playlist_id: 3, accelerator: 'Control+Alt+F9'},
      {playlist_id: 4, accelerator: 'ThisIsNotAKey'}
    ])`).catch((e) => 'IPC ERROR ' + e.message);
  // The renderer's invoke goes to ipcMain in main.js, which is not loaded in
  // this probe, so drive the same call directly to prove the module half.
  const direct = hotkeys.sync([
    { playlist_id: 2, accelerator: 'Control+Alt+F8' },
    { playlist_id: 3, accelerator: 'Control+Alt+F9' },
    { playlist_id: 4, accelerator: 'ThisIsNotAKey' },
  ]);
  rec('renderer invoke reached main', JSON.stringify(result));
  rec('registered', JSON.stringify(direct.registered));
  rec('failed (bogus rejected, app alive)', JSON.stringify(direct.failed));
  rec('OS really holds them', globalShortcut.isRegistered('Control+Alt+F8'));
  rec('bindings kept', direct.registered.length === hotkeys.bindings.length);

  // --- routing: browser device --------------------------------------------
  hotkeys.setDevice('browser');
  hotkeys.press(2);
  await new Promise((r) => setTimeout(r, 250));
  rec('browser: went to renderer', JSON.stringify(sent));
  rec('browser: did NOT hit server', triggered.length === 0);
  rec('renderer received via preload', await win.webContents.executeJavaScript('JSON.stringify(window.__got)'));

  // --- routing: voice device ----------------------------------------------
  hotkeys.setDevice('voice');
  hotkeys.press(3);
  await new Promise((r) => setTimeout(r, 250));
  rec('voice: went to server', JSON.stringify(triggered));
  rec('voice: renderer untouched', sent.length === 1);

  // --- expired session bubbles up -----------------------------------------
  serverOk = false;
  hotkeys.press(3);
  await new Promise((r) => setTimeout(r, 250));
  rec('401 raises onUnauthorized', unauthorized === 1);

  // --- clear releases the OS grabs ----------------------------------------
  hotkeys.clear();
  rec('clear released OS grab', !globalShortcut.isRegistered('Control+Alt+F8'));
  rec('device coercion (garbage -> browser)', (hotkeys.setDevice({}), hotkeys.device));

  // --- hostile input from the renderer (it is remote content) --------------
  hotkeys.sync([{ playlist_id: 2, accelerator: 'Control+Alt+F8' }]);
  rec('setDevice over IPC', await (async () => {
    await win.webContents.executeJavaScript(`window.bard.setDevice('voice'); true`);
    await new Promise((r) => setTimeout(r, 200));
    return hotkeys.device;
  })());
  rec('malformed payload survives', JSON.stringify(
    await win.webContents.executeJavaScript(
      `window.bard.syncHotkeys([{nope:1}, 'garbage', null])`)));
  rec('malformed sync released old grabs', !globalShortcut.isRegistered('Control+Alt+F8'));

  const w = Math.max(...out.map(([k]) => k.length));
  for (const [k, v] of out) console.log(`RESULT ${k.padEnd(w)}  ${v}`);
  app.exit(0);
}).catch((e) => { console.log('PROBE ERROR', e); app.exit(1); });
