"""小窗内的待发送截图缩略图。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QToolButton,
    QWidget,
)


class ScreenshotPreview(QWidget):
    """只在内存中持有当前待发送 QImage。"""

    remove_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image: QImage | None = None
        self.setObjectName("screenshotPreview")
        self.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self.thumbnail = QLabel()
        self.thumbnail.setObjectName("screenshotThumbnail")
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setFixedSize(132, 76)

        caption = QLabel("截图已附加")
        caption.setObjectName("sectionLabel")

        self.remove_button = QToolButton()
        self.remove_button.setObjectName("deleteScreenshotButton")
        self.remove_button.setText("删除")
        self.remove_button.setToolTip("删除截图")
        self.remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit())

        layout.addWidget(self.thumbnail)
        layout.addWidget(caption)
        layout.addStretch()
        layout.addWidget(self.remove_button)

    def set_image(self, image: QImage) -> None:
        self._image = image.copy()
        pixmap = QPixmap.fromImage(self._image)
        preview = pixmap.scaled(
            128,
            72,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.thumbnail.setPixmap(preview)
        self.show()

    def image(self) -> QImage | None:
        return self._image.copy() if self._image is not None else None

    def clear_image(self) -> None:
        self._image = None
        self.thumbnail.clear()
        self.hide()
