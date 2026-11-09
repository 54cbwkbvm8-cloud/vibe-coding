"""全屏截图框选层。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCloseEvent,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QKeySequence,
    QResizeEvent,
    QShortcut,
)
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from ..services.screenshot_geometry import selection_to_image_rect


class ScreenshotOverlay(QWidget):
    """覆盖单块屏幕，只返回内存中的裁剪 QImage。"""

    selected = Signal(QImage)
    cancelled = Signal()

    def __init__(
        self,
        screen,
        screenshot: QPixmap,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._screen = screen
        self._screenshot = screenshot
        self._selection = QRect()
        self._drag_start: QPoint | None = None
        self._finished = False

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.size_label = QLabel(self)
        self.size_label.setFont(QFont("Microsoft YaHei UI", 10))
        self.size_label.setStyleSheet(
            "color:white;background:rgba(16,19,25,210);"
            "border:1px solid rgba(255,255,255,90);"
            "border-radius:5px;padding:4px 8px;"
        )
        self.size_label.hide()

        self.confirm_button = QPushButton("确定", self)
        self.reselect_button = QPushButton("重选", self)
        self.cancel_button = QPushButton("取消", self)
        for button in (
            self.confirm_button,
            self.reselect_button,
            self.cancel_button,
        ):
            button.setFixedSize(72, 34)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton{color:#f5f7fa;background:#202630;"
                "border:1px solid #3b4553;border-radius:7px;}"
                "QPushButton:hover{background:#2d3541;}"
            )
            button.hide()

        self.confirm_button.setStyleSheet(
            "QPushButton{color:#171a20;background:#e2b96f;"
            "border:none;border-radius:7px;font-weight:700;}"
            "QPushButton:hover{background:#efc982;}"
        )
        self.confirm_button.clicked.connect(self._confirm)
        self.reselect_button.clicked.connect(self._reset_selection)
        self.cancel_button.clicked.connect(self._cancel)
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        self.escape_shortcut.activated.connect(self._cancel)

    def show_overlay(self) -> None:
        self.setScreen(self._screen)
        self.setGeometry(self._screen.geometry())
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._screenshot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 135))

        if self._selection.width() > 4 and self._selection.height() > 4:
            painter.save()
            painter.setClipRect(self._selection)
            painter.drawPixmap(self.rect(), self._screenshot)
            painter.restore()
            painter.setPen(QPen(QColor("#f0c777"), 2))
            painter.drawRect(self._selection.adjusted(1, 1, -1, -1))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_start = event.position().toPoint()
        self._selection = QRect(self._drag_start, self._drag_start)
        self._hide_action_buttons()
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is None:
            return
        current = event.position().toPoint()
        self._selection = (
            QRect(self._drag_start, current)
            .normalized()
            .intersected(self.rect())
        )
        self._update_selection_ui()
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._drag_start is None:
            return
        self._drag_start = None
        if self._selection.width() < 6 or self._selection.height() < 6:
            self._reset_selection()
        else:
            self._update_selection_ui()
            self._show_action_buttons()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._position_action_buttons()
        self._update_selection_ui()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._finished:
            self._finished = True
            self.cancelled.emit()
        event.accept()

    def _update_selection_ui(self) -> None:
        if self._selection.width() <= 0 or self._selection.height() <= 0:
            self.size_label.hide()
            return
        self.size_label.setText(
            f"{self._selection.width()} × {self._selection.height()}"
        )
        self.size_label.adjustSize()
        label_x = max(8, self._selection.left())
        label_y = max(8, self._selection.top() - self.size_label.height() - 6)
        self.size_label.move(label_x, label_y)
        self.size_label.show()

    def _show_action_buttons(self) -> None:
        for button in (
            self.confirm_button,
            self.reselect_button,
            self.cancel_button,
        ):
            button.show()
        self._position_action_buttons()

    def _hide_action_buttons(self) -> None:
        for button in (
            self.confirm_button,
            self.reselect_button,
            self.cancel_button,
        ):
            button.hide()

    def _position_action_buttons(self) -> None:
        total_width = 72 * 3 + 10 * 2
        x = max(10, (self.width() - total_width) // 2)
        y = max(10, self.height() - 58)
        self.confirm_button.move(x, y)
        self.reselect_button.move(x + 82, y)
        self.cancel_button.move(x + 164, y)

    def _reset_selection(self) -> None:
        self._selection = QRect()
        self._drag_start = None
        self.size_label.hide()
        self._hide_action_buttons()
        self.update()

    def _confirm(self) -> None:
        if self._selection.width() < 6 or self._selection.height() < 6:
            return
        image_rect = selection_to_image_rect(
            self._selection,
            QSize(self.width(), self.height()),
            self._screenshot.size(),
        )
        selected_image = self._screenshot.copy(image_rect).toImage()
        self._finished = True
        self.hide()
        self.selected.emit(selected_image)
        self.close()

    def _cancel(self) -> None:
        if self._finished:
            return
        self._finished = True
        self.hide()
        self.cancelled.emit()
        self.close()
