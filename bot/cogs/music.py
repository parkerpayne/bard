"""Discord voice music cog — play order, FFmpeg playback, and /music commands."""
from __future__ import annotations

import asyncio
import logging
import random
import shlex
import time
from functools import partial
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.db import Playlist, PlaylistTrack, Track, async_session_factory
from bot.ytdlp import get_audio_source, import_url

log = logging.getLogger(__name__)

_RECONNECT_OPTS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"

# Give up on a playlist after this many tracks fail back to back.
_MAX_CONSECUTIVE_FAILURES = 5

# A track that "finishes" faster than this never really played — ffmpeg failed
# to open the stream. Without this, an unplayable playlist advances as fast as
# the event loop allows and hammers YouTube in a tight loop.
_MIN_PLAYED_SEC = 3.0


def _ffmpeg_before_options(headers: dict[str, str]) -> str:
    """Build ffmpeg input options that carry yt-dlp's auth headers."""
    opts = [_RECONNECT_OPTS]
    ua = headers.get("User-Agent")
    if ua:
        opts.append(f"-user_agent {shlex.quote(ua)}")
    rest = "".join(f"{k}: {v}\r\n" for k, v in headers.items() if k != "User-Agent")
    if rest:
        opts.append(f"-headers {shlex.quote(rest)}")
    return " ".join(opts)


def parse_tags(raw: str | None) -> list[str]:
    """Split a playlist's tag string into normalised tags."""
    if not raw:
        return []
    return [t.lower() for t in raw.replace(",", " ").split() if t]


def _fmt_duration(sec: int | None) -> str:
    if not sec:
        return "0:00"
    return f"{sec // 60}:{sec % 60:02d}"


