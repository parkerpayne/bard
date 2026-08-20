"""yt-dlp helpers: import track metadata and resolve audio stream URLs."""
from __future__ import annotations

import asyncio
import logging
import re
from functools import partial
from typing import Any

import yt_dlp
from sqlalchemy import select

from bot.db import Track, async_session_factory

log = logging.getLogger(__name__)

_YT_ID_RE = re.compile(
    r'(?:v=|youtu\.be/|/v/|/embed/|shorts/|/live/)([A-Za-z0-9_-]{11})'
)
_YT_LIST_RE = re.compile(r'[?&]list=([A-Za-z0-9_-]+)')

_META_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'skip_download': True,
    'extract_flat': False,
    'noplaylist': True,
}

# Flat extraction: one network round-trip for the whole playlist instead of one
# per video. Entries carry id/title/duration/thumbnails, which is all we store.
_PLAYLIST_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'skip_download': True,
    'extract_flat': 'in_playlist',
    'ignoreerrors': True,
}

# Player client matters more than it looks. yt-dlp's current default
# (ANDROID_VR) hands back stream URLs that plain HTTP can fetch but ffmpeg gets
# 403 on, which shows up as "Error opening input" and a track that dies
# instantly. The clients below produce URLs ffmpeg can actually read; yt-dlp
# walks the list until one yields a playable format.
_PLAYER_CLIENTS = ['android', 'web_safari', 'web', 'ios', 'tv']

_AUDIO_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'skip_download': True,
    'format': 'bestaudio/best',
    'extractor_args': {'youtube': {'player_client': _PLAYER_CLIENTS}},
}


def extract_youtube_id(url: str) -> str | None:
    m = _YT_ID_RE.search(url)
    return m.group(1) if m else None


def extract_playlist_id(url: str) -> str | None:
    """Return the `list=` id, ignoring YouTube's auto-generated mixes (RD…)."""
    m = _YT_LIST_RE.search(url)
    if not m:
        return None
    list_id = m.group(1)
    return None if list_id.startswith(("RD", "UL")) else list_id


def _run_ydl(opts: dict, url: str) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


async def _ydl_async(opts: dict, url: str) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_run_ydl, opts, url))


def _thumbnail_of(info: dict[str, Any]) -> str | None:
    thumb = info.get('thumbnail')
    if thumb:
        return thumb
    thumbs = info.get('thumbnails') or []
    return thumbs[-1].get('url') if thumbs else None


async def _upsert_track(
    youtube_id: str, title: str, duration_sec: int | None, thumbnail_url: str | None
) -> Track:
    async with async_session_factory() as session:
        result = await session.execute(select(Track).where(Track.youtube_id == youtube_id))
        track = result.scalars().one_or_none()
        if not track:
            track = Track(
                youtube_id=youtube_id,
                title=title,
                duration_sec=duration_sec,
                thumbnail_url=thumbnail_url,
            )
            session.add(track)
            await session.commit()
            await session.refresh(track)
    return track


async def _find_track(youtube_id: str) -> Track | None:
    async with async_session_factory() as session:
        result = await session.execute(select(Track).where(Track.youtube_id == youtube_id))
        return result.scalars().one_or_none()


async def import_track(url: str) -> Track:
    """
    Fetch YouTube metadata for url and upsert a Track row.
    Returns the Track (existing or newly created).
    Raises ValueError if the URL is not a valid YouTube video.
    """
    youtube_id = extract_youtube_id(url)

    # Fast path: already in DB
    if youtube_id:
        existing = await _find_track(youtube_id)
        if existing:
            return existing

    info = await _ydl_async(_META_OPTS, url)
    youtube_id = youtube_id or info.get('id')
    if not youtube_id:
        raise ValueError(f"Could not resolve a YouTube video ID from: {url}")

    return await _upsert_track(
        youtube_id,
        info.get('title', 'Unknown'),
        info.get('duration'),
        _thumbnail_of(info),
    )


async def import_playlist(url: str) -> tuple[list[Track], int]:
    """
    Import every video in a YouTube playlist URL.
    Returns (tracks, skipped) where skipped counts entries with no usable id
    (deleted/private videos yt-dlp could not resolve).
    """
    info = await _ydl_async(_PLAYLIST_OPTS, url)
    entries = [e for e in (info.get('entries') or []) if e]
    if not entries:
        raise ValueError("That playlist is empty or could not be read.")

    tracks: list[Track] = []
    skipped = 0
    for entry in entries:
        youtube_id = entry.get('id')
        if not youtube_id or len(youtube_id) != 11:
            skipped += 1
            continue
        duration = entry.get('duration')
        try:
            tracks.append(await _upsert_track(
                youtube_id,
                entry.get('title') or 'Unknown',
                int(duration) if duration else None,
                _thumbnail_of(entry) or f"https://i.ytimg.com/vi/{youtube_id}/mqdefault.jpg",
            ))
        except Exception as exc:  # one bad row must not sink the whole import
            log.warning("import_playlist: skipping %s: %s", youtube_id, exc)
            skipped += 1

    return tracks, skipped


async def import_url(url: str) -> tuple[list[Track], int]:
    """Import a single video or a whole playlist, whichever the URL points at."""
    if extract_playlist_id(url):
        return await import_playlist(url)
    return [await import_track(url)], 0


async def get_audio_source(youtube_id: str) -> tuple[str, dict[str, str]]:
    """
    Resolve a direct audio stream URL plus the HTTP headers required to fetch it.

    YouTube binds a stream URL to the client that requested it (the `c=` param),
    and rejects requests whose User-Agent does not match with 403 Forbidden. The
    headers must travel with the URL to whatever finally reads it — ffmpeg or
    the browser proxy — or playback dies on a URL that looks perfectly valid.
    The URL is time-limited (a few hours); resolve close to playback.
    """
    url = f'https://www.youtube.com/watch?v={youtube_id}'
    info = await _ydl_async(_AUDIO_OPTS, url)

    direct_url = info.get('url')
    headers = dict(info.get('http_headers') or {})
    if not direct_url:
        # Some extractors only populate per-format URLs.
        for fmt in reversed(info.get('formats') or []):
            if fmt.get('acodec') not in (None, 'none') and fmt.get('url'):
                direct_url = fmt['url']
                headers = dict(fmt.get('http_headers') or headers)
                break
    if not direct_url:
        raise RuntimeError(f"yt-dlp returned no audio URL for {youtube_id}")

    # Only the headers that actually gate access; the rest confuse ffmpeg.
    allowed = ('User-Agent', 'Accept', 'Accept-Language', 'Cookie', 'Referer', 'Origin')
    headers = {k: v for k, v in headers.items() if k in allowed}
    return direct_url, headers


async def get_audio_url(youtube_id: str) -> str:
    """Backwards-compatible wrapper: URL only, no headers."""
    url, _ = await get_audio_source(youtube_id)
    return url
