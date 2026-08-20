/**
 * Verifies the three things the shell depends on, using the REAL preload.js:
 *   1. contextBridge exposure into a remotely-loaded page (and its origin guard)
 *   2. globalShortcut.register on this desktop session
 *   3. session.fetch carrying the login cookie to an authenticated endpoint
 * Window stays hidden; nothing appears on screen.
 */
const { app, BrowserWindow, globalShortcut } = require('electron');
const path = require('node:path');

const ORIGIN = 'http://127.0.0.1:5198';
const out = [];
const rec = (k, v) => { out.push([k, v]); };

app.commandLine.appendSwitch('disable-gpu');

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    show: false,
    webPreferences: {
      preload: path.join(__dirname, '..', 'dist', 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      additionalArguments: [`--bard-origin=${ORIGIN}`],
    },
  });

  // --- 1. preload on remote content ---------------------------------------
  await win.loadURL(ORIGIN + '/login');
  rec('login page loaded', await win.webContents.executeJavaScript('document.title'));
  rec('window.bard exposed on remote page', await win.webContents.executeJavaScript('!!window.bard'));
  rec('bridge keys', await win.webContents.executeJavaScript(
    'window.bard ? Object.keys(window.bard).sort().join(",") : "none"'));
  rec('no raw ipcRenderer leaked', await win.webContents.executeJavaScript(
    'typeof window.require === "undefined" && typeof window.ipcRenderer === "undefined"'));

  // --- 2. globalShortcut on this session -----------------------------------
  let fired = false;
  let ok = false;
  try {
    ok = globalShortcut.register('Control+Alt+Shift+F9', () => { fired = true; });
  } catch (e) {
    rec('register threw', String(e).slice(0, 90));
  }
  rec('globalShortcut.register returned', ok);
  rec('isRegistered', globalShortcut.isRegistered('Control+Alt+Shift+F9'));
  rec('register bogus accelerator', (() => {
    try { return globalShortcut.register('NotAKey+++', () => {}); }
    catch (e) { return 'threw: ' + String(e.message || e).slice(0, 60); }
  })());
  globalShortcut.unregisterAll();
  rec('unregisterAll cleared', !globalShortcut.isRegistered('Control+Alt+Shift+F9'));
  rec('callback fired during probe (expected false)', fired);

  // --- 3. session.fetch + auth cookie --------------------------------------
  const before = await win.webContents.session.fetch(ORIGIN + '/api/hotkeys', {
    credentials: 'include',
  });
  rec('session.fetch /api/hotkeys before login', before.status);

  // Log in through the page, exactly as a user would.
  await win.webContents.executeJavaScript(`
    (async () => {
      const r = await fetch('/api/login', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({username:'bard', password:'pw'})
      });
      return r.status;
    })()`);

  const cookies = await win.webContents.session.cookies.get({ name: 'bard_session' });
  rec('session cookie present in main', cookies.length === 1);

  const after = await win.webContents.session.fetch(ORIGIN + '/api/hotkeys', {
    credentials: 'include',
  });
  rec('session.fetch /api/hotkeys after login', after.status);
  rec('body readable', (await after.text()).slice(0, 40));

  // Bind one, then drive the real trigger endpoint from the main process.
  await win.webContents.executeJavaScript(`
    fetch('/api/hotkeys/2', {method:'PUT', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({accelerator:'Control+Alt+7'})}).then(r=>r.status)`);
  const trig = await win.webContents.session.fetch(ORIGIN + '/api/hotkeys/trigger', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ playlist_id: 2 }),
    credentials: 'include',
  });
  rec('main-process trigger status', trig.status);
  rec('main-process trigger body', (await trig.text()).slice(0, 80));

  // --- 4. origin guard -----------------------------------------------------
  const other = new BrowserWindow({
    show: false,
    webPreferences: {
      preload: path.join(__dirname, '..', 'dist', 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      additionalArguments: [`--bard-origin=${ORIGIN}`],
    },
  });
  await other.loadURL('http://127.0.0.1:5199/login');   // a DIFFERENT origin
  rec('bridge withheld from other origin', await other.webContents.executeJavaScript('!window.bard'));

  const width = Math.max(...out.map(([k]) => k.length));
  for (const [k, v] of out) console.log(`RESULT ${k.padEnd(width)}  ${v}`);
  app.exit(0);
}).catch((e) => { console.log('PROBE ERROR', e); app.exit(1); });
