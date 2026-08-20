# Probes

Not unit tests — small Electron programs that check the platform behaviour the
shell depends on. They open no visible window.

| Probe | Needs a bot? | Checks |
| --- | --- | --- |
| `platform.js` | no | Whether `globalShortcut` can claim a combination on this desktop session. Run it first when shortcuts do not fire. |
| `setup.js` | no | Server-address parsing, the config file round-trip, and the first-run page. |
| `probe.js` | yes | That the preload reaches remotely-loaded pages, withholds itself from other origins, and that `session.fetch` carries the login cookie. |
| `routing.js` | yes | The whole loop: renderer → `syncHotkeys` → registration → press → renderer or server, by device. |

The two that need a bot expect one on `http://127.0.0.1:5198` with
`WEB_USERNAME=bard` / `WEB_PASSWORD=pw`, and a second on `:5199` for the
cross-origin check.

```bash
npm run probe:platform     # the useful one for diagnosing dead shortcuts
npx electron probe/setup.js --no-sandbox
```

## Why `platform.js` matters

On X11 an application grabs keys directly and this all just works. On Wayland it
cannot: Chromium has to ask the compositor through `xdg-desktop-portal`, which
`main.ts` enables with the `GlobalShortcutsPortal` feature flag. Compositors
whose portal has no GlobalShortcuts backend will let a shortcut *register* and
then never fire it — so `register=true` from this probe means the API accepted
it, not that your compositor will deliver the key.
