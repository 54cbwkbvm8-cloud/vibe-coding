"""Qt loaders for the multi-resolution logo and Windows application icon."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from ..branding import asset_path
from ..personalization_runtime import current_brand_runtime


LOGO_LOGICAL_SIZE = 28


@lru_cache(maxsize=8)
def load_logo_icon(path: str = "") -> QIcon:
    """Load 1x/2x/3x logo images into one DPI-aware QIcon."""
    icon = QIcon()
    for scale in (1, 2, 3):
        source_path = path or str(
            asset_path("brand", f"logo@{scale}x.png")
        )
        pixmap = QPixmap(source_path)
        if pixmap.isNull():
            raise FileNotFoundError(f"Missing logo asset for scale {scale}x")
        if path:
            pixmap = pixmap.scaled(
                LOGO_LOGICAL_SIZE * scale,
                LOGO_LOGICAL_SIZE * scale,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        pixmap.setDevicePixelRatio(float(scale))
        icon.addPixmap(pixmap)
    return icon


@lru_cache(maxsize=8)
def load_app_icon(path: str = "") -> QIcon:
    """Load the multi-size Windows ICO used by the window, tray, and exe."""
    source = path or str(
        current_brand_runtime().app_icon_path
    )
    icon = QIcon(source)
    if icon.isNull():
        raise FileNotFoundError("Missing assets/brand/app_icon.ico")
    return icon


def title_logo_pixmap() -> QPixmap:
    """Return the logo at its logical title-bar size for the current display."""
    screen = QApplication.primaryScreen()
    device_ratio = screen.devicePixelRatio() if screen is not None else 1.0
    custom_path = current_brand_runtime().title_logo_path
    return load_logo_icon(
        str(custom_path) if custom_path is not None else ""
    ).pixmap(
        QSize(LOGO_LOGICAL_SIZE, LOGO_LOGICAL_SIZE),
        device_ratio,
    )
