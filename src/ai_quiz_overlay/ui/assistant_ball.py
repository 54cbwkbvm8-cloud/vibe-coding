"""Draggable Siri-style assistant ball with custom painted states."""

from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QRadialGradient,
    QGuiApplication,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from ..branding import asset_path
from ..config import (
    DEFAULT_ASSISTANT_BALL_SIZE,
    MAX_ASSISTANT_BALL_SIZE,
    MIN_ASSISTANT_BALL_SIZE,
)
from ..platform_support import IS_WINDOWS
from ..personalization_runtime import BrandRuntime, current_brand_runtime
from ..win32.acrylic import apply_acrylic_material
from ..win32.topmost import TopmostError, apply_topmost
from ..win32.window_style import WindowStyleError, set_no_activate


DEFAULT_FADE_MS = 160


def _window_size_for_ball(ball_size: int) -> int:
    return max(ball_size + 20, round(ball_size * 1.5))


@lru_cache(maxsize=32)
def _frog_pixmap(ball_size: int, device_ratio: float) -> QPixmap:
    source_path = (
        current_brand_runtime().ball_image_path
        or asset_path("brand", "assistant_ball_1024.png")
    )
    source = QPixmap(str(source_path))
    if source.isNull():
        raise FileNotFoundError("Missing assistant ball logo source.")
    source.setDevicePixelRatio(1.0)
    target = max(ball_size, round(ball_size * device_ratio))
    scaled = source.scaled(
        target,
        target,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    result = QPixmap(target, target)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(QRectF(0, 0, target, target))
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return result


@lru_cache(maxsize=128)
def _glow_pixmap(
    window_size: int,
    device_ratio: float,
    strength: int,
) -> QPixmap:
    pixel_size = max(
        window_size,
        round(window_size * device_ratio),
    )
    pixmap = QPixmap(pixel_size, pixel_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(device_ratio, device_ratio)
    center = QPointF(window_size / 2, window_size / 2)
    glow = QRadialGradient(center, window_size / 2)
    glow.setColorAt(
        0.42,
        QColor(255, 214, 112, strength),
    )
    glow.setColorAt(0.68, QColor(255, 206, 90, 35))
    glow.setColorAt(1.0, QColor(255, 206, 90, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(
        QRectF(0, 0, window_size, window_size)
    )
    painter.end()
    pixmap.setDevicePixelRatio(device_ratio)
    return pixmap


@lru_cache(maxsize=128)
def _idle_frame_pixmap(
    ball_size: int,
    window_size: int,
    device_ratio: float,
    strength: int,
) -> QPixmap:
    pixel_size = max(
        window_size,
        round(window_size * device_ratio),
    )
    pixmap = QPixmap(pixel_size, pixel_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(device_ratio, device_ratio)
    center = QPointF(window_size / 2, window_size / 2)
    glow = QRadialGradient(center, window_size / 2)
    glow.setColorAt(0.42, QColor(255, 214, 112, strength))
    glow.setColorAt(0.68, QColor(255, 206, 90, 35))
    glow.setColorAt(1.0, QColor(255, 206, 90, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(
        QRectF(0, 0, window_size, window_size)
    )
    painter.setPen(QPen(QColor(255, 246, 205, 160), 1.2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(center, ball_size / 2, ball_size / 2)
    frog = _frog_pixmap(ball_size, device_ratio)
    painter.drawPixmap(
        QRectF(
            center.x() - ball_size / 2,
            center.y() - ball_size / 2,
            ball_size,
            ball_size,
        ),
        frog,
        QRectF(frog.rect()),
    )
    painter.end()
    return pixmap


class AssistantBall(QWidget):
    activated = Signal()
    new_conversation_requested = Signal()
    settings_requested = Signal()
    hide_requested = Signal()
    position_changed = Signal(QPoint)

    def __init__(self) -> None:
        super().__init__()
        self._state = "idle"
        self._phase = 0.0
        self._voice_level = 0
        self._ball_size = DEFAULT_ASSISTANT_BALL_SIZE
        self._drag_offset: QPoint | None = None
        self._dragged = False
        window_size = _window_size_for_ball(self._ball_size)
        self.setFixedSize(window_size, window_size)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("奶蛙助手")
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._timer.timeout.connect(self._tick)
        self._fade_animation = QPropertyAnimation(
            self,
            b"windowOpacity",
            self,
        )
        self._fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_animation.finished.connect(self._fade_finished)
        self._hide_after_fade = False

    def apply_brand(self, runtime: BrandRuntime) -> None:
        self.setToolTip(runtime.interface_name)
        _frog_pixmap.cache_clear()
        _idle_frame_pixmap.cache_clear()
        self.update()

    @property
    def state(self) -> str:
        return self._state

    @property
    def ball_size(self) -> int:
        return self._ball_size

    def set_state(self, state: str) -> None:
        if state not in {"idle", "thinking", "responding", "listening"}:
            raise ValueError(f"Unknown assistant state: {state}")
        self._state = state
        self.update()

    def set_voice_level(self, level: int) -> None:
        self._voice_level = max(0, min(100, int(level)))
        if self._state == "listening":
            self.update()

    def start_animation(self) -> None:
        if self.isVisible() and not self._timer.isActive():
            self._timer.start()

    def stop_animation(self) -> None:
        self._timer.stop()

    def show_without_activation(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.show()
        self.raise_()
        if IS_WINDOWS:
            try:
                set_no_activate(int(self.winId()), True)
                apply_acrylic_material(int(self.winId()), False)
                apply_topmost(int(self.winId()))
            except (WindowStyleError, TopmostError, OSError):
                pass
        self.start_animation()

    def hide(self) -> None:
        self._fade_animation.stop()
        self._hide_after_fade = False
        self.setWindowOpacity(1.0)
        self.stop_animation()
        super().hide()

    def set_ball_size(self, ball_size: int) -> None:
        normalized = max(
            MIN_ASSISTANT_BALL_SIZE,
            min(MAX_ASSISTANT_BALL_SIZE, int(ball_size)),
        )
        if normalized == self._ball_size:
            return
        old_center = QPoint(
            self.x() + self.width() // 2,
            self.y() + self.height() // 2,
        )
        was_near_edge = self._is_near_screen_edge()
        self._ball_size = normalized
        window_size = _window_size_for_ball(normalized)
        self.setFixedSize(window_size, window_size)
        self.move(
            old_center.x() - window_size // 2,
            old_center.y() - window_size // 2,
        )
        self._clamp_to_screen(force_snap=was_near_edge)
        self.update()

    def set_visible_animated(
        self,
        visible: bool,
        duration_ms: int = DEFAULT_FADE_MS,
    ) -> None:
        duration = max(0, min(200, int(duration_ms)))
        if visible:
            if not self.isVisible():
                self.setWindowOpacity(0.0)
                self.show_without_activation()
            start_opacity = self.windowOpacity()
            end_opacity = 1.0
            self._hide_after_fade = False
        else:
            if not self.isVisible():
                self.stop_animation()
                return
            start_opacity = self.windowOpacity()
            end_opacity = 0.0
            self._hide_after_fade = True
        self._fade_animation.stop()
        self._fade_animation.setDuration(duration)
        self._fade_animation.setStartValue(start_opacity)
        self._fade_animation.setEndValue(end_opacity)
        self._fade_animation.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.start_animation()

    def hideEvent(self, event) -> None:
        self.stop_animation()
        super().hideEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.pos()
            )
            self._dragged = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            target = event.globalPosition().toPoint() - self._drag_offset
            if (target - self.pos()).manhattanLength() > 3:
                self._dragged = True
            self.move(target)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if self._dragged:
                self.snap_to_edge()
                self.position_changed.emit(self.pos())
            else:
                self.activated.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.addAction("打开输入", self.activated.emit)
        menu.addAction("新对话", self.new_conversation_requested.emit)
        menu.addSeparator()
        menu.addAction("设置", self.settings_requested.emit)
        menu.addAction("隐藏悬浮球", self.hide_requested.emit)
        menu.exec(event.globalPos())

    def snap_to_edge(self) -> None:
        center = self.frameGeometry().center()
        screen = QGuiApplication.screenAt(center)
        screen = screen or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        margin = 10
        left = area.left() + margin
        right = area.right() - self.width() - margin + 1
        top = area.top() + margin
        bottom = area.bottom() - self.height() - margin + 1
        candidates = (
            (abs(self.x() - left), QPoint(left, self.y())),
            (abs(self.x() - right), QPoint(right, self.y())),
            (abs(self.y() - top), QPoint(self.x(), top)),
            (abs(self.y() - bottom), QPoint(self.x(), bottom)),
        )
        _distance, target = min(candidates, key=lambda item: item[0])
        self.move(
            max(left, min(right, target.x())),
            max(top, min(bottom, target.y())),
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        ball_radius = self._ball_size / 2
        phase = math.sin(self._phase)

        frame_bucket = round(
            ((phase + 1) / 2) * 15
        )
        if self._state == "idle":
            idle = _idle_frame_pixmap(
                self._ball_size,
                self.width(),
                self.devicePixelRatioF(),
                frame_bucket,
            )
            painter.drawPixmap(
                QRectF(0, 0, self.width(), self.height()),
                idle,
                QRectF(idle.rect()),
            )
            return
        painter.drawPixmap(
            0,
            0,
            self.width(),
            self.height(),
            _glow_pixmap(
                self.width(),
                self.devicePixelRatioF(),
                frame_bucket,
            ),
        )

        if self._state == "thinking":
            gradient = QConicalGradient(center, self._phase * 80)
            gradient.setColorAt(0.0, QColor(255, 216, 114, 235))
            gradient.setColorAt(0.32, QColor(86, 214, 255, 190))
            gradient.setColorAt(0.62, QColor(255, 255, 255, 35))
            gradient.setColorAt(1.0, QColor(255, 216, 114, 235))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(
                QPen(gradient, max(2.0, self._ball_size / 16))
            )
            painter.drawArc(
                QRectF(
                    center.x() - ball_radius - self._ball_size / 12,
                    center.y() - ball_radius - self._ball_size / 12,
                    self._ball_size + self._ball_size / 6,
                    self._ball_size + self._ball_size / 6,
                ),
                20 * 16,
                285 * 16,
            )
        elif self._state == "responding":
            pulse = self._ball_size * (
                0.0625 + 0.09375 * (phase + 1) / 2
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 216, 114, 80))
            painter.drawEllipse(center, ball_radius + pulse, ball_radius + pulse)
        elif self._state == "listening":
            amplitude = self._voice_level / 100
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(
                QPen(
                    QColor(100, 224, 255, 220),
                    max(1.5, self._ball_size / 21),
                )
            )
            painter.drawEllipse(
                center,
                ball_radius
                + self._ball_size / 16
                + self._ball_size * 0.08 * amplitude,
                ball_radius
                + self._ball_size / 16
                + self._ball_size * 0.08 * amplitude,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(100, 224, 255, 58))
            painter.drawEllipse(
                center,
                ball_radius + self._ball_size * 0.12 * amplitude,
                ball_radius + self._ball_size * 0.12 * amplitude,
            )

        painter.setPen(
            QPen(
                QColor(255, 246, 205, 160),
                max(1.0, self._ball_size / 53),
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, ball_radius, ball_radius)
        ratio = self.devicePixelRatioF()
        pixmap = _frog_pixmap(self._ball_size, ratio)
        painter.drawPixmap(
            QRectF(
                center.x() - ball_radius,
                center.y() - ball_radius,
                self._ball_size,
                self._ball_size,
            ),
            pixmap,
            QRectF(pixmap.rect()),
        )

    def _tick(self) -> None:
        self._phase = (self._phase + 0.12) % (math.pi * 2)
        self.update()

    def _clamp_to_screen(self, force_snap: bool = False) -> None:
        center = self.frameGeometry().center()
        screen = QGuiApplication.screenAt(center)
        screen = screen or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = max(
            area.left(),
            min(area.right() - self.width() + 1, self.x()),
        )
        y = max(
            area.top(),
            min(area.bottom() - self.height() + 1, self.y()),
        )
        self.move(x, y)
        if force_snap:
            self.snap_to_edge()

    def _is_near_screen_edge(self, threshold: int = 12) -> bool:
        screen = QGuiApplication.screenAt(self.frameGeometry().center())
        screen = screen or QApplication.primaryScreen()
        if screen is None:
            return True
        area = screen.availableGeometry()
        distances = (
            abs(self.x() - area.left()),
            abs(self.frameGeometry().right() - area.right()),
            abs(self.y() - area.top()),
            abs(self.frameGeometry().bottom() - area.bottom()),
        )
        return min(distances) <= threshold

    def _fade_finished(self) -> None:
        if self._hide_after_fade:
            self._hide_after_fade = False
            self.stop_animation()
            super().hide()
            self.setWindowOpacity(1.0)
