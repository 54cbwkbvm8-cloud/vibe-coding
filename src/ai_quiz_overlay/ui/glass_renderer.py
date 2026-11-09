"""Low-overhead Qt painting for the liquid-glass window surface."""

from __future__ import annotations

from functools import lru_cache
import random

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

from ..theme import THEME, glass_alpha


@lru_cache(maxsize=1)
def _noise_texture() -> QPixmap:
    size = 96
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    rng = random.Random(7)
    for y in range(size):
        for x in range(size):
            alpha = rng.randint(0, 9)
            if alpha:
                image.setPixelColor(x, y, QColor(255, 255, 255, alpha))
    return QPixmap.fromImage(image)


def _glass_path(rect: QRectF) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, THEME.window_radius, THEME.window_radius)
    return path


def _color_with_alpha(name: str, alpha: int) -> QColor:
    color = QColor(name)
    color.setAlpha(alpha)
    return color


def draw_glass_window(
    painter: QPainter,
    bounds: QRect,
    *,
    opacity: float,
    acrylic_active: bool,
    active: bool = True,
    background_pixmap: QPixmap | None = None,
) -> None:
    """Paint the frosted layer, highlight, noise, and inner edge."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    panel = QRectF(bounds).adjusted(0.5, 0.5, -0.5, -0.5)
    radius = THEME.window_radius

    path = _glass_path(panel)
    painter.setClipPath(path)

    if background_pixmap is not None and not background_pixmap.isNull():
        painter.drawPixmap(bounds, background_pixmap)

    base_alpha = glass_alpha(opacity)
    if acrylic_active:
        base_alpha = round(base_alpha * 0.55)

    fill = QLinearGradient(panel.topLeft(), panel.bottomRight())
    fill.setColorAt(
        0.0,
        _color_with_alpha(
            THEME.glass_top,
            max(120, round(base_alpha * (1.0 if active else 0.9))),
        ),
    )
    fill.setColorAt(
        0.58,
        _color_with_alpha(THEME.glass_bottom, base_alpha),
    )
    fill.setColorAt(
        1.0,
        QColor(22, 27, 54, max(145, round(base_alpha * 0.96))),
    )
    painter.fillPath(path, QBrush(fill))

    accent_glow = QRadialGradient(
        QPointF(panel.right() - 54, panel.bottom() - 30),
        150,
    )
    accent_glow.setColorAt(0.0, QColor(240, 197, 104, 34))
    accent_glow.setColorAt(1.0, QColor(240, 197, 104, 0))
    painter.fillPath(path, QBrush(accent_glow))

    painter.setOpacity(0.34)
    painter.setBrushOrigin(panel.topLeft().toPoint())
    painter.fillPath(path, QBrush(_noise_texture()))
    painter.setOpacity(1.0)

    top_sheen = QLinearGradient(panel.topLeft(), QPointF(panel.left(), panel.top() + 150))
    top_sheen.setColorAt(0.0, QColor(255, 255, 255, 54))
    top_sheen.setColorAt(0.42, QColor(255, 255, 255, 14))
    top_sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillPath(path, QBrush(top_sheen))

    painter.setClipping(False)
    border = QLinearGradient(panel.topLeft(), panel.bottomRight())
    border.setColorAt(0.0, QColor(255, 255, 255, 148))
    border.setColorAt(0.42, QColor(197, 211, 247, 58))
    border.setColorAt(0.72, QColor(240, 197, 104, 90))
    border.setColorAt(1.0, QColor(255, 255, 255, 58))
    painter.setPen(QPen(QBrush(border), 1.15))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)

    inner = panel.adjusted(1.1, 1.1, -1.1, -1.1)
    inner_path = QPainterPath()
    inner_path.addRoundedRect(inner, radius - 1, radius - 1)
    painter.setPen(QPen(QColor(0, 0, 0, 48), 0.8))
    painter.drawPath(inner_path)
    painter.restore()
