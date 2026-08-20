"""Web server: audio proxy and API routes for the music UI."""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import TYPE_CHECKING

import aiohttp
import discord
from aiohttp import web
from sqlalchemy import func, select

from bot import auth
from bot.db import Hotkey, Playlist, PlaylistTrack, Track, async_session_factory
from bot.ytdlp import get_audio_source, import_url

if TYPE_CHECKING:
    from discord.ext import commands

log = logging.getLogger(__name__)

WEB_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
COVERS_DIR = os.path.join(WEB_ROOT, "covers")
# Vite's build output: hashed .js/.css/fonts referenced by index.html.
ASSETS_DIR = os.path.join(WEB_ROOT, "assets")

_COVER_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
_MAX_COVER_BYTES = 8 * 1024 * 1024

# youtube_id -> (direct_url, headers, fetched_at); URLs are valid ~6h, refresh after 2h
_audio_cache: dict[str, tuple[str, dict, float]] = {}
_CACHE_TTL = 7200


def _track_dict(t: Track) -> dict:
    return {
        "id": t.id,
        "youtube_id": t.youtube_id,
        "title": t.title,
        "duration_sec": t.duration_sec,
        "thumbnail_url": t.thumbnail_url,
    }


def _playlist_dict(p: Playlist, track_count: int | None = None) -> dict:
    d = {"id": p.id, "name": p.name, "cover_path": p.cover_path, "tags": p.tags}
    if track_count is not None:
        d["track_count"] = track_count
    return d


def _err(message: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "message": message}, status=status)


