const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('node:path');
const cfg = require('../dist/config.js');
const out = [];
const rec = (k, v) => out.push([k, v]);
app.commandLine.appendSwitch('disable-gpu');

app.whenReady().then(async () => {
  for (const [input, want] of [
    ['192.168.1.158:5000', 'http://192.168.1.158:5000'],
    ['  bard.example.com  ', 'http://bard.example.com'],
    ['https://music.example.com/', 'https://music.example.com'],
    ['http://h:5000/some/path?x=1', 'http://h:5000'],
    ['', null],
    ['   ', null],
    ['ht!tp://%%%', null],
    ['ht!tp', null],
    ['has space.com', null],
    ['-leadinghyphen.com', null],
    ['[::1]:5000', 'http://[::1]:5000'],
    ['ftp://nope.com', null],
    ['bard.local:5000', 'http://bard.local:5000'],
  ]) {
    rec(`normalise ${JSON.stringify(input)}`, JSON.stringify(cfg.normaliseServerUrl(input)));
    if (cfg.normaliseServerUrl(input) !== want) rec('  ^ MISMATCH, wanted', JSON.stringify(want));
  }

  // Round-trip through the real file on disk.
  cfg.save({ serverUrl: 'http://127.0.0.1:5198' });
  rec('config round-trips', JSON.stringify(cfg.load()));
  require('node:fs').writeFileSync(
    path.join(app.getPath('userData'), 'config.json'), '{ not json', 'utf8');
  rec('corrupt config -> first run', JSON.stringify(cfg.load()));

  // The bundled setup page and its own bridge.
  let saved = null;
  ipcMain.handle('setup:get', () => 'http://127.0.0.1:5198');
  ipcMain.handle('setup:save', (_e, raw) => {
    const url = cfg.normaliseServerUrl(String(raw ?? ''));
    if (!url) return { ok: false, message: 'That does not look like an address.' };
    saved = url;
    return { ok: true };
  });

  const win = new BrowserWindow({
    show: false,
    webPreferences: {
      preload: path.join(__dirname, '..', 'dist', 'setup-preload.js'),
      contextIsolation: true,
      sandbox: true,
    },
  });
  await win.loadFile(path.join(__dirname, '..', 'static', 'setup.html'));
  await new Promise((r) => setTimeout(r, 400));

  rec('setup page title', await win.webContents.executeJavaScript('document.title'));
  rec('prefilled from config', await win.webContents.executeJavaScript('document.getElementById("u").value'));
  rec('no app bridge on setup page', await win.webContents.executeJavaScript('!window.bard'));

  await win.webContents.executeJavaScript(`
    document.getElementById('u').value = 'nope!!!%%';
    document.getElementById('f').dispatchEvent(new Event('submit',{cancelable:true}));`);
  await new Promise((r) => setTimeout(r, 300));
  rec('bad address -> error shown', await win.webContents.executeJavaScript('document.getElementById("e").textContent'));

  await win.webContents.executeJavaScript(`
    document.getElementById('u').value = '10.0.0.5:5000';
    document.getElementById('f').dispatchEvent(new Event('submit',{cancelable:true}));`);
  await new Promise((r) => setTimeout(r, 300));
  rec('good address saved as', String(saved));

  const w = Math.max(...out.map(([k]) => k.length));
  for (const [k, v] of out) console.log(`RESULT ${k.padEnd(w)}  ${v}`);
  app.exit(0);
}).catch((e) => { console.log('PROBE ERROR', e); app.exit(1); });
