"""Scheduling: poll detection, halfway reminder, /schedule remind."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Set

import discord
from discord import app_commands
from discord.ext import commands
from discord.http import Route
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import Game, SchedulePoll, async_session_factory
from bot.utils import get_game_by_channel, get_game_by_scheduling_channel, get_player_ids

if TYPE_CHECKING:
    from bot.main import Bot


def _poll_answer_ids(poll) -> list[int]:
    """Get answer IDs from a discord Poll object."""
    out = []
    for a in getattr(poll, "answers", []) or []:
        aid = getattr(a, "answer_id", None) or getattr(a, "id", None)
        if aid is not None:
            out.append(int(aid))
    return out


async def _get_poll_voter_ids(bot: Bot, channel_id: int, message_id: int, poll) -> Set[int]:
    """Call Discord API to get all user IDs who voted on any answer of this poll."""
    voter_ids: Set[int] = set()
    answer_ids = _poll_answer_ids(poll)
    if not answer_ids:
        return voter_ids
    http = bot._connection.http
    for answer_id in answer_ids:
        route = Route(
            "GET",
            "/channels/{channel_id}/polls/{message_id}/answers/{answer_id}",
            channel_id=channel_id,
            message_id=message_id,
            answer_id=answer_id,
        )
        try:
            data = await http.request(route)
            for u in data.get("users", []):
                uid = u.get("id")
                if uid:
                    voter_ids.add(int(uid))
        except Exception:
            continue
    return voter_ids


def _poll_expiry(poll) -> datetime | None:
    """Get poll expiry as timezone-aware datetime."""
    exp = getattr(poll, "expiry", None)
    if exp is None:
        return None
    if hasattr(exp, "replace"):
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp
    return None


def _message_created_at(msg: discord.Message) -> datetime:
    t = msg.created_at
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t


class SchedulingCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self._scheduled_tasks: list[asyncio.Task] = []
        self._register_commands()

    def _register_commands(self):
        schedule_group = app_commands.Group(
            name="schedule",
            description="Scheduling (use in game text channels)",
        )
        schedule_group.add_command(
            app_commands.command(name="remind", description="DM players who haven't voted on the latest scheduling poll")(
                self.schedule_remind
            )
        )
        self.bot.tree.add_command(schedule_group)

    async def _remind_non_voters(self, game: Game, channel_id: int, message_id: int, guild_id: int):
        """DM all players (not DM) who haven't voted, with link to the poll message."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return
        try:
            message = await channel.fetch_message(message_id)
        except Exception:
            return
        poll = getattr(message, "poll", None)
        if not poll:
            return
        voter_ids = await _get_poll_voter_ids(self.bot, channel_id, message_id, poll)
        link = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
        async with async_session_factory() as session:
            player_ids = await get_player_ids(session, game.id)
        non_voters = player_ids - voter_ids
        failed = []
        for uid in non_voters:
            user = guild.get_member(uid) or await self.bot.fetch_user(uid)
            if not user:
                continue
            try:
                await user.send(
                    f"You haven't voted on the session scheduling for **{game.name}**. "
                    f"Please vote here: {link}"
                )
            except discord.Forbidden:
                failed.append(user.display_name)
        return failed

    async def _run_reminder_at(self, poll_id: int):
        """Wait until reminder_at then send reminders and mark reminder_sent."""
        async with async_session_factory() as session:
            poll = await session.get(SchedulePoll, poll_id)
            if not poll or poll.reminder_sent:
                return
            reminder_at = poll.reminder_at
            if reminder_at.tzinfo is None:
                reminder_at = reminder_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delay = (reminder_at - now).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        async with async_session_factory() as session:
            poll = await session.get(SchedulePoll, poll_id)
            if not poll or poll.reminder_sent:
                return
            game = await session.get(Game, poll.game_id)
            if not game:
                return
            channel_id = poll.channel_id
            message_id = poll.message_id
            guild_id = game.guild_id
        failed = await self._remind_non_voters(game, channel_id, message_id, guild_id)
        async with async_session_factory() as session:
            poll = await session.get(SchedulePoll, poll_id)
            if poll:
                poll.reminder_sent = True
                await session.commit()
        if failed and guild_id:
            guild = self.bot.get_guild(guild_id)
            if guild:
                channel = guild.get_channel(channel_id)
                if channel:
                    try:
                        await channel.send(
                            f"Reminder sent. Could not DM: {', '.join(failed)}"
                        )
                    except Exception:
                        pass

    async def _start_poll_reminder_scheduler(self):
        """On startup, schedule reminder tasks for all unsent SchedulePolls with reminder_at in the future."""
        await self.bot.wait_until_ready()
        async with async_session_factory() as session:
            result = await session.execute(
                select(SchedulePoll).where(
                    SchedulePoll.reminder_sent == False,
                    SchedulePoll.reminder_at > datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            rows = result.scalars().all()
        for poll in rows:
            task = asyncio.create_task(self._run_reminder_at(poll.id))
            self._scheduled_tasks.append(task)

    async def _on_poll_created(self, message: discord.Message, game: Game):
        """New message with poll in a scheduling channel: store and schedule halfway reminder."""
        poll = getattr(message, "poll", None)
        if not poll:
            return
        expiry = _poll_expiry(poll)
        if not expiry:
            return
        created = _message_created_at(message)
        half = (expiry - created).total_seconds() / 2
        reminder_at = created.timestamp() + half
        reminder_dt = datetime.fromtimestamp(reminder_at, tz=timezone.utc)
        if reminder_dt <= datetime.now(timezone.utc):
            return
        async with async_session_factory() as session:
            schedule_poll = SchedulePoll(
                game_id=game.id,
                channel_id=message.channel.id,
                message_id=message.id,
                expiry=expiry,
                reminder_at=reminder_dt.replace(tzinfo=None),
            )
            session.add(schedule_poll)
            await session.commit()
            await session.refresh(schedule_poll)
        task = asyncio.create_task(self._run_reminder_at(schedule_poll.id))
        self._scheduled_tasks.append(task)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not getattr(message, "poll", None):
            return
        async with async_session_factory() as session:
            game = await get_game_by_scheduling_channel(
                session, message.guild.id, message.channel.id
            )
        if game:
            await self._on_poll_created(message, game)

    async def schedule_remind(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return
        async with async_session_factory() as session:
            game = await get_game_by_channel(
                session, interaction.guild.id, interaction.channel_id
            )
            if not game:
                await interaction.response.send_message(
                    "Run this command in one of the game's text channels (important, scheduling, or general).",
                    ephemeral=True,
                )
                return
            if game.dm_user_id != interaction.user.id:
                await interaction.response.send_message(
                    "Only the DM can run this.",
                    ephemeral=True,
                )
                return

        channel = interaction.guild.get_channel(game.text_scheduling_id)
        if not channel:
            await interaction.response.send_message(
                "Scheduling channel not found.",
                ephemeral=True,
            )
            return
        try:
            messages = [m async for m in channel.history(limit=20)]
        except Exception:
            await interaction.response.send_message(
                "Could not read the scheduling channel.",
                ephemeral=True,
            )
            return
        poll_message = None
        for m in messages:
            if getattr(m, "poll", None):
                poll_message = m
                break
        if not poll_message:
            await interaction.response.send_message(
                "No scheduling poll found in this channel. Create a poll here first.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        failed = await self._remind_non_voters(
            game,
            game.text_scheduling_id,
            poll_message.id,
            interaction.guild.id,
        )
        if failed:
            await interaction.followup.send(
                f"Reminder sent. Could not DM: {', '.join(failed)}",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "Reminders sent to players who haven't voted.",
                ephemeral=True,
            )
