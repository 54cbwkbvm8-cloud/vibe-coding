"""Interactive square/circle crop dialog for personalized icon assets."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..personalization_runtime import current_brand_runtime
from ..services.personalization_assets import (
    ICON_MASTER_SIZE,
    MIN_HIGH_DPI_CROP_EDGE,
    masked_circle,
    render_square_crop,
)
from ..theme import APP_STYLE
from .brand_assets import load_app_icon


class CropCanvas(QWidget):
    changed = Signal()

    def __init__(self, image, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image = image
        self._zoom = 1.0
        self._offset = QPointF(0, 0)
        self._drag_origin: QPointF | None = None
        self._drag_offset = QPointF(0, 0)
        self.setMinimumSize(360, 360)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet(
            "background-color: rgba(8, 12, 24, 220);"
            "border: 1px solid rgba(255,255,255,45);"
            "border-radius: 16px;"
        )

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(1.0, min(4.0, float(zoom)))
        self._clamp_offset()
        self.update()
        self.changed.emit()

    def reset_crop(self) -> None:
        self._zoom = 1.0
        self._offset = QPointF(0, 0)
        self._clamp_offset()
        self.update()
        self.changed.emit()

    def _cover_scale(self) -> float:
        if self._image.isNull() or self.width() <= 0 or self.height() <= 0:
            return 1.0
        return max(
            self.width() / self._image.width(),
            self.height() / self._image.height(),
        ) * self._zoom

    def _clamp_offset(self) -> None:
        scale = self._cover_scale()
        content_width = self._image.width() * scale
        content_height = self._image.height() * scale
        min_x = min(0.0, self.width() - content_width)
        min_y = min(0.0, self.height() - content_height)
        self._offset.setX(
            min(0.0, max(min_x, self._offset.x()))
        )
        self._offset.setY(
            min(0.0, max(min_y, self._offset.y()))
        )

    def crop_rect_in_source(self) -> QRectF:
        scale = self._cover_scale()
        source_x = -self._offset.x() / scale
        source_y = -self._offset.y() / scale
        source_width = self.width() / scale
        source_height = self.height() / scale
        return QRectF(
            source_x,
            source_y,
            source_width,
            source_height,
        )

    def crop_source_edge(self) -> float:
        crop = self.crop_rect_in_source()
        return min(crop.width(), crop.height())

    def render_result(self) -> QImage:
        return render_square_crop(
            self._image,
            self.crop_rect_in_source(),
            ICON_MASTER_SIZE,
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setClipRect(self.rect().adjusted(1, 1, -1, -1))
        scale = self._cover_scale()
        target = QRectF(
            self._offset.x(),
            self._offset.y(),
            self._image.width() * scale,
            self._image.height() * scale,
        )
        painter.drawImage(target, self._image)
        painter.setClipping(False)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.position()
            self._drag_offset = QPointF(self._offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is not None:
            delta = event.position() - self._drag_origin
            self._offset = self._drag_offset + delta
            self._clamp_offset()
            self.update()
            self.changed.emit()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y() / 1200
        self.set_zoom(self._zoom + delta)
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._clamp_offset()
        self.changed.emit()


class ImageCropDialog(QDialog):
    def __init__(self, image, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            current_brand_runtime().dialog_title("选择图标裁剪")
        )
        self.setWindowIcon(
            load_app_icon(
                str(current_brand_runtime().app_icon_path)
            )
        )
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setStyleSheet(APP_STYLE)
        self.resize(820, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        title = QLabel("调整图标位置")
        title.setObjectName("settingsGroupTitle")
        layout.addWidget(title)
        hint = QLabel("拖动图片调整位置，滚轮或滑块缩放。")
        hint.setObjectName("settingsHint")
        layout.addWidget(hint)

        previews = QHBoxLayout()
        previews.setSpacing(16)
        self.square_preview = QLabel()
        self.square_preview.setFixedSize(150, 150)
        self.square_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.circle_preview = QLabel()
        self.circle_preview.setFixedSize(150, 150)
        self.circle_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for label, caption_text in (
            (self.square_preview, "方形"),
            (self.circle_preview, "圆形"),
        ):
            column = QVBoxLayout()
            caption = QLabel(caption_text)
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            column.addWidget(label, 0, Qt.AlignmentFlag.AlignCenter)
            column.addWidget(caption)
            previews.addLayout(column)
        previews.addStretch()
        layout.addLayout(previews)

        self.canvas = CropCanvas(image, self)
        layout.addWidget(self.canvas, 1)

        zoom_row = QHBoxLayout()
        zoom_label = QLabel("缩放")
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(100, 400)
        self.zoom_slider.setValue(100)
        self.zoom_value = QLabel("1.0×")
        self.zoom_value.setMinimumWidth(48)
        zoom_row.addWidget(zoom_label)
        zoom_row.addWidget(self.zoom_slider, 1)
        zoom_row.addWidget(self.zoom_value)
        layout.addLayout(zoom_row)

        self.warning_label = QLabel()
        self.warning_label.setObjectName("settingsHint")
        self.warning_label.setWordWrap(True)
        layout.addWidget(self.warning_label)

        buttons = QHBoxLayout()
        reset_button = QPushButton("居中")
        reset_button.setObjectName("secondaryButton")
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("secondaryButton")
        accept_button = QPushButton("使用此裁剪")
        accept_button.setObjectName("sendButton")
        buttons.addWidget(reset_button)
        buttons.addStretch()
        buttons.addWidget(cancel_button)
        buttons.addWidget(accept_button)
        layout.addLayout(buttons)

        self.zoom_slider.valueChanged.connect(
            lambda value: self.canvas.set_zoom(value / 100)
        )
        reset_button.clicked.connect(self._reset)
        cancel_button.clicked.connect(self.reject)
        accept_button.clicked.connect(self.accept)
        self.canvas.changed.connect(self._refresh_previews)
        self._refresh_previews()

    def square_image(self):
        return self._square_image

    def _reset(self) -> None:
        self.zoom_slider.setValue(100)
        self.canvas.reset_crop()
        self._refresh_previews()

    def _refresh_previews(self) -> None:
        square = self.canvas.render_result()
        self._square_image = square
        square_preview = QPixmap.fromImage(square).scaled(
            140,
            140,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        circle = masked_circle(square, 512)
        circle_preview = QPixmap.fromImage(circle).scaled(
            140,
            140,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.square_preview.setPixmap(square_preview)
        self.circle_preview.setPixmap(circle_preview)
        edge = self.canvas.crop_source_edge()
        if edge < MIN_HIGH_DPI_CROP_EDGE:
            self.warning_label.setText(
                "当前裁剪区域小于 320×320 像素，200% 缩放或 160 px "
                "悬浮球下可能发糊。"
            )
        else:
            self.warning_label.setText("")
        self.zoom_value.setText(f"{self.canvas.zoom:.1f}×")
