"""Minimal web server for the media player UI. Serves static files and stub API routes for future bot integration."""
import os
from aiohttp import web

# Directory for static files (HTML, JS, CSS). Relative to project root.
WEB_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def _stub_json(data: dict, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


# --- Stub API routes (hook these to the bot later) ---

async def api_now_playing(_request: web.Request) -> web.Response:
    """Current track and queue. Replace with bot state when music cog exists."""
    return _stub_json({
        "playing": False,
        "current": None,
        "queue": [],
        "position_sec": 0,
        "duration_sec": 0,
    })


async def api_play(request: web.Request) -> web.Response:
    """Start playing a playlist (e.g. body: { "playlist_id": 1, "shuffle": false })."""
    try:
        body = await request.json() if request.can_read_body() else {}
    except Exception:
        body = {}
    # Stub: not implemented until music cog is wired
    return _stub_json({"ok": False, "message": "Not implemented"}, status=501)


async def api_pause(_request: web.Request) -> web.Response:
    """Pause playback."""
    return _stub_json({"ok": False, "message": "Not implemented"}, status=501)


async def api_resume(_request: web.Request) -> web.Response:
    """Resume playback."""
    return _stub_json({"ok": False, "message": "Not implemented"}, status=501)


async def api_stop(_request: web.Request) -> web.Response:
    """Stop and disconnect."""
    return _stub_json({"ok": False, "message": "Not implemented"}, status=501)


async def api_skip(_request: web.Request) -> web.Response:
    """Skip to next track."""
    return _stub_json({"ok": False, "message": "Not implemented"}, status=501)


async def api_playlists(_request: web.Request) -> web.Response:
    """List playlists (for Library)."""
    return _stub_json({"playlists": []})


def create_app() -> web.Application:
    app = web.Application()
    # API routes (stubs for UI to call; hook to bot later)
    app.router.add_get("/api/now-playing", api_now_playing)
    app.router.add_post("/api/play", api_play)
    app.router.add_post("/api/pause", api_pause)
    app.router.add_post("/api/resume", api_resume)
    app.router.add_post("/api/stop", api_stop)
    app.router.add_post("/api/skip", api_skip)
    app.router.add_get("/api/playlists", api_playlists)
    # Static files: serve from web/
    if os.path.isdir(WEB_ROOT):
        app.router.add_static("/", WEB_ROOT, name="static", show_index=True)
    else:
        async def index(_request: web.Request) -> web.Response:
            return web.Response(
                text="<html><body><p>Create a <code>web/</code> directory in the project root and add your media player UI (e.g. <code>index.html</code>).</p></body></html>",
                content_type="text/html",
            )
        app.router.add_get("/", index)
    return app


async def run_web_server(host: str = "127.0.0.1", port: int = 5000 , debug: bool = True) -> web.AppRunner:
    """Create, start, and run the aiohttp app. Returns the runner for cleanup."""
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"Media player web UI: http://{host}:{port}")
    return runner
