"""窗口位置和尺寸的跨屏恢复规则。"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize

from ..config import WindowGeometry


MIN_VISIBLE_WIDTH = 80
MIN_VISIBLE_HEIGHT = 80


def restore_window_rect(
    saved: WindowGeometry | None,
    screens: list[QRect],
    default_size: QSize,
) -> QRect:
    """恢复已保存位置；完全离屏时重新居中到主屏。"""
    if saved is None:
        return _center_rect(default_size, screens)

    width = max(380, saved.width)
    height = max(460, saved.height)
    candidate = QRect(saved.x, saved.y, width, height)

    best_screen: QRect | None = None
    best_overlap = 0
    for screen in screens:
        overlap = candidate.intersected(screen)
        area = max(0, overlap.width()) * max(0, overlap.height())
        if area > best_overlap:
            best_overlap = area
            best_screen = screen

    if best_screen is None:
        return _center_rect(default_size, screens)

    width = min(width, best_screen.width())
    height = min(height, best_screen.height())
    visible = candidate.intersected(best_screen)
    if (
        visible.width() < MIN_VISIBLE_WIDTH
        or visible.height() < MIN_VISIBLE_HEIGHT
    ):
        return _center_rect(default_size, screens)

    x = min(max(saved.x, best_screen.left()), best_screen.right() - width + 1)
    y = min(max(saved.y, best_screen.top()), best_screen.bottom() - height + 1)
    return QRect(x, y, width, height)


def _center_rect(default_size: QSize, screens: list[QRect]) -> QRect:
    if not screens:
        return QRect(0, 0, default_size.width(), default_size.height())
    screen = screens[0]
    width = min(default_size.width(), screen.width())
    height = min(default_size.height(), screen.height())
    x = screen.left() + (screen.width() - width) // 2
    y = screen.top() + (screen.height() - height) // 2
    return QRect(x, y, width, height)
