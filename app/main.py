"""DigiKam Web – FastAPI application entry point."""

from __future__ import annotations

import argparse
from datetime import datetime
import asyncio
import os
import signal
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

# Windows: ProactorEventLoop raises ConnectionResetError (WinError 10054) on client
# disconnect and often blocks graceful shutdown with uvicorn/HTTPS.
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

import uvicorn
from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import albums, auth_routes, config_routes, dates, images, tags
from app.api.deps import get_optional_user, set_globals
from app.config import settings
from app.db.app_db import AppDB
from app.repositories.digikam_repo import DigikamRepository
from app.services.path_resolver import PathResolver
from app.services.thumbnail import ThumbnailService
from app.paths import templates_dir, static_dir, default_data_dir


def _format_local_ts(dt: datetime | None = None) -> str:
    """
    Locale-independent local timestamp.
    Avoid %Z (can expand to long translated names, e.g. Chinese Windows).
    Use numeric offset: 2026-08-15 20:53:00 UTC-10:00
    """
    dt = dt or datetime.now().astimezone()
    if dt.tzinfo is None:
        dt = dt.astimezone()
    off = dt.strftime("%z") or ""
    if len(off) == 5:  # e.g. -1000
        off = f"{off[:3]}:{off[3:]}"
    return f"{dt.strftime('%Y-%m-%d %H:%M:%S')} UTC{off}"


def _log(msg: str, *, error: bool = False) -> None:
    """Console line with local datetime prefix."""
    stream = sys.stderr if error else sys.stdout
    print(f"[{_format_local_ts()}] {msg}", file=stream)


def _uvicorn_log_config() -> dict:
    """Access/error logs with the same timestamp style as _log."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(asctime)s %(levelprefix)s %(message)s",
                "use_colors": None,
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": '%(asctime)s %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        },
    }



def _install_loop_exception_filter() -> None:
    """Suppress connection-reset noise (especially WinError 10054)."""

    def _handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
        exc = context.get("exception")
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        if isinstance(exc, OSError):
            winerror = getattr(exc, "winerror", None)
            if winerror in (10054, 10053, 10038):
                return
            errno_mod = __import__("errno")
            if getattr(exc, "errno", None) in (
                getattr(errno_mod, "ECONNRESET", -1),
                getattr(errno_mod, "EPIPE", -1),
                getattr(errno_mod, "ECONNABORTED", -1),
            ):
                return
        msg = context.get("message", "") or ""
        if "connection_lost" in msg or "_call_connection_lost" in msg:
            if exc is None or isinstance(exc, (ConnectionError, OSError)):
                return
        loop.default_exception_handler(context)

    try:
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(_handler)
    except RuntimeError:
        # No running loop yet – will retry from lifespan
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown (replaces deprecated on_event)."""
    app_db_path = settings.app_db_path
    if not app_db_path.exists():
        _log(
            f"ERROR: Application database not found at {app_db_path}.\n"
            "Run the init command first:\n"
            "  python -m app.cli.init_cmd init --digikam-db /path/to/digikam4.db",
            error=True,
        )
        sys.exit(1)

    app_db = AppDB(app_db_path)
    app_db.init_schema()

    secret = app_db.get_config("secret_key")
    if secret:
        settings.secret_key = secret

    digikam_path = app_db.get_config("digikam_db_path")
    if not digikam_path:
        _log("ERROR: digikam_db_path not set in app database. Re-run init.", error=True)
        sys.exit(1)

    digikam = DigikamRepository(Path(digikam_path))
    resolver = PathResolver(app_db, digikam)

    cache_dir = default_data_dir() / "thumb_cache"
    thumbs = ThumbnailService(cache_dir=cache_dir, prefer_webp=True)

    set_globals(app_db, digikam, resolver, thumbs)
    from app.map_links import ensure_map_templates
    ensure_map_templates(app_db)
    _install_loop_exception_filter()
    _log(f"DigiKam Web ready – core DB: {digikam_path}")

    yield

    # Shutdown hooks (if needed later) go here


