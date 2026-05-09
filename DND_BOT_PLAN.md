# Discord D&D Management Bot — Plan

## Overview

A Discord bot that lets users create and manage “games” (D&D campaigns). Each game gets its own category with restricted access; the creator is the Dungeon Master (DM) and has full control over that game’s channels and membership.

---

## 1. Core Concepts

| Term | Meaning |
|------|--------|
| **Game** | A campaign. Has a name, one DM, and a set of players. |
| **DM** | Dungeon Master. The user who created the game. Full control over that game’s category and channels. |
| **Player** | A user added to the game by the DM. Has access to the game category (except DM-only channels). |
| **Category** | A Discord category named after the game. All game channels live under it. Only the DM and players have access. |

---

## 2. Game Creation

### Trigger
- **Slash command** `/create-game <name>`. Available in any channel in the guild (no game context needed).

### What happens
1. **Validation**
   - Game name: length, allowed characters, no duplicate name in the guild.

2. **Category**
   - Create a category with the **game name exactly** (e.g. `Curse of Strahd`).
   - Permissions:
     - **@everyone**: View Channel = OFF (no access by default).
     - **DM (role or user overwrite)**: View Channel = ON, Manage Channel = ON, all other needed permissions.
     - **“Game members”**: Implemented via a **role per game** (e.g. `Game: Curse of Strahd`) given to DM + all players, with View Channel = ON for the category and children.

3. **Channels under the category**

   (Created in this order so they appear top-to-bottom.)

   | Order | Type | Name | Who can access |
   |-------|------|------|----------------|
   | 1 | Text | `important` | **DM only** |
   | 2 | Text | `scheduling` | All members |
   | 3 | Text | `general` | All members |
   | 4 | Voice | `game` | All members |
   | 5 | Voice | `private` | **Only DM** can join; DM can drag others in. |

4. **Permission details**
   - **Category**: Inherit for children; only game role sees the category.
   - **private** (voice): Game role has View Channel so they can be dragged in; only DM has Connect.
   - **important** (text): Only DM has View Channel and Read Message History.
   - **scheduling** and **general** (text): Game role has normal read/send.

5. **State to store**
   - Game ID (or category ID as id).
   - Guild ID.
   - Game name.
   - DM user ID.
   - List of player user IDs (or role ID for the game role).
   - Category ID, channel IDs (for cleanup and permission updates).

Storage: database (SQLite/PostgreSQL) or JSON file; recommend DB for multiple guilds and safety.

---

## 3. Game Deletion

### Trigger
- **Slash command** `/delete-game <name>`. Available only **outside** game channels. Requires the **game name**. DM only.

### Flow
1. **Check**: Requester is the DM for the named game.
2. **Confirmation**: Bot sends a message with **buttons**: "Delete game" and "Cancel". Text e.g.  
   “Delete game **Curse of Strahd**? All channels will be removed. Reply with `confirm` or use a button (e.g. “Delete game” / “Cancel”) within 60 seconds.”
3. **On confirm** (user clicks "Delete game"):
   - Delete all channels in the category (voice and text).
   - Delete the category.
   - Optionally delete the game role.
   - Remove game from storage.
4. **On cancel / timeout**: Do nothing; optionally delete the confirmation message.

---

## 4. Add / Remove Players

**Where these run**: `/game add-player`, `/game remove-player`, and `/schedule remind` must be run **inside one of that game's text channels** (important, scheduling, or general). The bot infers the game from the channel. If run outside a game channel, the command fails or is not available.

### Add player
- **Command**: `/game add-player <user>`.
- **Check**: Run in a game text channel; requester is the DM of that game.
- **Action**: Add the user to the game’s member list and assign them the game role.

### Remove player
- **Command**: `/game remove-player <user>`.
- **Check**: Run in a game text channel; requester is the DM.
- **Action**: Remove the user from the game’s member list and remove the game role.

### Edge cases
- Cannot remove the DM (or treat “leave game” separately for DM and only allow transfer or delete).
- Adding a user who is already a player: idempotent (no error, or “already in game” message).
- Removing a user not in the game: “they are not in this game.”

---

## 5. Scheduling (Reminders Only)

The bot **does not create polls**. The DM (or anyone) creates a **native Discord poll** in the game's scheduling channel (Discord's built-in poll UI). The bot's only job: **send reminders to players who haven't voted** (DM is assumed available; only **players** get reminded).

### 5.1 Assumption

- Any **poll message** in a game's scheduling channel is treated as a scheduling poll for that game.
- The bot never creates or edits the poll; it only finds it and uses it for reminders.

### 5.2 Detecting new polls and scheduling automatic reminder