class MusicCog(commands.Cog, name="MusicCog"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._voice_client: Optional[discord.VoiceClient] = None

        # Play order: _queue holds the playlist in stored order, _order is the
        # sequence of indices we actually play (shuffled or not), _pos points
        # into _order. Keeping these separate means toggling shuffle never
        # loses track of what is playing right now.
        self._queue: list[Track] = []
        self._order: list[int] = []
        self._pos: int = 0

        self._playlist_id: Optional[int] = None
        self._paused: bool = False
        self._shuffled: bool = False
        self._volume: float = 0.5
        self._source: Optional[discord.PCMVolumeTransformer] = None

        # Bumped whenever we deliberately replace or tear down a source, so the
        # FFmpeg "after" callback of the old source can tell it is stale and
        # not advance the queue a second time.
        self._generation: int = 0
        self._failures: int = 0
        # Set when we stop a source on purpose (skip/previous), so the
        # after-callback does not mistake a deliberate stop for a dead stream.
        self._expected_stop: bool = False

        # Position tracking
        self._play_start: float = 0.0   # monotonic time when current track began
        self._pause_start: float = 0.0  # monotonic time when pause was triggered
        self._pause_accum: float = 0.0  # total seconds spent paused this track

    # ------------------------------------------------------------------
    # Public API (called from web server handlers and slash commands)
    # ------------------------------------------------------------------

    async def play_playlist(
        self,
        playlist_id: int,
        start_track_id: Optional[int] = None,
        shuffled: Optional[bool] = None,
        channel: Optional[discord.VoiceChannel] = None,
    ) -> int:
        """Load a playlist and start voice playback. Returns the track count."""
        tracks = await load_playlist_tracks(playlist_id)
        if not tracks:
            return 0

        if shuffled is not None:
            self._shuffled = shuffled

        self._playlist_id = playlist_id
        self._queue = tracks
        self._paused = False
        self._failures = 0
        self._rebuild_order(start_track_id)

        if channel is not None:
            await self._connect(channel)
        await self._play_current()
        return len(tracks)

    async def pause(self) -> None:
        if self._voice_client and self._voice_client.is_playing():
            self._voice_client.pause()
            self._paused = True
            self._pause_start = time.monotonic()

    async def resume(self) -> None:
        if self._voice_client and self._voice_client.is_paused():
            self._voice_client.resume()
            self._paused = False
            self._pause_accum += time.monotonic() - self._pause_start

    async def stop(self) -> None:
        self._generation += 1  # invalidate the running source's after-callback
        self._queue = []
        self._order = []
        self._pos = 0
        self._playlist_id = None
        self._paused = False
        self._source = None
        if self._voice_client and (self._voice_client.is_playing() or self._voice_client.is_paused()):
            self._voice_client.stop()

    async def skip(self) -> None:
        """Stop the current track; the after-callback advances the queue."""
        if self._voice_client and (self._voice_client.is_playing() or self._voice_client.is_paused()):
            self._paused = False
            self._expected_stop = True
            self._voice_client.stop()
        elif self._queue:
            await self._advance()

    async def previous(self) -> None:
        if not self._queue:
            return
        # Restart the current track if we are more than 3s in, else step back.
        if self.position_sec() > 3:
            await self._play_current()
            return
        self._pos = (self._pos - 1) % len(self._order)
        self._failures = 0
        await self._play_current()

    async def set_shuffled(self, shuffled: bool) -> None:
        """Toggle shuffle, keeping the currently playing track in place."""
        if shuffled == self._shuffled:
            return
        self._shuffled = shuffled
        if not self._queue:
            return
        current = self._current_track()
        self._rebuild_order(current.id if current else None)

    async def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))
        if self._source:
            self._source.volume = self._volume

    async def join_voice(
        self, channel_id: Optional[int] = None, prefer_user: Optional[discord.Member] = None
    ) -> bool:
        """Join a specific channel, the caller's channel, or the busiest one."""
        channel = await self._find_voice_channel(channel_id, prefer_user)
        if not channel:
            return False
        await self._connect(channel)
        return True

    async def leave_voice(self) -> None:
        await self.stop()
        if self._voice_client:
            try:
                await self._voice_client.disconnect()
            except Exception as exc:
                log.warning("MusicCog: disconnect failed: %s", exc)
            self._voice_client = None

    def position_sec(self) -> float:
        """Elapsed playback seconds for the current track, accounting for pauses."""
        if not self._queue or not self._voice_client:
            return 0.0
        if self._paused:
            return max(0.0, self._pause_start - self._play_start - self._pause_accum)
        if self._voice_client.is_playing():
            return max(0.0, time.monotonic() - self._play_start - self._pause_accum)
        return 0.0

    def is_active(self) -> bool:
        """True when voice is the live playback device (connected with a queue)."""
        return bool(
            self._voice_client
            and self._voice_client.is_connected()
            and self._queue
        )

    def state_dict(self) -> dict:
        track = self._current_track()
        in_voice = bool(self._voice_client and self._voice_client.is_connected())
        return {
            "playing": bool(self._voice_client and self._voice_client.is_playing()),
            "paused": self._paused,
            "shuffled": self._shuffled,
            "volume": self._volume,
            "playlist_id": self._playlist_id,
            "position_sec": self.position_sec(),
            # "device" describes what is actually driving audio right now, so a
            # browser client can tell whether to defer to the bot or to itself.
            "device": "voice" if self.is_active() else "browser",
            "connected": in_voice,
            "voice_channel_id": self._voice_client.channel.id if in_voice else None,
            "current": _track_dict(track) if track else None,
            "queue": [_track_dict(t) for t in self._ordered_queue()],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild_order(self, start_track_id: Optional[int] = None) -> None:
        """Recompute the play order, starting at start_track_id when given."""
        n = len(self._queue)
        self._order = list(range(n))
        if self._shuffled:
            random.shuffle(self._order)
        self._pos = 0
        if start_track_id is None or not n:
            return
        ids = [t.id for t in self._queue]
        if start_track_id not in ids:
            return
        # Rotate so the requested track plays first and the rest follow in the
        # already-decided order (shuffled or sequential).
        queue_idx = ids.index(start_track_id)
        order_pos = self._order.index(queue_idx)
        self._order = self._order[order_pos:] + self._order[:order_pos]
        self._pos = 0

    def _ordered_queue(self) -> list[Track]:
        return [self._queue[i] for i in self._order if 0 <= i < len(self._queue)]

    def _current_track(self) -> Optional[Track]:
        if not self._queue or not self._order:
            return None
        idx = self._order[self._pos % len(self._order)]
        return self._queue[idx] if 0 <= idx < len(self._queue) else None

    async def _play_current(self) -> None:
        if not self._queue:
            return

        if not self._voice_client or not self._voice_client.is_connected():
            if not await self.join_voice():
                log.warning("MusicCog: no voice channel available for playback")
                return

        track = self._current_track()
        if not track:
            return

        try:
            audio_url, headers = await get_audio_source(track.youtube_id)
        except Exception as exc:
            log.error("MusicCog: audio URL failed for %s: %s", track.youtube_id, exc)
            await self._handle_failure()
            return

        # Bump the generation first: the currently running source's callback
        # will now see a stale generation and skip its advance.
        self._generation += 1
        my_gen = self._generation
        if self._voice_client.is_playing() or self._voice_client.is_paused():
            self._expected_stop = False   # the stale callback is ignored by generation
            self._voice_client.stop()

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(
                audio_url,
                before_options=_ffmpeg_before_options(headers),
                options="-vn",
            ),
            volume=self._volume,
        )
        self._source = source

        self._play_start = time.monotonic()
        self._pause_accum = 0.0
        self._paused = False

        loop = asyncio.get_running_loop()

        started_at = self._play_start

        def _after(error: Optional[Exception], gen: int = my_gen) -> None:
            if error:
                log.warning("MusicCog: playback error: %s", error)
            if gen != self._generation:
                return  # superseded by a newer source; that one owns the queue
            # ffmpeg exiting immediately means the stream never opened (a 403 on
            # an expired or client-bound URL, a dead video). Treat it as a
            # failure rather than "track finished", or we spin.
            if self._expected_stop:
                self._expected_stop = False          # user asked for this
                asyncio.run_coroutine_threadsafe(self._advance(), loop)
                return
            played = time.monotonic() - started_at
            if error or played < _MIN_PLAYED_SEC:
                asyncio.run_coroutine_threadsafe(self._handle_failure(), loop)
            else:
                asyncio.run_coroutine_threadsafe(self._advance(), loop)

        self._voice_client.play(source, after=_after)
        log.info("MusicCog: playing '%s' (track_id=%d)", track.title, track.id)

        async def _clear_failures() -> None:
            await asyncio.sleep(_MIN_PLAYED_SEC)
            if self._generation == my_gen:
                self._failures = 0   # it is genuinely playing

        asyncio.create_task(_clear_failures())

    async def _handle_failure(self) -> None:
        """Count a failed track, move on, and stop once the whole queue fails."""
        track = self._current_track()
        self._failures += 1
        limit = min(_MAX_CONSECUTIVE_FAILURES, len(self._queue) or 1)
        if self._failures >= limit:
            log.error(
                "MusicCog: %d tracks failed in a row (last: %s) — stopping playback",
                self._failures, track.title if track else "?",
            )
            await self.stop()
            return
        if self._order:
            self._pos = (self._pos + 1) % len(self._order)
        # Small backoff so a bad run cannot become a tight retry loop.
        await asyncio.sleep(1.0)
        await self._play_current()

    async def _advance(self) -> None:
        if not self._queue or not self._order:
            return
        self._pos += 1
        if self._pos >= len(self._order):
            # Loop the playlist; reshuffle so the next pass is a new order.
            self._pos = 0
            if self._shuffled:
                random.shuffle(self._order)
        await self._play_current()

    async def _find_voice_channel(
        self, channel_id: Optional[int], prefer_user: Optional[discord.Member] = None
    ) -> Optional[discord.VoiceChannel]:
        if channel_id:
            ch = self.bot.get_channel(channel_id)
            if isinstance(ch, discord.VoiceChannel):
                return ch

        # The channel the requester is sitting in wins.
        if prefer_user is not None and prefer_user.voice and prefer_user.voice.channel:
            ch = prefer_user.voice.channel
            if isinstance(ch, discord.VoiceChannel):
                return ch

        # Otherwise stay where we are, else pick the busiest populated channel.
        if self._voice_client and self._voice_client.is_connected():
            ch = self._voice_client.channel
            if isinstance(ch, discord.VoiceChannel):
                return ch

        best: Optional[discord.VoiceChannel] = None
        best_count = 0
        for guild in self.bot.guilds:
            for ch in guild.voice_channels:
                humans = len([m for m in ch.members if not m.bot])
                if humans > best_count:
                    best, best_count = ch, humans
        return best

    async def _connect(self, channel: discord.VoiceChannel) -> None:
        if self._voice_client and self._voice_client.is_connected():
            if self._voice_client.channel.id == channel.id:
                return
            await self._voice_client.move_to(channel)
        else:
            self._voice_client = await channel.connect()
        log.info("MusicCog: connected to #%s (%d)", channel.name, channel.id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after) -> None:
        """Stop and disconnect once the bot is alone in a channel."""
        vc = self._voice_client
        if member.bot or not vc or not vc.is_connected():
            return
        if before.channel is None or before.channel.id != vc.channel.id:
            return
        if any(not m.bot for m in vc.channel.members):
            return
        log.info("MusicCog: left alone in #%s, disconnecting", vc.channel.name)
        await self.leave_voice()

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    music = app_commands.Group(name="music", description="Play playlists in voice chat")

    async def _playlist_autocomplete(
        self, _interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        q = current.lower().strip()
        async with async_session_factory() as session:
            rows = await session.execute(select(Playlist).order_by(Playlist.name))
            playlists = rows.scalars().all()
        matches = [
            p for p in playlists
            if not q or q in p.name.lower() or any(q in t for t in parse_tags(p.tags))
        ]
        return [
            app_commands.Choice(name=p.name[:100], value=str(p.id))
            for p in matches[:25]
        ]

    @music.command(name="play", description="Play a playlist in your voice channel")
    @app_commands.describe(playlist="Playlist to play", shuffle="Shuffle the playlist (default: yes)")
    @app_commands.autocomplete(playlist=_playlist_autocomplete)
    async def cmd_play(
        self, interaction: discord.Interaction, playlist: str, shuffle: bool = True
    ) -> None:
        await interaction.response.defer(thinking=True)

        pl = await _resolve_playlist(playlist)
        if not pl:
            await interaction.followup.send(f"No playlist matching **{playlist}**.", ephemeral=True)
            return

        channel = None
        if isinstance(interaction.user, discord.Member) and interaction.user.voice:
            channel = interaction.user.voice.channel
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.followup.send("Join a voice channel first.", ephemeral=True)
            return

        count = await self.play_playlist(pl.id, shuffled=shuffle, channel=channel)
        if not count:
            await interaction.followup.send(f"**{pl.name}** has no tracks yet.", ephemeral=True)
            return

        track = self._current_track()
        await interaction.followup.send(
            f"{'🔀' if shuffle else '▶️'} Playing **{pl.name}** ({count} tracks) in "
            f"**{channel.name}**\nNow playing: *{track.title if track else '…'}*"
        )

    @music.command(name="pause", description="Pause playback")
    async def cmd_pause(self, interaction: discord.Interaction) -> None:
        await self.pause()
        await interaction.response.send_message("⏸️ Paused.", ephemeral=True)

    @music.command(name="resume", description="Resume playback")
    async def cmd_resume(self, interaction: discord.Interaction) -> None:
        await self.resume()
        await interaction.response.send_message("▶️ Resumed.", ephemeral=True)

    @music.command(name="skip", description="Skip to the next track")
    async def cmd_skip(self, interaction: discord.Interaction) -> None:
        if not self._queue:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        await self.skip()
        await interaction.response.send_message("⏭️ Skipped.", ephemeral=True)

    @music.command(name="shuffle", description="Turn shuffle on or off")
    async def cmd_shuffle(self, interaction: discord.Interaction, on: bool = True) -> None:
        await self.set_shuffled(on)
        await interaction.response.send_message(
            f"🔀 Shuffle {'on' if on else 'off'}.", ephemeral=True
        )

    @music.command(name="volume", description="Set playback volume (0-100)")
    async def cmd_volume(self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 100]) -> None:
        await self.set_volume(percent / 100)
        await interaction.response.send_message(f"🔊 Volume {percent}%.", ephemeral=True)

    @music.command(name="stop", description="Stop playback and leave the voice channel")
    async def cmd_stop(self, interaction: discord.Interaction) -> None:
        await self.leave_voice()
        await interaction.response.send_message("⏹️ Stopped.", ephemeral=True)

    @music.command(name="now", description="Show what is playing")
    async def cmd_now(self, interaction: discord.Interaction) -> None:
        track = self._current_track()
        if not track:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        upcoming = self._ordered_queue()[self._pos + 1:self._pos + 6]
        embed = discord.Embed(
            title=track.title,
            url=f"https://www.youtube.com/watch?v={track.youtube_id}",
            description=f"`{_fmt_duration(int(self.position_sec()))} / {_fmt_duration(track.duration_sec)}`"
                        f"{' · 🔀 shuffled' if self._shuffled else ''}",
            color=discord.Color.green(),
        )
        if track.thumbnail_url:
            embed.set_thumbnail(url=track.thumbnail_url)
        if upcoming:
            embed.add_field(
                name="Up next",
                value="\n".join(f"{i}. {t.title}" for i, t in enumerate(upcoming, 1)),
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @music.command(name="playlists", description="List playlists, optionally filtered by tag")
    async def cmd_playlists(self, interaction: discord.Interaction, tag: Optional[str] = None) -> None:
        async with async_session_factory() as session:
            rows = await session.execute(select(Playlist).order_by(Playlist.name))
            playlists = rows.scalars().all()
        if tag:
            wanted = tag.lower().strip()
            playlists = [p for p in playlists if wanted in parse_tags(p.tags)]
        if not playlists:
            await interaction.response.send_message(
                f"No playlists{f' tagged `{tag}`' if tag else ''} yet.", ephemeral=True
            )
            return
        lines = []
        for p in playlists:
            tags = parse_tags(p.tags)
            lines.append(f"• **{p.name}**" + (f" — `{'` `'.join(tags)}`" if tags else ""))
        embed = discord.Embed(
            title=f"Playlists{f' tagged “{tag}”' if tag else ''}",
            description="\n".join(lines)[:4000],
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @music.command(name="add", description="Import a YouTube video or playlist into the library")
    async def cmd_add(self, interaction: discord.Interaction, url: str) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            tracks, skipped = await import_url(url)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception as exc:
            log.error("cmd_add failed for %s: %s", url, exc)
            await interaction.followup.send("Could not fetch that from YouTube.", ephemeral=True)
            return
        if len(tracks) == 1:
            await interaction.followup.send(f"Added **{tracks[0].title}** to the library.", ephemeral=True)
        else:
            note = f" ({skipped} unavailable skipped)" if skipped else ""
            await interaction.followup.send(
                f"Added **{len(tracks)}** tracks to the library{note}.", ephemeral=True
            )


def _track_dict(t: Track) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "youtube_id": t.youtube_id,
        "duration_sec": t.duration_sec,
        "thumbnail_url": t.thumbnail_url,
    }


async def load_playlist_tracks(playlist_id: int) -> list[Track]:
    """Load a playlist's tracks in stored order (one query, no N+1)."""
    async with async_session_factory() as session:
        rows = await session.execute(
            select(Track)
            .join(PlaylistTrack, PlaylistTrack.track_id == Track.id)
            .where(PlaylistTrack.playlist_id == playlist_id)
            .order_by(PlaylistTrack.position)
        )
        return list(rows.scalars().all())


async def _resolve_playlist(value: str) -> Optional[Playlist]:
    """Resolve an autocomplete value (an id) or a typed playlist name."""
    async with async_session_factory() as session:
        if value.isdigit():
            pl = await session.get(Playlist, int(value))
            if pl:
                return pl
        rows = await session.execute(select(Playlist).order_by(Playlist.name))
        playlists = rows.scalars().all()
    needle = value.lower().strip()
    for p in playlists:
        if p.name.lower() == needle:
            return p
    for p in playlists:
        if needle in p.name.lower():
            return p
    return None
