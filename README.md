# Bard — D&D Management Bot

Discord bot for managing D&D games: create games (category + channels + role), add/remove players, and send scheduling poll reminders — plus a music player that builds a YouTube library, organises it into tagged playlists, and shuffles them into voice chat for a session.

## Quick start (Docker)

1. Copy `.env.example` to `.env` and set `DISCORD_TOKEN` (and optionally `GUILD_ID` for instant slash commands).
2. Run:
   ```bash
   docker compose up -d
   ```
3. Invite the bot to your server with scope `applications.commands` and `bot`, and permissions: Manage Channels, Manage Roles, View Channels, Send Messages, Read Message History, Connect, Speak.
4. Set `WEB_PASSWORD` in `.env` — the web player refuses to start without it (see [Web login](#web-login)).
5. Open the web player at `http://<host>:5000` (set `WEB_PORT=0` in `.env` to disable it) and sign in.

## Commands

- **`/create-game <name>`** — Create a new game (you become the DM). Use in any channel.
- **`/delete-game <name>`** — Delete a game (DM only). Use **outside** the game’s channels. Confirmation via buttons.
- **`/game add-player <user>`** — Add a player (DM only). Use in the game’s important, scheduling, or general channel.
- **`/game remove-player <user>`** — Remove a player (DM only). Same channels.
- **`/schedule remind`** — DM all players who haven’t voted on the latest poll in the scheduling channel (DM only, in a game text channel).

### Music

- **`/music play <playlist>`** — Play a playlist in **your** voice channel. Shuffles by default (`shuffle: False` plays in order). The playlist name autocompletes, and typing a tag matches too.
- **`/music playlists [tag]`** — List playlists, optionally filtered by tag.
- **`/music add <url>`** — Import a YouTube video, or an entire YouTube playlist, into the library.
- **`/music now`** — Current track, position, and what’s up next.
- **`/music pause` · `resume` · `skip` · `shuffle` · `volume` · `stop`** — Playback controls.

## Scheduling

- The DM (or anyone) creates a **native Discord poll** in the game’s **scheduling** channel.
- The bot automatically sends a reminder to **players** who haven’t voted at the **halfway point** of the poll.
- The DM can also run **`/schedule remind`** anytime to send reminders on demand.

## Music

The web player at port `5000` is the main way to manage music; the slash commands above cover playback during a session.

- **Library** — paste a YouTube URL to import it. Paste a *playlist* URL and every video in it is imported at once. This is your "liked songs": everything you have saved, in one list.
- **Playlists** — group library tracks into playlists, give each a cover image and space-separated **tags** (e.g. `epic battle combat`).
- **Tags** — tag pills appear on the playlists page. Click one to filter; click several to narrow further; the search box matches names *and* tags.
- **Shuffle Play** — the green button on any playlist card or its detail page shuffles the playlist and starts it. Every pass through the playlist gets a fresh shuffle.
- **Devices** — the speaker picker in the player bar switches between **Browser** (audio plays in your tab) and any **voice channel** the bot can join. Whoever is driving owns the queue: switching to voice hands playback to the bot, and it hands back if the bot leaves.

Playback in voice needs `ffmpeg`, which the Docker image already installs.

## Web login

Everything the web player serves — the UI, the whole `/api/*` surface, the audio proxy, and playlist covers — sits behind a single shared login, so the port is safe to put behind a tunnel.

| Variable | Default | What it does |
| --- | --- | --- |
| `WEB_PASSWORD` | *(none)* | The password. **Required** — the web player refuses to start without it. |
| `WEB_USERNAME` | `bard` | The username to sign in with. |
| `WEB_SECRET_KEY` | *(random)* | Signs session cookies. Unset means a fresh key each restart, which signs every browser out. Generate one with `openssl rand -hex 32`. |
| `WEB_AUTH` | `on` | `off` serves the UI with **no login at all**. Trusted LAN only. |
| `WEB_COOKIE_SECURE` | `auto` | `auto` marks the cookie `Secure` when the request arrives over HTTPS (including via `X-Forwarded-Proto`), so plain-HTTP LAN access still works. |

Sessions are a signed, HttpOnly, SameSite=Lax cookie that expires after 30 days; nothing is stored server-side. Sign out from the sidebar. Eight failed logins from one address locks that address out for 15 minutes.

## Building the web UI

The player is a Vue app in `web-src/`; `web/` holds its **build output** and is what
the bot serves and the Docker image copies. Editing files in `web/` directly means
losing them on the next build.

```bash
cd web-src
npm install
npm run build      # writes web/index.html, web/login.html and web/assets/
```

| Script | What it does |
| --- | --- |
| `npm run dev` | Vite dev server, proxying `/api`, `/covers` and `/login` to a bot already running on `:5000`. |
| `npm run build` | Builds the player *and* the login page. Run this before `docker compose build`. |
| `npm run typecheck` | `vue-tsc` over the whole app. |

Two builds, because `/login` is the one path served without a session: a login page
that fetched `/assets/*.js` would be redirected to itself, so `vite.login.config.ts`
inlines everything into a single `login.html`. Everything else is hashed chunks
under `/assets`, behind the same cookie as the rest of the site.

Two pins are deliberate. `typescript` stays on 5.x because `vue-tsc` cannot drive
the 7.x native compiler. `primevue` and `primeicons` stay on 4.x / 7.x because
from PrimeVue 5 and primeicons 8 onward they are commercially licensed and paint
an "Invalid PrimeUI License" badge over the UI without a key; the 4.x line is MIT.

## Desktop app and playlist shortcuts

`desktop/` is a small Electron shell around the same web player. It exists for
one reason: a page in a browser cannot claim a key combination that fires while
another application has focus, and a desktop app can. Mid-session you can switch
the music without leaving whatever you are looking at.

```bash
cd desktop
npm install
npm start          # compiles and launches
```

On first run it asks for the bot's address (`192.168.1.158:5000` is enough —
`http://` is assumed), then loads the ordinary web UI and its login page. It
does **not** bundle a copy of the front-end, so a `npm run build` in `web-src/`
is picked up on the next launch with no desktop release.

Bind shortcuts under **Settings → Playlist shortcuts**. One combination per
playlist; pressing it plays that playlist, pressing it again pauses, again
resumes. Binding a combination that is already in use moves it. Bindings are
stored on the server, not on the machine, so they follow the login.

Closing the window hides it to the tray — the shortcuts need a live process.
Quit from the tray menu, which is also where you can point it at a different
server.

### Where a press goes

It follows the device picker in the player bar, so a shortcut does exactly what
clicking the playlist would. On **Discord** the shell calls the server and the
bot plays it, which works with the window hidden. On **Browser** the press is
forwarded to the window, because the audio element lives there.

| Route | Endpoint |
| --- | --- |
| List / bind / clear | `GET`, `PUT`, `DELETE /api/hotkeys[/{playlist_id}]` |
| Toggle one playlist | `POST /api/hotkeys/trigger` |

All four sit behind the session cookie like everything else — `auth_middleware`
exempts only `/login`, `/api/login` and `/api/logout`. The shell needs no
separate credential: it reuses the cookie from the window you signed in with.

### If shortcuts do not fire

On X11 an application grabs keys directly. On Wayland it cannot, and has to ask
the compositor through `xdg-desktop-portal`; the app enables Chromium's
`GlobalShortcutsPortal` for this, but a compositor with no GlobalShortcuts
portal backend will accept a registration and then never deliver the key.
`cd desktop && npm run probe:platform` reports what the API says on your
session, and `desktop/probe/README.md` explains how to read it.

## Exposing it with cloudflared

Point the tunnel's ingress at the container's port:

```yaml
ingress:
  - hostname: music.example.com
    service: http://localhost:5000
  - service: http_status:404
```

Then reload cloudflared so it picks up the change:

```bash
sudo systemctl reload cloudflared     # or: sudo systemctl restart cloudflared
# running in Docker instead:
docker restart cloudflared
```

Once it is reachable from the internet, set a long `WEB_PASSWORD` and a fixed `WEB_SECRET_KEY`, and consider narrowing the published port in `docker-compose.yml` to `127.0.0.1:5000:5000` so only the tunnel can reach it. Cloudflare Access in front of the hostname is a good second layer, but this login stands on its own without it.

## Data

- SQLite database is stored in the `bard_data` Docker volume (or `./data/bard.db` if run locally). Back up this volume to keep your games.

## Plan

See `DND_BOT_PLAN.md` for the full design.
