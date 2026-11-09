"""User-facing brand text and runtime asset locations."""

from __future__ import annotations

from pathlib import Path
import sys


INTERFACE_NAME = "超级奶蛙助手"
SOFTWARE_NAME = "奶蛙的荣光"
APP_VERSION = "1.0.0"


def application_root() -> Path:
    """Return the project root or PyInstaller's bundled data directory."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def asset_path(*parts: str) -> Path:
    """Resolve a file under assets/ without depending on the current directory."""
    return application_root().joinpath("assets", *parts)
