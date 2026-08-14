"""Resolve project paths for development and PyInstaller builds."""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """
    Directory that contains `templates/` and `static/`.

    - Dev: project root (parent of the `app` package)
    - PyInstaller onedir/onefile: sys._MEIPASS (bundled data extract dir)
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    # app/paths.py -> app/ -> project root
    return Path(__file__).resolve().parent.parent


def templates_dir() -> Path:
    return app_root() / "templates"


def static_dir() -> Path:
    return app_root() / "static"


def default_data_dir() -> Path:
    """Writable data next to the executable when frozen, else ./data."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path("data")