- **On every new message** in a channel that is a game's scheduling channel (Message Create event): check if the message has a `poll` object.
- **If it is a poll**: Read `poll.expiry` (end time). Compute the **halfway point** = message creation time + (expiry − creation time) / 2. Store the poll in the DB (game_id, channel_id, message_id, expiry, reminder_at = halfway). Schedule a one-off task (or use a scheduler loop) to run at `reminder_at`.
- **At the halfway point**: Run the same logic as on-demand remind (get voters, DM non-voters with link). Remind **players only** (not the DM). Mark that reminder was sent for this poll so we don't remind again.

### 5.3 On-demand remind

- **Trigger**: DM runs `/schedule remind` in the scheduling channel (or another of that game's text channels). Bot finds the latest poll in the scheduling channel and sends reminders to players who haven't voted.
- **Link**: `https://discord.com/channels/<guild_id>/<channel_id>/<message_id>` so recipients can jump straight to the poll.
- **Who voted**: Use Discord's Get Answer Voters API for each answer; union the user IDs. Anyone in the game's **player** list (from DB; exclude DM) who is not in that set gets a DM.
- **DM text**: e.g. *"You haven't voted on the session scheduling for **{Game Name}**. Please vote here: {link}."*
- If a user has DMs disabled, report e.g. "Could not DM: @User" to the DM (ephemeral or in channel).

### 5.4 Finding the poll (for on-demand or scheduled run)

- Fetch recent messages in the scheduling channel; find the most recent message with a `poll` object (and optionally where `poll.expiry` > now for open polls). Use that message. For automatic reminders we already have the poll stored (SchedulePoll) with message_id.

### 5.5 Edge cases

- **No poll in channel**: Reply with "No scheduling poll found in this channel. Create a poll here first."
- **Poll already expired**: Still allow remind (link may show results); or only remind for open polls (expiry > now).
- **Multiple polls**: For on-demand, use the **latest**. For automatic, each new poll message gets its own SchedulePoll row and reminder at its halfway point.
- **Channel or message deleted**: Fail gracefully; skip or mark SchedulePoll invalid.
- **DMs disabled**: Bot can't DM that user; report to DM.

### 5.6 Data model (scheduling)

- **SchedulePoll** table: id, game_id, channel_id, message_id, expiry (poll end time), reminder_at (halfway point), reminder_sent (boolean), created_at. When a new message with a poll is created in a scheduling channel, insert a row and schedule the reminder task. When the task runs, set reminder_sent = true after sending DMs.

---

## 6. Command Summary (Suggested)

| Command | Who | Description |
|--------|-----|-------------|
| `/create-game <name>` | Any | Create game; requester becomes DM. |
| `/delete-game <name>` | DM only | Request deletion (game name required); use outside game channels; button confirm. |
| `/game add-player <user>` | DM only | Add player to the game. |
| `/game remove-player <user>` | DM only | Remove player from the game. |
| `/schedule remind` | DM only | Find latest poll; DM players who haven't voted (only in game text channels). |

Optional later:
- `/game list` — list games in the server (or “your games”).
- `/game info` — show DM, player list, channel links.
- DM transfer (e.g. `/game set-dm <user>`).
- Automatic reminder before poll expiry (if scheduler available).

---

## 7. Permission Model (Discord)

- **Bot permissions** (server-wide): Manage Channels, Manage Roles, View Channels, Connect (for voice), Create Instant Invite.
- **Per-category**: @everyone denied; game role allowed (View + use channels as needed).
- **Per-channel overwrites**:
  - **private** (voice): DM = Connect + View; game role = View only (so members can be dragged in but only DM joins by default).
  - **important** (text): Only DM = View + Read History; game role = no access.

Implement “only DM can join” by giving only the DM the “Connect” permission on that voice channel; “drag” still works when the DM has Move Members (or the channel is visible to the dragged user in some implementations). Confirm in Discord’s docs that “drag into voice” works with your overwrites.

---

## 8. Data Model (Logical)

```
Game
  - id (uuid or snowflake)
  - guild_id
  - name
  - dm_user_id
  - category_id
  - game_role_id
  - voice_game_id       # channel named "game"
  - voice_private_id    # channel named "private"
  - text_important_id
  - text_general_id
  - text_scheduling_id
  - created_at

SchedulePoll
  - id, game_id, channel_id, message_id, expiry, reminder_at, reminder_sent, created_at

Player (or GameMember)
  - game_id
  - user_id
  - added_at
```

Alternatively, store only `game_id`, `guild_id`, `dm_user_id`, `category_id`, `game_role_id` and derive channel layout by convention (e.g. channel names); then you can recreate channel list by scanning category children. Trade-off: simpler schema vs. explicit IDs for each channel.

---

## 9. Tech Stack Suggestions

- **Language**: **discord.py** (Python).
- **Storage**: SQLite. Use an ORM (e.g. SQLAlchemy) for games, players, and SchedulePoll. DB in Docker volume (see §10).
- **Slash commands**: **Per-guild** registration (instant). Docker-only run.

---

## 10. Docker + SQLite (Portable Deployment)

Run the bot and its SQLite database in Docker so the whole setup is portable: copy the project (or image + volume) to another machine and run the same way.

### 10.1 What to add

- **Dockerfile**: Builds the bot (install deps, copy code, set entrypoint to run the bot process). No separate DB container—SQLite is a file; the bot process reads/writes it.
- **docker-compose.yml** (or `compose.yaml`): One service (the bot). Mount a **volume** for the directory where the SQLite file lives (e.g. `./data` or `/app/data` inside the container) so the database persists across container restarts and can be backed up or moved.
- **Environment**: Bot token and config via env (e.g. `DISCORD_TOKEN`). Use an `.env` file (add `.env` to `.gitignore`) or pass env in compose; do not bake the token into the image.
- **.dockerignore**: Exclude `node_modules` / `__pycache__`, `.env`, `.git`, and the SQLite file so the DB lives only in the volume.

### 10.2 Layout (suggested)

```
bardBot/
  Dockerfile
  docker-compose.yml
  .env.example          # DISCORD_TOKEN= (no real token)
  .dockerignore
  src/ or bot/          # app code
  data/                 # created at runtime; mount as volume (sqlite file here)
```

- **SQLite path**: Use a path inside the container that is the volume mount (e.g. `/app/data/bard.db`). In compose, mount a named volume or host path onto that directory.

### 10.3 docker-compose outline

- **Service**: e.g. `bot`. Build from Dockerfile; no published ports needed (bot only does outbound Discord API).
- **Volume**: Map a volume to the container path that holds the SQLite file so data persists.
- **Env**: Pass `DISCORD_TOKEN` via `environment` or `env_file: .env`.
- **Restart**: `restart: unless-stopped` so the bot comes back after crashes or host reboot.

### 10.4 Usage (target)

- **Run**: `docker compose up -d` (or `docker-compose up -d`).
- **First time**: Create `.env` from `.env.example`, set `DISCORD_TOKEN`, then `docker compose up -d`.
- **Portability**: To move, copy the project plus the volume (or the `data/` directory if using a bind mount). On the new machine, set `.env` and run `docker compose up -d` again.

### 10.5 Optional

- **Non-root user**: Run the container as a non-root user if the image supports it.
- **Healthcheck**: Add a `healthcheck` in compose if the bot can expose liveness (optional).

---

## 11. Edge Cases & Safety

- **Name collisions**: Ensure category name is unique in the guild (or add a suffix, e.g. `GameName (D&D)`).
- **Bot role hierarchy**: Bot’s role must be above the game role and any channels it creates so it can assign the role and manage channels.
- **Missing channels**: If someone deletes a channel manually, have a way to detect (e.g. on command use) and either recreate or mark game as broken and allow DM to run “repair” or “delete game.”
- **DM leaves server**: Decide policy (e.g. game becomes orphaned until an admin runs an “assign new DM” or “delete game” command).
- **Rate limits**: Creating many channels at once; space creation out if needed to avoid Discord rate limits.

---

## 12. Implementation Order (When You Build It)

1. Bot skeleton: connect, slash command registration, guild-only checks.
2. Persistence: create Games and Players tables; link to guild/category/role/channels.
3. Create game: category (game name) + role (`Game: [name]`) + 5 channels **in order** (important, scheduling, general, game, private) + permission overwrites; save to DB.
4. Add/remove player: only in game text channels; update DB and assign/remove game role.
5. Delete game: `/delete-game <name>` (outside game channels); **button** confirmation; then delete channels, category, role, and DB record.
6. **Scheduling**: SchedulePoll table. On Message Create in a scheduling channel, if message has poll → store poll, compute halfway point, schedule reminder task. At halfway (and on `/schedule remind`): Get Answer Voters, DM **players** who haven't voted with link. On-demand remind only in game text channels.
7. Polish: error messages, game-not-found / not-DM checks, name validation.
8. **Docker**: Dockerfile, docker-compose.yml with volume for SQLite, .env for token, .dockerignore. Run with `docker compose up -d`.

---

This plan gives you a clear shape for the bot without implementation. When you’re ready to implement, you can start with one guild and SQLite, then expand to more guilds and a stronger DB if needed.