app = FastAPI(title="DigiKam Web", docs_url=None, redoc_url=None, lifespan=lifespan)
templates = Jinja2Templates(directory=str(templates_dir()))

_static = static_dir()
if _static.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")

app.include_router(auth_routes.router)
app.include_router(albums.router)
app.include_router(images.router)
app.include_router(dates.router)
app.include_router(tags.router)
app.include_router(config_routes.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user=Depends(get_optional_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"username": user["username"]},
    )


def run() -> None:
    """Entry point for `python -m app.main`."""
    parser = argparse.ArgumentParser(description="DigiKam Web HTTPS server")
    parser.add_argument(
        "--host",
        default=None,
        help="Bind address (default: 0.0.0.0 = all interfaces). "
             "Use 127.0.0.1 for localhost-only.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Listen port (default: {settings.port})",
    )
    parser.add_argument(
        "--cert",
        type=Path,
        default=None,
        help="TLS certificate file (overrides app DB / env)",
    )
    parser.add_argument(
        "--key",
        type=Path,
        default=None,
        help="TLS private key file (overrides app DB / env)",
    )
    args = parser.parse_args()

    host = args.host or settings.host
    port = args.port or settings.port

    app_db_path = settings.app_db_path
    cert = args.cert or settings.tls_cert
    key = args.key or settings.tls_key

    if app_db_path.exists():
        db = AppDB(app_db_path)
        if not cert:
            c = db.get_config("tls_cert")
            if c:
                cert = Path(c)
        if not key:
            k = db.get_config("tls_key")
            if k:
                key = Path(k)

    if not cert or not key:
        _log(
            "ERROR: TLS certificate and key are required.\n"
            "Provide them via --cert/--key, environment variables\n"
            "DIGIKAM_WEB_TLS_CERT / DIGIKAM_WEB_TLS_KEY, or store them in the app DB at init.",
            error=True,
        )
        sys.exit(1)

    if not Path(cert).is_file() or not Path(key).is_file():
        _log(f"ERROR: TLS files not found: cert={cert} key={key}", error=True)
        sys.exit(1)

    _log(f"Listening on https://{host}:{port}/")
    if host in ("0.0.0.0", "::"):
        _log("  (bound to all interfaces – reachable from LAN / Internet if firewall allows)")
    else:
        _log(f"  (bound to {host} only)")
    _log("Press Ctrl+C to stop (press again to force exit).")

    import logging

    log_config = _uvicorn_log_config()
    config = uvicorn.Config(
        "app.main:app",
        host=host,
        port=port,
        ssl_certfile=str(cert),
        ssl_keyfile=str(key),
        reload=False,
        log_level="info",
        log_config=log_config,
        timeout_graceful_shutdown=3,
        timeout_keep_alive=5,
    )

    # Force locale-independent asctime on uvicorn formatters (no translated %Z)
    def _fmt_time(self, record, datefmt=None):  # noqa: ARG001
        return _format_local_ts(datetime.fromtimestamp(record.created).astimezone())

    logging.Formatter.formatTime = _fmt_time  # type: ignore[method-assign]

    server = uvicorn.Server(config)

    force_exit_armed = {"n": 0}

    def _force_exit_later() -> None:
        def _kill() -> None:
            _log("Shutdown is taking too long – forcing exit.", error=True)
            os._exit(0)

        t = threading.Timer(4.0, _kill)
        t.daemon = True
        t.start()

    def _handle_signal(signum, frame) -> None:
        force_exit_armed["n"] += 1
        if force_exit_armed["n"] == 1:
            _log("Shutting down…")
            server.should_exit = True
            server.force_exit = True
            _force_exit_later()
        else:
            _log("Force exit.")
            os._exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    try:
        signal.signal(signal.SIGTERM, _handle_signal)
    except Exception:
        pass

    try:
        server.run()
    except KeyboardInterrupt:
        _log("Shutting down…")
        server.should_exit = True


if __name__ == "__main__":
    run()