async def _json_body(request: web.Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise ValueError("Invalid JSON")
    if not isinstance(body, dict):
        raise ValueError("Invalid JSON")
    return body


# --- Audio proxy ----------------------------------------------------------

async def _resolve_audio(youtube_id: str, force: bool = False) -> tuple[str, dict]:
    """Resolve a stream URL and the headers YouTube requires to serve it."""
    now = time.monotonic()
    if not force:
        entry = _audio_cache.get(youtube_id)
        if entry and now - entry[2] < _CACHE_TTL:
            return entry[0], entry[1]
    url, headers = await get_audio_source(youtube_id)
    _audio_cache[youtube_id] = (url, headers, now)
    return url, headers


async def api_audio_stream(request: web.Request) -> web.StreamResponse:
    try:
        track_id = int(request.match_info["track_id"])
    except ValueError:
        return web.Response(status=400, text="Invalid track id")

    async with async_session_factory() as session:
        track = await session.get(Track, track_id)
    if not track:
        return web.Response(status=404, text="Track not found")

    client: aiohttp.ClientSession = request.app["http_client"]

    for attempt in range(2):
        try:
            audio_url, stream_headers = await _resolve_audio(track.youtube_id, force=attempt > 0)
        except Exception as exc:
            log.error("Audio resolve failed for %s: %s", track.youtube_id, exc)
            return web.Response(status=502, text="Could not resolve audio for this track")

        # These headers are what make the URL work: YouTube 403s a stream fetched
        # with a User-Agent that does not match the client that resolved it.
        upstream_headers: dict[str, str] = dict(stream_headers)
        if "Range" in request.headers:
            upstream_headers["Range"] = request.headers["Range"]

        try:
            async with client.get(audio_url, headers=upstream_headers) as upstream:
                if upstream.status in (401, 403, 410) and attempt == 0:
                    _audio_cache.pop(track.youtube_id, None)
                    continue

                resp_headers: dict[str, str] = {
                    "Content-Type": upstream.headers.get("Content-Type", "audio/webm"),
                    "Accept-Ranges": "bytes",
                }
                for h in ("Content-Length", "Content-Range"):
                    if h in upstream.headers:
                        resp_headers[h] = upstream.headers[h]

                resp = web.StreamResponse(status=upstream.status, headers=resp_headers)
                await resp.prepare(request)
                async for chunk in upstream.content.iter_chunked(65536):
                    await resp.write(chunk)
                await resp.write_eof()
                return resp

        except (aiohttp.ClientError, ConnectionResetError) as exc:
            log.warning("Audio proxy error (attempt %d) for track %d: %s", attempt + 1, track_id, exc)
            if attempt == 0:
                _audio_cache.pop(track.youtube_id, None)
                continue
            return web.Response(status=502, text="Failed to stream audio")

    return web.Response(status=502, text="Failed to stream audio")


# --- Playback control API -------------------------------------------------

def _cog(request: web.Request):
    bot = request.app.get("bot")
    return bot.get_cog("MusicCog") if bot else None


_IDLE_STATE = {
    "playing": False, "paused": False, "shuffled": False, "volume": 0.5,
    "playlist_id": None, "position_sec": 0, "device": "browser",
    "connected": False, "voice_channel_id": None, "current": None, "queue": [],
}


async def api_now_playing(request: web.Request) -> web.Response:
    cog = _cog(request)
    return web.json_response(cog.state_dict() if cog else _IDLE_STATE)


async def api_play(request: web.Request) -> web.Response:
    cog = _cog(request)
    if not cog:
        return _err("Music cog not available", 503)
    try:
        body = await _json_body(request)
    except ValueError as exc:
        return _err(str(exc))

    playlist_id = body.get("playlist_id")
    if playlist_id is None:
        return _err("playlist_id required")
    track_id = body.get("track_id")
    shuffled = body.get("shuffled")

    try:
        count = await cog.play_playlist(
            int(playlist_id),
            int(track_id) if track_id is not None else None,
            shuffled=bool(shuffled) if shuffled is not None else None,
        )
    except Exception as exc:
        log.error("api_play error: %s", exc)
        return _err(str(exc), 500)

    if not count:
        return _err("That playlist has no tracks", 400)
    return web.json_response({"ok": True, "track_count": count})


async def _simple_control(request: web.Request, method: str) -> web.Response:
    cog = _cog(request)
    if cog:
        await getattr(cog, method)()
    return web.json_response({"ok": True})


async def api_pause(request: web.Request) -> web.Response:
    return await _simple_control(request, "pause")


async def api_resume(request: web.Request) -> web.Response:
    return await _simple_control(request, "resume")


async def api_stop(request: web.Request) -> web.Response:
    return await _simple_control(request, "stop")


async def api_skip(request: web.Request) -> web.Response:
    return await _simple_control(request, "skip")


async def api_previous(request: web.Request) -> web.Response:
    return await _simple_control(request, "previous")


async def api_shuffle(request: web.Request) -> web.Response:
    cog = _cog(request)
    try:
        body = await _json_body(request)
    except ValueError as exc:
        return _err(str(exc))
    shuffled = bool(body.get("shuffled", False))
    if cog:
        await cog.set_shuffled(shuffled)
    return web.json_response({"ok": True, "shuffled": shuffled})


async def api_volume(request: web.Request) -> web.Response:
    cog = _cog(request)
    try:
        body = await _json_body(request)
        volume = float(body.get("volume", 0.5))
    except (ValueError, TypeError):
        return _err("volume must be a number between 0 and 1")
    if cog:
        await cog.set_volume(volume)
    return web.json_response({"ok": True, "volume": volume})


async def api_device(request: web.Request) -> web.Response:
    """Switch playback device. Body: {"device": "voice"|"browser", "channel_id": int?}"""
    cog = _cog(request)
    if not cog:
        return _err("Music cog not available", 503)
    try:
        body = await _json_body(request)
    except ValueError as exc:
        return _err(str(exc))

    device = body.get("device", "browser")
    channel_id = body.get("channel_id")

    if device == "voice":
        ok = await cog.join_voice(int(channel_id) if channel_id else None)
        return web.json_response({
            "ok": ok,
            "message": "Joined" if ok else "No voice channel available — join one first",
        })
    await cog.leave_voice()
    return web.json_response({"ok": True})


async def api_devices(request: web.Request) -> web.Response:
    """List playback devices: this browser plus every reachable voice channel."""
    from bot.db import Game

    bot = request.app.get("bot")
    devices = [{"type": "browser", "label": "Browser", "channel_id": None, "members": 0}]
    if not bot:
        return web.json_response({"devices": devices})

    # Label a channel with its game name when it belongs to one.
    async with async_session_factory() as session:
        rows = await session.execute(select(Game))
        game_names = {g.voice_game_id: g.name for g in rows.scalars().all()}

    voice: list[dict] = []
    for guild in bot.guilds:
        for ch in guild.voice_channels:
            perms = ch.permissions_for(guild.me)
            if not (perms.view_channel and perms.connect):
                continue
            humans = len([m for m in ch.members if not m.bot])
            voice.append({
                "type": "voice",
                "label": game_names.get(ch.id, ch.name),
                "channel": f"{guild.name} · {ch.name}",
                "channel_id": ch.id,
                "members": humans,
            })

    # Channels with people in them first, then alphabetical.
    voice.sort(key=lambda d: (-d["members"], d["label"].lower()))
    return web.json_response({"devices": devices + voice})


# --- Library --------------------------------------------------------------

async def api_library_tracks(_request: web.Request) -> web.Response:
    async with async_session_factory() as session:
        rows = await session.execute(select(Track).order_by(Track.added_at.desc(), Track.id.desc()))
        tracks = rows.scalars().all()
    return web.json_response([_track_dict(t) for t in tracks])


async def api_library_import(request: web.Request) -> web.Response:
    try:
        body = await _json_body(request)
    except ValueError as exc:
        return _err(str(exc))

    url = str(body.get("url", "")).strip()
    if not url:
        return _err("url is required")

    try:
        tracks, skipped = await import_url(url)
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        log.error("library import error for %s: %s", url, exc)
        return _err("Failed to fetch that from YouTube", 500)

    if not tracks:
        return _err("Nothing importable was found at that URL")

    # Optionally drop the imported tracks straight into a playlist.
    playlist_id = body.get("playlist_id")
    added_to_playlist = 0
    if playlist_id is not None:
        added_to_playlist = await _append_tracks(int(playlist_id), [t.id for t in tracks])

    return web.json_response({
        "ok": True,
        "track": _track_dict(tracks[0]),
        "tracks": [_track_dict(t) for t in tracks],
        "imported": len(tracks),
        "skipped": skipped,
        "added_to_playlist": added_to_playlist,
    })


async def api_library_delete(request: web.Request) -> web.Response:
    try:
        track_id = int(request.match_info["track_id"])
    except ValueError:
        return _err("Invalid id")
    async with async_session_factory() as session:
        track = await session.get(Track, track_id)
        if not track:
            return _err("Not found", 404)
        # Playlist entries cascade via the relationship.
        await session.delete(track)
        await session.commit()
    return web.json_response({"ok": True})


# --- Playlists ------------------------------------------------------------

async def api_playlists(_request: web.Request) -> web.Response:
    async with async_session_factory() as session:
        # Join to tracks: an entry whose track has been deleted is not a track.
        cnt_sq = (
            select(PlaylistTrack.playlist_id, func.count().label("cnt"))
            .join(Track, Track.id == PlaylistTrack.track_id)
            .group_by(PlaylistTrack.playlist_id)
            .subquery()
        )
        stmt = (
            select(Playlist, cnt_sq.c.cnt)
            .outerjoin(cnt_sq, Playlist.id == cnt_sq.c.playlist_id)
            .order_by(Playlist.name)
        )
        rows = await session.execute(stmt)
        result = [_playlist_dict(p, cnt or 0) for p, cnt in rows]
    return web.json_response({"playlists": result})


async def api_create_playlist(request: web.Request) -> web.Response:
    try:
        body = await _json_body(request)
    except ValueError as exc:
        return _err(str(exc))

    name = str(body.get("name", "")).strip()
    tags = str(body.get("tags", "")).strip() or None
    if not name:
        return _err("name is required")

    async with async_session_factory() as session:
        p = Playlist(name=name, tags=tags)
        session.add(p)
        await session.commit()
        await session.refresh(p)
    return web.json_response({"ok": True, "playlist": _playlist_dict(p, 0)})


async def api_get_playlist(request: web.Request) -> web.Response:
    try:
        pl_id = int(request.match_info["id"])
    except ValueError:
        return _err("Invalid id")

    async with async_session_factory() as session:
        p = await session.get(Playlist, pl_id)
        if not p:
            return _err("Not found", 404)
        rows = await session.execute(
            select(Track, PlaylistTrack.position)
            .join(PlaylistTrack, PlaylistTrack.track_id == Track.id)
            .where(PlaylistTrack.playlist_id == pl_id)
            .order_by(PlaylistTrack.position)
        )
        tracks = [{**_track_dict(t), "position": pos} for t, pos in rows]

    return web.json_response({**_playlist_dict(p), "tracks": tracks})


async def api_update_playlist(request: web.Request) -> web.Response:
    try:
        pl_id = int(request.match_info["id"])
        body = await _json_body(request)
    except (ValueError, KeyError) as exc:
        return _err(str(exc) or "Invalid request")

    async with async_session_factory() as session:
        p = await session.get(Playlist, pl_id)
        if not p:
            return _err("Not found", 404)
        if "name" in body and str(body["name"]).strip():
            p.name = str(body["name"]).strip()
        if "tags" in body:
            p.tags = str(body["tags"]).strip() or None
        await session.commit()
        await session.refresh(p)
    return web.json_response({"ok": True, "playlist": _playlist_dict(p)})


async def api_delete_playlist(request: web.Request) -> web.Response:
    try:
        pl_id = int(request.match_info["id"])
    except ValueError:
        return _err("Invalid id")

    async with async_session_factory() as session:
        p = await session.get(Playlist, pl_id)
        if not p:
            return _err("Not found", 404)
        cover = p.cover_path
        # SQLite foreign keys are not enforced here (no PRAGMA foreign_keys=ON),
        # so ON DELETE CASCADE does not fire and the hotkey has to go by hand.
        # Leaving it is not merely untidy: playlist ids are plain rowids and
        # SQLite reuses them, so the next playlist created could inherit this
        # one's shortcut.
        hotkey = (await session.execute(
            select(Hotkey).where(Hotkey.playlist_id == pl_id)
        )).scalars().one_or_none()
        if hotkey:
            await session.delete(hotkey)
        await session.delete(p)
        await session.commit()

    if cover:
        _unlink_cover(cover)
    return web.json_response({"ok": True})


async def _append_tracks(pl_id: int, track_ids: list[int]) -> int:
    """Append tracks to a playlist, skipping ones already on it. Returns count added."""
    added = 0
    async with async_session_factory() as session:
        if not await session.get(Playlist, pl_id):
            return 0
        existing = set((await session.execute(
            select(PlaylistTrack.track_id).where(PlaylistTrack.playlist_id == pl_id)
        )).scalars().all())
        # Explicit None check: position 0 is falsy, and `or -1` here would
        # restart numbering at 0 and collide with the existing first track.
        max_pos = (await session.execute(
            select(func.max(PlaylistTrack.position)).where(PlaylistTrack.playlist_id == pl_id)
        )).scalar()
        next_pos = 0 if max_pos is None else max_pos + 1

        for track_id in track_ids:
            if track_id in existing or not await session.get(Track, track_id):
                continue
            session.add(PlaylistTrack(playlist_id=pl_id, track_id=track_id, position=next_pos))
            existing.add(track_id)
            next_pos += 1
            added += 1
        await session.commit()
    return added


async def api_playlist_add_track(request: web.Request) -> web.Response:
    try:
        pl_id = int(request.match_info["id"])
        body = await _json_body(request)
    except ValueError as exc:
        return _err(str(exc) or "Invalid request")

    # Accept either a single track_id or a list of them.
    raw_ids = body.get("track_ids")
    if raw_ids is None:
        if "track_id" not in body:
            return _err("track_id or track_ids required")
        raw_ids = [body["track_id"]]
    try:
        track_ids = [int(t) for t in raw_ids]
    except (TypeError, ValueError):
        return _err("track ids must be integers")

    async with async_session_factory() as session:
        if not await session.get(Playlist, pl_id):
            return _err("Not found", 404)

    added = await _append_tracks(pl_id, track_ids)
    if not added:
        return _err("Already in playlist", 409)
    return web.json_response({"ok": True, "added": added})


async def api_playlist_remove_track(request: web.Request) -> web.Response:
    try:
        pl_id = int(request.match_info["id"])
        track_id = int(request.match_info["track_id"])
    except ValueError:
        return _err("Invalid id")

    async with async_session_factory() as session:
        row = (await session.execute(
            select(PlaylistTrack).where(
                PlaylistTrack.playlist_id == pl_id, PlaylistTrack.track_id == track_id
            )
        )).scalars().one_or_none()
        if not row:
            return _err("Not found", 404)
        await session.delete(row)
        await session.commit()
    return web.json_response({"ok": True})


async def api_playlist_reorder(request: web.Request) -> web.Response:
    """Body: {"track_ids": [...]} — rewrites positions to match the given order."""
    try:
        pl_id = int(request.match_info["id"])
        body = await _json_body(request)
        track_ids = [int(t) for t in body.get("track_ids", [])]
    except (ValueError, TypeError):
        return _err("Invalid request")
    if not track_ids:
        return _err("track_ids required")

    async with async_session_factory() as session:
        rows = (await session.execute(
            select(PlaylistTrack).where(PlaylistTrack.playlist_id == pl_id)
        )).scalars().all()
        by_track = {r.track_id: r for r in rows}
        if set(track_ids) != set(by_track):
            return _err("track_ids must list exactly the playlist's tracks")
        # Two passes: park positions out of the way first so the unique
        # (playlist_id, position) constraint cannot trip mid-reorder.
        for offset, r in enumerate(rows):
            r.position = -1 - offset
        await session.flush()
        for pos, track_id in enumerate(track_ids):
            by_track[track_id].position = pos
        await session.commit()
    return web.json_response({"ok": True})


# --- Hotkeys ---------------------------------------------------------------
#
# The desktop app registers these with the OS, but they are stored here so a
# login carries its shortcuts to whatever machine it signs in from. Like every
# other /api/ route they sit behind the session cookie: auth.auth_middleware
# only exempts /login, /api/login and /api/logout.

# Electron accelerator grammar, loosely: zero or more modifiers then one key.
_MODIFIERS = {
    "command", "cmd", "control", "ctrl", "commandorcontrol", "cmdorctrl",
    "alt", "option", "altgr", "shift", "super", "meta",
}
_MAX_ACCELERATOR = 64


def _hotkey_dict(h: Hotkey, playlist_name: str | None = None) -> dict:
    d = {"playlist_id": h.playlist_id, "accelerator": h.accelerator}
    if playlist_name is not None:
        d["playlist_name"] = playlist_name
    return d


def _clean_accelerator(raw: object) -> str:
    """Validate an accelerator, or raise ValueError with something showable.

    The desktop app hands whatever it captured straight to Electron's
    globalShortcut, and an unparseable string there throws at registration
    time — on a machine nobody is watching. Rejecting it here means the error
    lands in the UI that produced it.
    """
    value = str(raw or "").strip()
    if not value:
        raise ValueError("accelerator is required")
    if len(value) > _MAX_ACCELERATOR:
        raise ValueError("That shortcut is too long")

    parts = [p.strip() for p in value.split("+")]
    if not all(parts):
        raise ValueError("That shortcut is not a valid key combination")

    *mods, key = parts
    if not key or key.lower() in _MODIFIERS:
        raise ValueError("A shortcut needs a key, not just modifiers")
    for mod in mods:
        if mod.lower() not in _MODIFIERS:
            raise ValueError(f"{mod!r} is not a modifier key")
    if not mods:
        # A bare key would swallow that keystroke system-wide, in every app.
        raise ValueError("Add at least one modifier (Ctrl, Alt, Shift or Super)")
    return "+".join(mods + [key])


async def api_hotkeys(_request: web.Request) -> web.Response:
    async with async_session_factory() as session:
        rows = await session.execute(
            select(Hotkey, Playlist.name)
            .join(Playlist, Playlist.id == Hotkey.playlist_id)
            .order_by(Playlist.name)
        )
        hotkeys = [_hotkey_dict(h, name) for h, name in rows]
    return web.json_response({"hotkeys": hotkeys})


async def api_set_hotkey(request: web.Request) -> web.Response:
    """Bind one accelerator to one playlist. Body: {"accelerator": "..."}"""
    try:
        pl_id = int(request.match_info["playlist_id"])
        body = await _json_body(request)
        accelerator = _clean_accelerator(body.get("accelerator"))
    except ValueError as exc:
        return _err(str(exc) or "Invalid request")

    async with async_session_factory() as session:
        if not await session.get(Playlist, pl_id):
            return _err("Not found", 404)

        # One combination, one meaning: steal it from whatever held it, so the
        # UI never has to make the user go and clear the old binding first.
        clash = (await session.execute(
            select(Hotkey).where(
                Hotkey.accelerator == accelerator, Hotkey.playlist_id != pl_id
            )
        )).scalars().one_or_none()
        if clash:
            await session.delete(clash)
            await session.flush()

        existing = (await session.execute(
            select(Hotkey).where(Hotkey.playlist_id == pl_id)
        )).scalars().one_or_none()
        if existing:
            existing.accelerator = accelerator
        else:
            session.add(Hotkey(playlist_id=pl_id, accelerator=accelerator))
        await session.commit()

    return web.json_response({"ok": True, "accelerator": accelerator})


async def api_delete_hotkey(request: web.Request) -> web.Response:
    try:
        pl_id = int(request.match_info["playlist_id"])
    except ValueError:
        return _err("Invalid id")

    async with async_session_factory() as session:
        row = (await session.execute(
            select(Hotkey).where(Hotkey.playlist_id == pl_id)
        )).scalars().one_or_none()
        if not row:
            return _err("Not found", 404)
        await session.delete(row)
        await session.commit()
    return web.json_response({"ok": True})


async def api_hotkey_trigger(request: web.Request) -> web.Response:
    """Toggle one playlist in voice. Body: {"playlist_id": int}

    This is the whole hotkey behaviour in one call, because the desktop app
    must not have to read the state, decide, and write back — two hotkey
    presses in quick succession would race and both decide "play".
    """
    cog = _cog(request)
    if not cog:
        return _err("Music cog not available", 503)
    try:
        body = await _json_body(request)
        playlist_id = int(body["playlist_id"])
    except (ValueError, KeyError, TypeError):
        return _err("playlist_id required")

    state = cog.state_dict()
    same_playlist = state["playlist_id"] == playlist_id

    if same_playlist and state["playing"] and not state["paused"]:
        await cog.pause()
        return web.json_response({"ok": True, "action": "paused"})
    if same_playlist and state["paused"]:
        await cog.resume()
        return web.json_response({"ok": True, "action": "resumed"})

    try:
        count = await cog.play_playlist(playlist_id)
    except Exception as exc:
        log.error("hotkey trigger error for playlist %s: %s", playlist_id, exc)
        return _err(str(exc), 500)
    if not count:
        return _err("That playlist has no tracks", 400)
    return web.json_response({"ok": True, "action": "playing", "track_count": count})


def _unlink_cover(filename: str) -> None:
    path = os.path.join(COVERS_DIR, os.path.basename(filename))
    try:
        if os.path.exists(path):
            os.unlink(path)
    except OSError as exc:
        log.warning("Could not remove cover %s: %s", filename, exc)


async def api_playlist_cover(request: web.Request) -> web.Response:
    try:
        pl_id = int(request.match_info["id"])
    except ValueError:
        return _err("Invalid id")

    os.makedirs(COVERS_DIR, exist_ok=True)
    async with async_session_factory() as session:
        p = await session.get(Playlist, pl_id)
        if not p:
            return _err("Not found", 404)

        reader = await request.multipart()
        field = await reader.next()
        if not field or field.name != "cover":
            return _err("cover field required")

        content_type = (field.headers.get("Content-Type") or "").split(";")[0].strip()
        if content_type not in _COVER_TYPES:
            return _err("Cover must be a JPEG, PNG, WebP, or GIF image")

        filename = f"{uuid.uuid4().hex}.{_COVER_TYPES[content_type]}"
        filepath = os.path.join(COVERS_DIR, filename)
        written = 0
        try:
            with open(filepath, "wb") as f:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > _MAX_COVER_BYTES:
                        raise ValueError("Cover image is too large (max 8 MB)")
                    f.write(chunk)
        except ValueError as exc:
            _unlink_cover(filename)
            return _err(str(exc))

        old_cover = p.cover_path
        p.cover_path = filename
        await session.commit()

    if old_cover:
        _unlink_cover(old_cover)
    return web.json_response({"ok": True, "cover_path": filename})


async def api_debug_state(request: web.Request) -> web.Response:
    """
    Read-only snapshot: what is in the database, and what a game rebuild would
    make of the guild. Exists so "why did the rebuild find nothing?" is a
    question you can answer by looking, instead of guessing.
    """
    from bot.db import Game, Player, SchedulePoll

    out: dict = {"database": {}, "guilds": []}

    async with async_session_factory() as session:
        games = (await session.execute(select(Game))).scalars().all()
        players = (await session.execute(select(Player))).scalars().all()
        polls = (await session.execute(select(SchedulePoll))).scalars().all()
        tracks = (await session.execute(select(Track))).scalars().all()
        playlists = (await session.execute(select(Playlist))).scalars().all()
        entries = (await session.execute(select(PlaylistTrack))).scalars().all()

    by_game: dict[int, int] = {}
    for pl in players:
        by_game[pl.game_id] = by_game.get(pl.game_id, 0) + 1

    out["database"] = {
        "counts": {
            "games": len(games), "players": len(players), "schedule_polls": len(polls),
            "tracks": len(tracks), "playlists": len(playlists), "playlist_entries": len(entries),
        },
        "games": [
            {
                "id": g.id, "name": g.name, "guild_id": str(g.guild_id),
                "dm_user_id": str(g.dm_user_id), "category_id": str(g.category_id),
                "game_role_id": str(g.game_role_id),
                "dm_role_id": str(g.dm_role_id) if g.dm_role_id else None,
                "players": by_game.get(g.id, 0),
            }
            for g in games
        ],
        "playlists": [
            {"id": p.id, "name": p.name, "tags": p.tags} for p in playlists
        ],
    }

    bot = request.app.get("bot")
    if not bot:
        return web.json_response(out)

    known = {g.category_id for g in games}
    wanted = {"important": "text", "scheduling": "text", "general": "text",
              "game": "voice", "private": "voice"}

    for guild in bot.guilds:
        categories = []
        for cat in guild.categories:
            found = {}
            for ch in cat.channels:
                kind = "voice" if isinstance(ch, discord.VoiceChannel) else (
                    "text" if isinstance(ch, discord.TextChannel) else "other")
                found[ch.name] = kind
            missing = [n for n, t in wanted.items() if found.get(n) != t]
            game_role = discord.utils.find(
                lambda r: r.name.lower() == f"game: {cat.name}".lower(), guild.roles)
            dm_role = discord.utils.find(
                lambda r: r.name.lower() == f"dm: {cat.name}".lower(), guild.roles)

            if cat.id in known:
                verdict = "already in database"
            elif missing:
                verdict = f"skipped — channels missing/wrong type: {', '.join(missing)}"
            elif not game_role:
                verdict = f"skipped — no role named 'Game: {cat.name}'"
            elif not dm_role:
                verdict = f"skipped — no role named 'DM: {cat.name}'"
            elif not [m for m in dm_role.members if not m.bot]:
                verdict = f"skipped — nobody holds 'DM: {cat.name}'"
            else:
                verdict = "would rebuild"

            categories.append({
                "name": cat.name, "id": str(cat.id), "channels": found,
                "game_role": game_role.name if game_role else None,
                "dm_role": dm_role.name if dm_role else None,
                "dm_role_members": [m.display_name for m in dm_role.members if not m.bot] if dm_role else [],
                "game_role_members": [m.display_name for m in game_role.members if not m.bot] if game_role else [],
                "verdict": verdict,
            })

        categories.sort(key=lambda c: c["name"].lower())
        out["guilds"].append({
            "name": guild.name, "id": str(guild.id),
            "roles": sorted(
                r.name for r in guild.roles
                if r.name.lower().startswith(("game:", "dm:"))
            ),
            "categories": categories,
        })

    return web.json_response(out)


# --- App lifecycle ---------------------------------------------------------

async def _on_startup(app: web.Application) -> None:
    app["http_client"] = aiohttp.ClientSession()


async def _on_cleanup(app: web.Application) -> None:
    await app["http_client"].close()


@web.middleware
async def _error_middleware(request: web.Request, handler):
    """Log tracebacks and answer API routes with JSON the UI can display."""
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception:
        log.exception("Unhandled error in %s %s", request.method, request.path)
        if request.path.startswith("/api/"):
            return web.json_response(
                {"ok": False, "message": "Server error — check the bot logs"}, status=500
            )
        raise


def create_app(bot=None) -> web.Application:
    app = web.Application(middlewares=[_error_middleware, auth.auth_middleware])
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    app["bot"] = bot

    auth.add_routes(app)

    app.router.add_get("/api/audio/{track_id}", api_audio_stream)
    app.router.add_get("/api/now-playing", api_now_playing)
    app.router.add_post("/api/play", api_play)
    app.router.add_post("/api/pause", api_pause)
    app.router.add_post("/api/resume", api_resume)
    app.router.add_post("/api/stop", api_stop)
    app.router.add_post("/api/skip", api_skip)
    app.router.add_post("/api/previous", api_previous)
    app.router.add_post("/api/shuffle", api_shuffle)
    app.router.add_post("/api/volume", api_volume)
    app.router.add_post("/api/device", api_device)
    app.router.add_get("/api/devices", api_devices)

    app.router.add_get("/api/playlists", api_playlists)
    app.router.add_post("/api/playlists", api_create_playlist)
    app.router.add_get("/api/playlists/{id}", api_get_playlist)
    app.router.add_put("/api/playlists/{id}", api_update_playlist)
    app.router.add_delete("/api/playlists/{id}", api_delete_playlist)
    app.router.add_post("/api/playlists/{id}/tracks", api_playlist_add_track)
    app.router.add_put("/api/playlists/{id}/tracks", api_playlist_reorder)
    app.router.add_delete("/api/playlists/{id}/tracks/{track_id}", api_playlist_remove_track)
    app.router.add_post("/api/playlists/{id}/cover", api_playlist_cover)

    app.router.add_get("/api/hotkeys", api_hotkeys)
    app.router.add_post("/api/hotkeys/trigger", api_hotkey_trigger)
    app.router.add_put("/api/hotkeys/{playlist_id}", api_set_hotkey)
    app.router.add_delete("/api/hotkeys/{playlist_id}", api_delete_hotkey)

    app.router.add_get("/api/debug/state", api_debug_state)
    app.router.add_get("/api/library/tracks", api_library_tracks)
    app.router.add_post("/api/library/import", api_library_import)
    app.router.add_delete("/api/library/tracks/{track_id}", api_library_delete)

    if os.path.isdir(WEB_ROOT):
        index_path = os.path.join(WEB_ROOT, "index.html")
        os.makedirs(COVERS_DIR, exist_ok=True)

        async def _index(_request: web.Request) -> web.FileResponse:
            # No-store: the filename never changes, but the hashed asset names
            # inside it do, so a cached shell can point at chunks that are gone.
            return web.FileResponse(index_path, headers={"Cache-Control": "no-store"})

        app.router.add_get("/", _index)
        app.router.add_static("/covers", COVERS_DIR, name="covers")

        # The built bundle. Every filename carries a content hash, so these are
        # safe to cache hard — and they stay behind the session cookie like the
        # rest of the site, because add_static sits under the auth middleware.
        if os.path.isdir(ASSETS_DIR):
            app.router.add_static("/assets", ASSETS_DIR, name="assets")
        else:
            log.warning(
                "web/assets is missing — run `npm run build` in web-src/, or the "
                "UI will load an empty page."
            )
    else:
        async def _no_ui(_request: web.Request) -> web.Response:
            return web.Response(
                text="<html><body><p>No web/ directory found.</p></body></html>",
                content_type="text/html",
            )
        app.router.add_get("/", _no_ui)

    return app


async def run_web_server(host: str = "0.0.0.0", port: int = 5000, bot=None) -> web.AppRunner:
    if not auth.is_configured():
        raise RuntimeError(
            "WEB_PASSWORD is not set. The web player is refusing to start rather "
            "than serve an unauthenticated UI — set WEB_PASSWORD in .env, or set "
            "WEB_AUTH=off if you deliberately want it open on a trusted network."
        )

    app = create_app(bot=bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info(
        "Web UI: http://%s:%d (login %s)",
        host, port, "required" if auth.is_enabled() else "DISABLED — WEB_AUTH=off",
    )
    return runner
