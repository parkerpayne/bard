const { app, globalShortcut } = require('electron');
app.commandLine.appendSwitch('disable-gpu');
if (process.platform === 'linux') app.commandLine.appendSwitch('enable-features', 'GlobalShortcutsPortal');
app.whenReady().then(() => {
  let ok = false, err = '';
  try { ok = globalShortcut.register('Control+Alt+Shift+F10', () => {}); }
  catch (e) { err = String(e.message || e).slice(0, 60); }
  console.log(`RESULT platform=${process.env.PROBE_LABEL} register=${ok} isRegistered=${globalShortcut.isRegistered('Control+Alt+Shift+F10')} ${err}`);
  globalShortcut.unregisterAll();
  app.exit(0);
});
