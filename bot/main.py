"""Bard D&D management bot — entry point."""
import asyncio
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from bot.db import init_db, async_session_factory
from bot.cogs.games import GamesCog
from bot.cogs.music import MusicCog
from bot.cogs.scheduling import SchedulingCog
from bot.cogs.voice_nicks import VoiceNickCog
from bot.web_server import run_web_server

load_dotenv()

# Logging: INFO shows voice_nick events; set LOG_LEVEL=DEBUG to see "not a game voice" skips
logging.basicConfig(
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
)
log = logging.getLogger("bard")

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.members = True
intents.voice_states = True  # required for on_voice_state_update (game voice nicknames)

bot = commands.Bot(command_prefix="/", intents=intents)


@bot.tree.command(name="help", description="List all commands and how to use the bot")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Bard — D&D management bot",
        description="Commands for creating games, managing players, and scheduling.",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="/create-game <name>",
        value="Create a new game. You become the DM. Use in any channel.",
        inline=False,
    )
    embed.add_field(
        name="/delete-game <name>",
        value="Delete a game (DM only). **Use outside** the game's channels. You'll get a confirmation button.",
        inline=False,
    )
    embed.add_field(
        name="/game add-player <user>",
        value="Add a player (DM only). Use **inside** the game's important, scheduling, or general channel.",
        inline=False,
    )
    embed.add_field(
        name="/game remove-player <user>",
        value="Remove a player (DM only). Same channels as add-player.",
        inline=False,
    )
    embed.add_field(
        name="/game info",
        value="List the DM and players for this game. Use in any game text channel.",
        inline=False,
    )
    embed.add_field(
        name="/game transfer <user>",
        value="Transfer game ownership to another member (current DM only). They become DM; you become a player.",
        inline=False,
    )
    embed.add_field(
        name="/game set-nickname <name>",
        value="Set your game-specific character name (DM or player). Use in a game text channel. Shown in /game info.",
        inline=False,
    )
    embed.add_field(
        name="/game remove-nickname",
        value="Remove your game character name. Use in a game text channel.",
        inline=False,
    )
    embed.add_field(
        name="/schedule remind",
        value="DM all players who haven't voted on the latest poll in the scheduling channel (DM only, in a game text channel). The bot also reminds automatically at the halfway point when someone creates a poll.",
        inline=False,
    )
    embed.add_field(
        name="\u200b",
        value="**Music** — build a library and play it in voice chat.",
        inline=False,
    )
    embed.add_field(
        name="/music play <playlist>",
        value="Play a playlist in **your** voice channel. Shuffles by default; pass `shuffle: False` for stored order.",
        inline=False,
    )
    embed.add_field(
        name="/music playlists [tag]",
        value="List playlists, optionally filtered by tag (e.g. `tag: battle`).",
        inline=False,
    )
    embed.add_field(
        name="/music add <url>",
        value="Import a YouTube video — or a whole YouTube playlist — into the library.",
        inline=False,
    )
    embed.add_field(
        name="/music pause · resume · skip · shuffle · volume · now · stop",
        value="Playback controls. `/music now` shows the current track and what's up next.",
        inline=False,
    )
    web_port = os.environ.get("WEB_PORT", "5000")
    if web_port != "0":
        embed.set_footer(text=f"Web player (playlists, tags, covers) runs on port {web_port}.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# on_ready fires again on every reconnect. Startup work must happen once, or
# the second run tries to re-bind the web port and re-arms the scheduler.
_startup_complete = False


@bot.event
async def on_ready():
    global _startup_complete
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    if _startup_complete:
        log.info("Reconnected; startup already done.")
        return
    _startup_complete = True

    # Each phase is isolated: a failure in one must not silently take down the
    # rest. Losing the web UI because a migration hiccuped is how you end up
    # with a bot that answers /help while port 5000 refuses connections.
    try:
        await init_db()
    except Exception:
        log.exception("Database init failed — the API will not work until this is fixed")

    try:
        guild_id = os.environ.get("GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
        else:
            synced = await bot.tree.sync()
        log.info("Synced %d slash commands", len(synced))
    except Exception:
        log.exception("Slash command sync failed")

    try:
        scheduling_cog = bot.get_cog("SchedulingCog")
        if scheduling_cog is not None and hasattr(scheduling_cog, "_start_poll_reminder_scheduler"):
            asyncio.create_task(scheduling_cog._start_poll_reminder_scheduler())
    except Exception:
        log.exception("Poll reminder scheduler failed to start")

    # Start the media player web UI (set WEB_PORT=0 to disable).
    try:
        web_port = int(os.environ.get("WEB_PORT", "5000"))
    except ValueError:
        web_port = 5000
    if web_port > 0:
        web_host = os.environ.get("WEB_HOST", "0.0.0.0")
        try:
            await run_web_server(host=web_host, port=web_port, bot=bot)
            log.info("Web player listening on %s:%d", web_host, web_port)
        except OSError as exc:
            log.error("Could not bind the web player to %s:%d — %s", web_host, web_port, exc)
        except Exception:
            log.exception("Web player failed to start")
    else:
        log.info("Web player disabled (WEB_PORT=0)")


async def main():
    async with bot:
        await bot.add_cog(GamesCog(bot))
        await bot.add_cog(MusicCog(bot))
        await bot.add_cog(SchedulingCog(bot))
        await bot.add_cog(VoiceNickCog(bot))
        await bot.start(os.environ["DISCORD_TOKEN"])


if __name__ == "__main__":
    asyncio.run(main())
