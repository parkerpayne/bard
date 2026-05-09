"""Temporarily set server nickname to game character name when in game voice channels."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from bot.db import async_session_factory
from bot.utils import get_character_name_for_voice_channel

if TYPE_CHECKING:
    from bot.main import Bot

log = logging.getLogger(__name__)

NICK_MAX_LEN = 32


# (guild_id, user_id) -> nickname to restore (None = user had no server nick; clear it on restore)
_original_nicks: dict[tuple[int, int], str | None] = {}


def _display_nick(character_name: str, original: str) -> str:
    s = f"{character_name} ({original})"
    return s[:NICK_MAX_LEN] if len(s) > NICK_MAX_LEN else s


class VoiceNickCog(commands.Cog):
    """Apply game character names as server nick in game voice channels."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if not member.guild:
            return
        if before.channel == after.channel:
            return
        before_id = before.channel.id if before.channel else None
        after_id = after.channel.id if after.channel else None
        log.info(
            "voice_state_update: %s (id=%s) %s -> %s (guild_id=%s)",
            member.name,
            member.id,
            before_id,
            after_id,
            member.guild.id,
        )
        guild_id = member.guild.id
        user_id = member.id
        key = (guild_id, user_id)
        just_restored: str | None = None

        # Left a channel — restore nickname if we had overridden it (no return: they may have switched to another channel)
        if before.channel is not None and key in _original_nicks:
            just_restored = _original_nicks.pop(key)
            try:
                await member.edit(nick=just_restored)  # None = clear nickname (they had none before)
                log.info("voice_nick: restored nick for %s to %r", member.name, just_restored)
            except discord.Forbidden as e:
                log.warning("voice_nick: restore nick FORBIDDEN (permission/hierarchy) for %s: %s", member.name, e)
            except discord.HTTPException as e:
                log.warning("voice_nick: restore nick HTTP error for %s: %s", member.name, e)

        # Joined or moved to a channel — set nickname if game voice and has character name
        if after.channel is None:
            return
        async with async_session_factory() as session:
            character_name = await get_character_name_for_voice_channel(
                session, guild_id, after.channel.id, user_id
            )
        if not character_name:
            log.debug("voice_nick: channel %s is not a game voice for %s or no character name", after_id, member.name)
            return
        if key in _original_nicks:
            return  # already applied (e.g. moved between game voice channels, we didn't restore above)
        # If they have a server nick, use it and restore it after; if none, use global display name and clear nick after
        original_nick = member.nick
        current_display = original_nick or member.display_name
        # If nick is already "CharacterName (Original)" (e.g. after bot restart), store original for restore
        prefix = character_name + " ("
        if current_display.startswith(prefix) and current_display.endswith(")"):
            extracted = current_display[len(prefix) : -1]
            # If extracted part is their global name (or username), they had no server nick — clear on restore
            _original_nicks[key] = (
                None if extracted == (getattr(member, "global_name", None) or member.name) else extracted
            )
            log.info("voice_nick: %s already has game nick format, tracking for restore", member.name)
            return
        new_nick = _display_nick(character_name, current_display)
        if new_nick == current_display:
            return
        try:
            await member.edit(nick=new_nick)
            _original_nicks[key] = original_nick  # None if they had no nick — we'll clear on restore
            log.info("voice_nick: set nick for %s to %r (stored original %r)", member.name, new_nick, original_nick)
        except discord.Forbidden as e:
            log.warning("voice_nick: set nick FORBIDDEN (permission/hierarchy) for %s -> %r: %s", member.name, new_nick, e)
        except discord.HTTPException as e:
            log.warning("voice_nick: set nick HTTP error for %s -> %r: %s", member.name, new_nick, e)
