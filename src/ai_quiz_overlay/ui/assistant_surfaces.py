"""Glass input bar and streaming answer bubble for global assistant mode."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..platform_support import IS_WINDOWS
from ..personalization_runtime import BrandRuntime, current_brand_runtime
from ..theme import APP_STYLE
from ..win32.acrylic import apply_acrylic_material
from ..win32.topmost import TopmostError, apply_topmost
from ..win32.window_style import (
    WindowStyleError,
    activate_foreground,
    set_no_activate,
)
from .glass_renderer import draw_glass_window
from .personalized_background import GlassSurfaceRenderer


def _clamp_rect(rect: QRect, screen_rect: QRect, margin: int = 12) -> QRect:
    width = min(rect.width(), max(120, screen_rect.width() - margin * 2))
    height = min(rect.height(), max(80, screen_rect.height() - margin * 2))
    x = max(
        screen_rect.left() + margin,
        min(screen_rect.right() - width - margin + 1, rect.x()),
    )
    y = max(
        screen_rect.top() + margin,
        min(screen_rect.bottom() - height - margin + 1, rect.y()),
    )
    return QRect(x, y, width, height)


class AssistantLineEdit(QLineEdit):
    escape_pressed = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class AssistantAnswerView(QTextBrowser):
    activity = Signal()

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.activity.emit()


class MicrophoneButton(QToolButton):
    """Painted microphone icon with visible listening state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        listening = bool(self.property("listening"))
        hovered = self.underMouse() or self.hasFocus()
        background = QColor(255, 198, 92, 70 if listening else 28)
        if hovered and not listening:
            background = QColor(255, 255, 255, 42)
        painter.setPen(
            QPen(
                QColor(255, 226, 152, 190)
                if listening
                else QColor(255, 255, 255, 75),
                1,
            )
        )
        painter.setBrush(background)
        painter.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
        pen = QPen(
            QColor(255, 229, 166) if listening else QColor(235, 239, 249),
            1.8,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        center_x = self.width() / 2
        painter.drawRoundedRect(
            QRectF(center_x - 4.5, 8, 9, 13),
            4.5,
            4.5,
        )
        painter.drawLine(
            QPointF(center_x - 8, 15),
            QPointF(center_x - 8, 17),
        )
        painter.drawArc(
            QRectF(center_x - 8, 10, 16, 14),
            180 * 16,
            180 * 16,
        )
        painter.drawLine(
            QPointF(center_x, 24),
            QPointF(center_x, 27),
        )
        painter.drawLine(
            QPointF(center_x - 4, 27),
            QPointF(center_x + 4, 27),
        )


class VoiceLevelIndicator(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._level = 0
        self.setFixedSize(40, 24)

    def set_level(self, level: int) -> None:
        self._level = max(0, min(100, int(level)))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        active_bars = max(1, round(self._level / 100 * 7))
        for index in range(7):
            height = 5 + index * 2.2
            rect = QRectF(
                2 + index * 5.4,
                (self.height() - height) / 2,
                3.2,
                height,
            )
            color = (
                QColor(104, 224, 255, 225)
                if index < active_bars
                else QColor(255, 255, 255, 52)
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 1.6, 1.6)

    def wheelEvent(self, event) -> None:
        super().wheelEvent(event)
        self.activity.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        super().keyPressEvent(event)
        self.activity.emit()


class AssistantInputBar(QWidget):
    send_requested = Signal(str)
    stop_requested = Signal()
    dismissed = Signal()
    microphone_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._opacity = 1.0
        self._busy = False
        self._brand_runtime = current_brand_runtime()
        self._glass_cache: QPixmap | None = None
        self._glass_cache_key: tuple | None = None
        self._background_renderer = GlassSurfaceRenderer(self)
        self._background_renderer.configure(self._brand_runtime)
        self._background_renderer.changed.connect(self.update)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet(APP_STYLE)
        self.setFixedHeight(72)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 14, 10)
        layout.setSpacing(8)
        self.input = AssistantLineEdit()
        self.input.setObjectName("compactInput")
        self.input.setPlaceholderText("问奶蛙任何问题…")
        self.input.returnPressed.connect(self._emit_send)
        self.input.escape_pressed.connect(self.dismiss)
        self.send_button = QPushButton("发送")
        self.send_button.setObjectName("sendButton")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.clicked.connect(self._send_or_stop)
        self.close_button = QToolButton()
        self.close_button.setObjectName("secondaryButton")
        self.close_button.setText("关闭")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(lambda: self.dismiss())
        self.microphone_button = MicrophoneButton()
        self.microphone_button.setObjectName("microphoneButton")
        self.microphone_button.setText("话筒")
        self.microphone_button.setToolTip("开始或结束语音输入")
        self.microphone_button.setAccessibleName("语音输入")
        self.microphone_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.microphone_button.clicked.connect(
            self.microphone_requested.emit
        )
        self.listening_label = QLabel("正在聆听")
        self.listening_label.setObjectName("listeningLabel")
        self.listening_label.hide()
        self.voice_level = VoiceLevelIndicator()
        self.voice_level.hide()
        layout.addWidget(self.input, 1)
        layout.addWidget(self.listening_label)
        layout.addWidget(self.voice_level)
        layout.addWidget(self.microphone_button)
        layout.addWidget(self.send_button)
        layout.addWidget(self.close_button)
        self._animation = QPropertyAnimation(self, b"geometry", self)
        self._animation.setDuration(170)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    @property
    def busy(self) -> bool:
        return self._busy

    def set_opacity(self, opacity: float) -> None:
        self._opacity = opacity
        self._invalidate_glass_cache()
        self.update()

    def apply_brand(self, runtime: BrandRuntime) -> None:
        self._brand_runtime = runtime
        self._background_renderer.configure(runtime)
        self._invalidate_glass_cache()
        self.update()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.send_button.setText("停止" if busy else "发送")
        self.send_button.setProperty("danger", busy)
        self.send_button.style().unpolish(self.send_button)
        self.send_button.style().polish(self.send_button)
        self.input.setEnabled(not busy)

    def set_listening(self, listening: bool) -> None:
        self.microphone_button.setProperty("listening", listening)
        self.microphone_button.style().unpolish(self.microphone_button)
        self.microphone_button.style().polish(self.microphone_button)
        self.listening_label.setVisible(listening)
        self.voice_level.setVisible(listening)
        self.send_button.setEnabled(not listening and not self._busy)
        if not listening:
            self.voice_level.set_level(0)

    def set_voice_level(self, level: int) -> None:
        self.voice_level.set_level(level)

    def append_transcript(self, transcript: str) -> None:
        addition = transcript.strip()
        if not addition:
            return
        current = self.input.text()
        if not current:
            separator = ""
        elif current[-1].isspace():
            separator = ""
        else:
            separator = " "
        self.input.setText(current + separator + addition)
        self.input.setCursorPosition(len(self.input.text()))

    def show_focused(self, anchor: QRect) -> None:
        screen = QGuiApplication.screenAt(anchor.center())
        screen = screen or QGuiApplication.primaryScreen()
        if screen is None:
            return
        target_width = min(
            600,
            max(520, round(anchor.width() * 3)),
        )
        target = _clamp_rect(
            QRect(
                anchor.center().x() - target_width // 2,
                anchor.center().y() - 36,
                target_width,
                72,
            ),
            screen.availableGeometry(),
        )
        if IS_WINDOWS:
            try:
                set_no_activate(int(self.winId()), False)
                apply_acrylic_material(int(self.winId()), False)
                apply_topmost(int(self.winId()))
            except (WindowStyleError, TopmostError, OSError):
                pass
        self.setGeometry(anchor)
        self.show()
        self.raise_()
        self._animation.stop()
        self._animation.setStartValue(anchor)
        self._animation.setEndValue(target)
        self._animation.start()
        self.activateWindow()
        if IS_WINDOWS:
            try:
                activate_foreground(int(self.winId()))
            except (AttributeError, OSError, WindowStyleError):
                pass
        QTimer.singleShot(0, self._focus_input)

    def dismiss(self) -> None:
        self.hide()
        self.input.clear()
        self.set_listening(False)
        self.dismissed.emit()

    def restore_focus(self) -> None:
        if self.isVisible():
            self._focus_input()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        self._glass_cache = self._background_renderer.pixmap_for(
            self.width(),
            self.height(),
            self.devicePixelRatioF(),
            opacity=self._opacity,
            active=self.isActiveWindow(),
        )
        if self._glass_cache is not None:
            painter.drawPixmap(0, 0, self._glass_cache)

    def _invalidate_glass_cache(self) -> None:
        self._glass_cache = None
        self._glass_cache_key = None
        self.update()

    def _focus_input(self) -> None:
        self.raise_()
        self.activateWindow()
        if IS_WINDOWS:
            try:
                activate_foreground(int(self.winId()))
            except (AttributeError, OSError, WindowStyleError):
                pass
        self.input.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _emit_send(self) -> None:
        text = self.input.text().strip()
        if text and not self._busy:
            self.send_requested.emit(text)

    def _send_or_stop(self) -> None:
        if self._busy:
            self.stop_requested.emit()
        else:
            self._emit_send()


class AssistantBubble(QWidget):
    closed = Signal()
    new_conversation_requested = Signal()
    stop_requested = Signal()
    activity = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._opacity = 1.0
        self._busy = False
        self._markdown = ""
        self._status_placeholder = False
        self._auto_hide_seconds = 60
        self._brand_runtime = current_brand_runtime()
        self._glass_cache: QPixmap | None = None
        self._glass_cache_key: tuple | None = None
        self._background_renderer = GlassSurfaceRenderer(self)
        self._background_renderer.configure(self._brand_runtime)
        self._background_renderer.changed.connect(self.update)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet(APP_STYLE)
        self.installEventFilter(self)
        self.resize(520, 380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        self.answer = AssistantAnswerView()
        self.answer.setOpenExternalLinks(False)
        self.answer.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.answer.installEventFilter(self)
        self.answer.activity.connect(self.activity.emit)
        self.answer.cursorPositionChanged.connect(self.activity.emit)
        self.answer.verticalScrollBar().valueChanged.connect(
            lambda _value: self.activity.emit()
        )
        layout.addWidget(self.answer, 1)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("secondaryButton")
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.copy_button = QToolButton()
        self.copy_button.setObjectName("secondaryButton")
        self.copy_button.setText("复制")
        self.copy_button.clicked.connect(self.copy_answer)
        self.new_button = QToolButton()
        self.new_button.setObjectName("secondaryButton")
        self.new_button.setText("新对话")
        self.new_button.clicked.connect(self.new_conversation_requested.emit)
        self.close_button = QToolButton()
        self.close_button.setObjectName("secondaryButton")
        self.close_button.setText("关闭")
        self.close_button.clicked.connect(self.close_bubble)
        buttons.addWidget(self.stop_button)
        buttons.addStretch()
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.new_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.close_bubble)
        self.activity.connect(self.restart_auto_hide)

    @property
    def markdown_text(self) -> str:
        return self._markdown

    @property
    def busy(self) -> bool:
        return self._busy

    def set_opacity(self, opacity: float) -> None:
        self._opacity = opacity
        self._invalidate_glass_cache()
        self.update()

    def apply_brand(self, runtime: BrandRuntime) -> None:
        self._brand_runtime = runtime
        self._background_renderer.configure(runtime)
        self._invalidate_glass_cache()
        self.update()

    def set_auto_hide_seconds(self, seconds: int) -> None:
        self._auto_hide_seconds = max(5, int(seconds))

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.stop_button.setVisible(busy)
        self.stop_button.setEnabled(busy)
        self.new_button.setEnabled(not busy)
        if busy:
            self._auto_hide_timer.stop()

    def begin_stream(self, status_text: str = "") -> None:
        self._markdown = ""
        self._status_placeholder = bool(status_text)
        self.answer.clear()
        if status_text:
            self.answer.setPlainText(status_text)
        self.set_busy(True)

    def append_markdown(self, chunk: str) -> None:
        if self._status_placeholder:
            self._status_placeholder = False
            self.answer.clear()
        self._markdown += chunk
        self.answer.setMarkdown(self._markdown)
        scrollbar = self.answer.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self.activity.emit()

    def show_result(self, message: str = "", error: bool = False) -> None:
        if message and error:
            self._markdown = message
            self.answer.setPlainText(message)
            self.answer.setProperty("error", True)
        elif message:
            self.answer.setMarkdown(
                f"{self._markdown}\n\n_{message}_"
            )
        else:
            self.answer.setMarkdown(self._markdown)
        self.set_busy(False)
        self._auto_hide_timer.start(self._auto_hide_seconds * 1000)

    def restart_auto_hide(self) -> None:
        if self.isVisible() and not self._busy:
            self._auto_hide_timer.start(self._auto_hide_seconds * 1000)

    def clear_conversation(self) -> None:
        self._auto_hide_timer.stop()
        self._markdown = ""
        self._status_placeholder = False
        self.answer.clear()
        self.set_busy(False)
        self.hide()

    def show_near(self, anchor: QRect) -> None:
        screen = QGuiApplication.screenAt(anchor.center())
        screen = screen or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        target_width = min(
            600,
            max(520, round(anchor.width() * 3)),
        )
        target_height = min(
            440,
            max(380, round(anchor.width() * 2)),
        )
        preferred_x = (
            anchor.right() + 12
            if anchor.center().x() < area.center().x()
            else anchor.left() - target_width - 12
        )
        preferred_y = anchor.center().y() - target_height // 2
        target = _clamp_rect(
            QRect(
                preferred_x,
                preferred_y,
                target_width,
                target_height,
            ),
            area,
        )
        self.setGeometry(target)
        self.show()
        self.raise_()
        if IS_WINDOWS:
            try:
                set_no_activate(int(self.winId()), True)
                apply_acrylic_material(int(self.winId()), False)
                apply_topmost(int(self.winId()))
            except (WindowStyleError, TopmostError, OSError):
                pass

    def close_bubble(self) -> None:
        self._auto_hide_timer.stop()
        self.hide()
        self.closed.emit()

    def copy_answer(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.answer.toPlainText())
        self.activity.emit()

    def eventFilter(self, watched, event) -> bool:
        if event.type() in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.Wheel,
            QEvent.Type.KeyPress,
        ):
            self.activity.emit()
        return super().eventFilter(watched, event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        self._glass_cache = self._background_renderer.pixmap_for(
            self.width(),
            self.height(),
            self.devicePixelRatioF(),
            opacity=self._opacity,
            active=self.isActiveWindow(),
        )
        if self._glass_cache is not None:
            painter.drawPixmap(0, 0, self._glass_cache)

    def _invalidate_glass_cache(self) -> None:
        self._glass_cache = None
        self._glass_cache_key = None
        self.update()
