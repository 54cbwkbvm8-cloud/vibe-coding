"""截图缩放和 DeepSeek 图片 data URL 编码。"""

from __future__ import annotations

import base64

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt


MAX_IMAGE_LONG_EDGE = 1600
MAX_IMAGE_BYTES = 32 * 1024 * 1024


class ImagePayloadError(RuntimeError):
    """表示图片无效或编码后超过接口限制。"""


def resize_for_api(image: QImage, max_edge: int = MAX_IMAGE_LONG_EDGE) -> QImage:
    if image.isNull():
        raise ImagePayloadError("截图图片为空。")
    if max(image.width(), image.height()) <= max_edge:
        return image.copy()
    return image.scaled(
        max_edge,
        max_edge,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _encode(image: QImage, image_format: str, quality: int = -1) -> bytes:
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise ImagePayloadError("无法创建内存图片缓冲区。")
    if not image.save(buffer, image_format, quality):
        raise ImagePayloadError("图片内存编码失败。")
    return bytes(buffer.data())


def image_to_data_url(
    image: QImage,
    max_edge: int = MAX_IMAGE_LONG_EDGE,
) -> str:
    """缩放到长边 1600，并生成不含明文日志的 PNG/JPEG data URL。"""
    resized = resize_for_api(image, max_edge)
    image_bytes = _encode(resized, "PNG")
    mime_type = "image/png"

    if len(image_bytes) > 8 * 1024 * 1024:
        image_bytes = _encode(resized, "JPEG", 90)
        mime_type = "image/jpeg"

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ImagePayloadError("截图编码后仍然过大，无法发送。")

    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
