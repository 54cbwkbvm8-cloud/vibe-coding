"""逻辑选区到物理截图像素的坐标换算。"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize


def selection_to_image_rect(
    selection: QRect,
    overlay_size: QSize,
    image_size: QSize,
) -> QRect:
    """把界面逻辑坐标映射到截图 QImage 的物理像素坐标。"""
    normalized = selection.normalized().intersected(
        QRect(0, 0, overlay_size.width(), overlay_size.height())
    )
    if (
        overlay_size.width() <= 0
        or overlay_size.height() <= 0
        or normalized.width() <= 0
        or normalized.height() <= 0
    ):
        return QRect()

    scale_x = image_size.width() / overlay_size.width()
    scale_y = image_size.height() / overlay_size.height()

    left = round(normalized.left() * scale_x)
    top = round(normalized.top() * scale_y)
    right = round((normalized.right() + 1) * scale_x)
    bottom = round((normalized.bottom() + 1) * scale_y)

    return QRect(left, top, right - left, bottom - top).intersected(
        QRect(0, 0, image_size.width(), image_size.height())
    )
