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
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_ready():
    await init_db()
    guild_id = os.environ.get("GUILD_ID")
    if guild_id:
        guild = discord.Object(id=int(guild_id))
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    else:
        await bot.tree.sync()
    # Ensure all existing games have correct channel permissions (commented out; only new game creation sets perms)
    # games_cog = bot.get_cog("GamesCog")
    # if games_cog is not None and hasattr(games_cog, "sync_all_game_permissions"):
    #     await games_cog.sync_all_game_permissions()
    # Start poll reminder scheduler after DB exists
    scheduling_cog = bot.get_cog("SchedulingCog")
    if scheduling_cog is not None and hasattr(scheduling_cog, "_start_poll_reminder_scheduler"):
        asyncio.create_task(scheduling_cog._start_poll_reminder_scheduler())
    # Start media player web UI (optional: set WEB_PORT=0 to disable)
    web_port = int(os.environ.get("WEB_PORT", "5000"))
    if web_port > 0:
        web_host = os.environ.get("WEB_HOST", "0.0.0.0")
        asyncio.create_task(run_web_server(host=web_host, port=web_port))
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")


async def main():
    async with bot:
        await bot.add_cog(GamesCog(bot))
        await bot.add_cog(SchedulingCog(bot))
        await bot.add_cog(VoiceNickCog(bot))
        await bot.start(os.environ["DISCORD_TOKEN"])


if __name__ == "__main__":
    asyncio.run(main())
