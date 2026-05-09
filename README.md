# Bard — D&D Management Bot

Discord bot for managing D&D games: create games (category + channels + role), add/remove players, and send scheduling poll reminders.

## Quick start (Docker)

1. Copy `.env.example` to `.env` and set `DISCORD_TOKEN` (and optionally `GUILD_ID` for instant slash commands).
2. Run:
   ```bash
   docker compose up -d
   ```
3. Invite the bot to your server with scope `applications.commands` and `bot`, and permissions: Manage Channels, Manage Roles, View Channels, Send Messages, Read Message History, Connect.

## Commands

- **`/create-game <name>`** — Create a new game (you become the DM). Use in any channel.
- **`/delete-game <name>`** — Delete a game (DM only). Use **outside** the game’s channels. Confirmation via buttons.
- **`/game add-player <user>`** — Add a player (DM only). Use in the game’s important, scheduling, or general channel.
- **`/game remove-player <user>`** — Remove a player (DM only). Same channels.
- **`/schedule remind`** — DM all players who haven’t voted on the latest poll in the scheduling channel (DM only, in a game text channel).

## Scheduling

- The DM (or anyone) creates a **native Discord poll** in the game’s **scheduling** channel.
- The bot automatically sends a reminder to **players** who haven’t voted at the **halfway point** of the poll.
- The DM can also run **`/schedule remind`** anytime to send reminders on demand.

## Data

- SQLite database is stored in the `bard_data` Docker volume (or `./data/bard.db` if run locally). Back up this volume to keep your games.

## Plan

See `DND_BOT_PLAN.md` for the full design.
