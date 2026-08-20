"""Login and session auth for the web player.

One shared password, held in the environment; a successful login hands back a
signed cookie that carries its own expiry, so nothing is stored server-side and
sessions survive a bot restart as long as WEB_SECRET_KEY is set.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from urllib.parse import quote

from aiohttp import web

log = logging.getLogger(__name__)

COOKIE_NAME = "bard_session"
SESSION_TTL = 30 * 24 * 3600

# Reachable without a session: the login page itself, and the endpoints that
# start and end a session. Everything else — including /covers — needs one.
_PUBLIC_PATHS = {"/login", "/api/login", "/api/logout"}

# Failed logins per client, for the lockout below.
_MAX_FAILURES = 8
_FAILURE_WINDOW = 900
_failures: dict[str, list[float]] = {}

_generated_secret: str | None = None


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def is_enabled() -> bool:
    """Auth is on unless explicitly turned off (WEB_AUTH=off) for local-only use."""
    return _env("WEB_AUTH", "on").lower() not in ("off", "0", "false", "no")


def password() -> str:
    return os.environ.get("WEB_PASSWORD", "")


def username() -> str:
    return _env("WEB_USERNAME", "bard")


def is_configured() -> bool:
    return not is_enabled() or bool(password())


def _secret() -> bytes:
    """Signing key. A generated one works, but every restart signs out everybody."""
    global _generated_secret
    configured = _env("WEB_SECRET_KEY")
    if configured:
        return configured.encode()
    if _generated_secret is None:
        _generated_secret = secrets.token_hex(32)
        log.warning(
            "WEB_SECRET_KEY is not set — using a random key, so every restart "
            "signs out all browsers. Set WEB_SECRET_KEY in .env to keep sessions."
        )
    return _generated_secret.encode()


# --- Tokens ---------------------------------------------------------------

def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def _make_token(user: str, ttl: int = SESSION_TTL) -> str:
    payload = f"{user}:{int(time.time()) + ttl}"
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    return f"{encoded}.{_sign(payload)}"


def _read_token(token: str) -> str | None:
    """Return the username a token vouches for, or None if it is bad or expired."""
    try:
        encoded, signature = token.split(".", 1)
        padding = "=" * (-len(encoded) % 4)
        payload = base64.urlsafe_b64decode(encoded + padding).decode()
        user, expires = payload.rsplit(":", 1)
    except (ValueError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    try:
        if int(expires) < time.time():
            return None
    except ValueError:
        return None
    # A password change should not leave old cookies valid forever, and neither
    # should a renamed user.
    return user if user == username() else None


def session_user(request: web.Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    return _read_token(token) if token else None


# --- Cookies --------------------------------------------------------------

def _client_ip(request: web.Request) -> str:
    """Behind cloudflared the peer address is the tunnel, so prefer its headers."""
    for header in ("CF-Connecting-IP", "X-Forwarded-For"):
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.remote or "unknown"


def _is_https(request: web.Request) -> bool:
    forwarded = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip().lower()
    return forwarded == "https" if forwarded else request.secure


def _cookie_secure(request: web.Request) -> bool:
    """`auto` keeps plain-HTTP LAN access working while still hardening HTTPS."""
    mode = _env("WEB_COOKIE_SECURE", "auto").lower()
    if mode in ("on", "1", "true", "yes"):
        return True
    if mode in ("off", "0", "false", "no"):
        return False
    return _is_https(request)


def _set_cookie(response: web.Response, request: web.Request, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=SESSION_TTL,
        httponly=True,
        # Lax is what keeps a cross-site POST from riding this cookie; the UI
        # only ever calls the API from its own origin, so nothing needs more.
        samesite="Lax",
        secure=_cookie_secure(request),
        path="/",
    )


# --- Lockout --------------------------------------------------------------

def _locked_out(client: str) -> bool:
    cutoff = time.time() - _FAILURE_WINDOW
    recent = [t for t in _failures.get(client, []) if t > cutoff]
    if recent:
        _failures[client] = recent
    else:
        _failures.pop(client, None)
    return len(recent) >= _MAX_FAILURES


def _record_failure(client: str) -> None:
    _failures.setdefault(client, []).append(time.time())


# --- Handlers -------------------------------------------------------------

def _login_url(request: web.Request) -> str:
    target = request.path_qs
    if target in ("/", "") or target.startswith("/login"):
        return "/login"
    return f"/login?next={quote(target, safe='')}"


async def login_page(request: web.Request) -> web.StreamResponse:
    if session_user(request):
        raise web.HTTPFound(_safe_next(request.query.get("next")))
    from bot.web_server import WEB_ROOT  # local import: avoids a circular import

    path = os.path.join(WEB_ROOT, "login.html")
    if not os.path.isfile(path):
        return web.Response(text="Login page missing", status=500)
    return web.FileResponse(path, headers={"Cache-Control": "no-store"})


def _safe_next(value: str | None) -> str:
    """Only same-origin paths — an open redirect on a login page is a phishing gift."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return "/"


async def api_login(request: web.Request) -> web.Response:
    if not is_enabled():
        return web.json_response({"ok": True, "redirect": "/"})

    client = _client_ip(request)
    if _locked_out(client):
        return web.json_response(
            {"ok": False, "message": "Too many attempts — wait 15 minutes and try again."},
            status=429,
        )

    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError
    except Exception:
        return web.json_response({"ok": False, "message": "Invalid request"}, status=400)

    expected = password()
    if not expected:
        return web.json_response(
            {"ok": False, "message": "Server has no WEB_PASSWORD set"}, status=503
        )

    given_user = str(body.get("username", "")).strip()
    given_pass = str(body.get("password", ""))
    # Both comparisons run every time so a wrong username is not faster to
    # reject than a wrong password.
    user_ok = hmac.compare_digest(given_user, username())
    pass_ok = hmac.compare_digest(given_pass, expected)
    if not (user_ok and pass_ok):
        _record_failure(client)
        log.warning("Failed web login from %s (user %r)", client, given_user)
        return web.json_response(
            {"ok": False, "message": "Incorrect username or password"}, status=401
        )

    _failures.pop(client, None)
    log.info("Web login from %s", client)
    response = web.json_response({"ok": True, "redirect": _safe_next(body.get("next"))})
    _set_cookie(response, request, _make_token(username()))
    return response


async def api_logout(request: web.Request) -> web.Response:
    response = web.json_response({"ok": True, "redirect": "/login"})
    response.del_cookie(COOKIE_NAME, path="/")
    return response


async def api_session(request: web.Request) -> web.Response:
    user = session_user(request)
    return web.json_response({
        "ok": True,
        "auth_enabled": is_enabled(),
        "user": user if is_enabled() else None,
    })


# --- Middleware -----------------------------------------------------------

@web.middleware
async def auth_middleware(request: web.Request, handler):
    if not is_enabled() or request.path in _PUBLIC_PATHS or session_user(request):
        return await handler(request)
    if request.path.startswith("/api/"):
        return web.json_response({"ok": False, "message": "Not signed in"}, status=401)
    raise web.HTTPFound(_login_url(request))


def add_routes(app: web.Application) -> None:
    app.router.add_get("/login", login_page)
    app.router.add_post("/api/login", api_login)
    app.router.add_post("/api/logout", api_logout)
    app.router.add_get("/api/session", api_session)
