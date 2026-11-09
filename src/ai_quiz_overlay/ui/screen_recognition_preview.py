"""Reusable glass preview for one-shot screen recognition."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QGuiApplication,
    QImage,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import DEFAULT_SCREEN_RECOGNITION_PROMPT
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
from .brand_assets import load_app_icon
from .assistant_surfaces import (
    MicrophoneButton,
    VoiceLevelIndicator,
    _clamp_rect,
)


class ScreenRecognitionPreview(QWidget):
    send_requested = Signal(str)
    cancelled = Signal()
    microphone_requested = Signal()
    voice_cancel_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._opacity = 1.0
        self._image = QImage()
        self._listening = False
        self._brand_runtime = current_brand_runtime()
        self._glass_cache: QPixmap | None = None
        self._glass_cache_key: tuple | None = None
        self._background_renderer = GlassSurfaceRenderer(self)
        self._background_renderer.configure(self._brand_runtime)
        self._background_renderer.changed.connect(self.update)
        self.setWindowTitle(
            self._brand_runtime.dialog_title("识别当前屏幕")
        )
        self.setWindowIcon(
            load_app_icon(str(self._brand_runtime.app_icon_path))
        )
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet(APP_STYLE)
        self.resize(600, 540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        title = QLabel("识别当前屏幕")
        title.setObjectName("settingsGroupTitle")
        layout.addWidget(title)
        self.thumbnail = QLabel()
        self.thumbnail.setObjectName("screenPreviewImage")
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setMinimumHeight(220)
        self.thumbnail.setStyleSheet(
            "QLabel#screenPreviewImage {"
            "background-color: rgba(8, 12, 24, 185);"
            "border: 1px solid rgba(255,255,255,38);"
            "border-radius: 16px;"
            "}"
        )
        layout.addWidget(self.thumbnail, 1)
        self.prompt = QPlainTextEdit()
        self.prompt.setObjectName("screenPromptEdit")
        self.prompt.setPlaceholderText(DEFAULT_SCREEN_RECOGNITION_PROMPT)
        self.prompt.setMinimumHeight(104)
        layout.addWidget(self.prompt)
        voice_row = QHBoxLayout()
        voice_row.setSpacing(8)
        self.microphone_button = MicrophoneButton()
        self.microphone_button.setToolTip("用语音补充提示词")
        self.microphone_button.clicked.connect(
            self.microphone_requested.emit
        )
        self.listening_label = QLabel("正在聆听，转写会追加到提示词")
        self.listening_label.setObjectName("listeningLabel")
        self.listening_label.hide()
        self.voice_level = VoiceLevelIndicator()
        self.voice_level.hide()
        voice_row.addWidget(self.microphone_button)
        voice_row.addWidget(self.listening_label)
        voice_row.addWidget(self.voice_level)
        voice_row.addStretch()
        layout.addLayout(voice_row)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.cancel)
        self.send_button = QPushButton("发送")
        self.send_button.setObjectName("sendButton")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.clicked.connect(self._emit_send)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        buttons.addWidget(self.send_button)
        layout.addLayout(buttons)

    @property
    def has_image(self) -> bool:
        return not self._image.isNull()

    def set_opacity(self, opacity: float) -> None:
        self._opacity = max(0.2, min(1.0, float(opacity)))
        self._invalidate_glass_cache()
        self.update()

    def apply_brand(self, runtime: BrandRuntime) -> None:
        self._brand_runtime = runtime
        self.setWindowIcon(load_app_icon(str(runtime.app_icon_path)))
        self._background_renderer.configure(runtime)
        self._invalidate_glass_cache()
        self.update()

    def set_listening(self, listening: bool) -> None:
        self._listening = bool(listening)
        self.microphone_button.setProperty("listening", listening)
        self.microphone_button.style().unpolish(self.microphone_button)
        self.microphone_button.style().polish(self.microphone_button)
        self.listening_label.setVisible(listening)
        self.voice_level.setVisible(listening)
        self.send_button.setEnabled(not listening)
        if not listening:
            self.voice_level.set_level(0)

    def set_voice_level(self, level: int) -> None:
        self.voice_level.set_level(level)

    def append_transcript(self, transcript: str) -> None:
        addition = transcript.strip()
        if not addition:
            return
        current = self.prompt.toPlainText().rstrip()
        separator = "\n" if current else ""
        self.prompt.setPlainText(current + separator + addition)
        self.prompt.moveCursor(QTextCursor.MoveOperation.End)

    def show_for(
        self,
        image: QImage,
        prompt: str,
        anchor: QRect,
    ) -> bool:
        screen = QGuiApplication.screenAt(anchor.center())
        screen = screen or QGuiApplication.primaryScreen()
        if screen is None or image.isNull():
            return False
        area = screen.availableGeometry()
        target_width = min(
            600,
            max(520, round(anchor.width() * 2.5)),
        )
        target_height = min(540, max(460, area.height() - 32))
        preferred_x = (
            anchor.right() + 16
            if anchor.center().x() < area.center().x()
            else anchor.left() - target_width - 16
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
        self._image = image.copy()
        pixmap = QPixmap.fromImage(image)
        preview = pixmap.scaled(
            max(1, target_width - 50),
            238,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.thumbnail.setPixmap(preview)
        self.prompt.setPlainText(
            prompt.strip() or DEFAULT_SCREEN_RECOGNITION_PROMPT
        )
        self.prompt.moveCursor(QTextCursor.MoveOperation.End)
        self.setGeometry(target)
        self.show()
        self.raise_()
        if IS_WINDOWS:
            try:
                set_no_activate(int(self.winId()), False)
                apply_acrylic_material(int(self.winId()), False)
                apply_topmost(int(self.winId()))
                activate_foreground(int(self.winId()))
            except (WindowStyleError, TopmostError, OSError):
                pass
        self.activateWindow()
        QTimer.singleShot(0, self._focus_prompt)
        return True

    def cancel(self) -> None:
        if not self.isVisible() and self._image.isNull():
            return
        self.clear_image()
        self.hide()
        self.cancelled.emit()

    def clear_image(self) -> None:
        self._image = QImage()
        self.thumbnail.clear()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self._listening:
                self.voice_cancel_requested.emit()
            else:
                self.cancel()
            event.accept()
            return
        super().keyPressEvent(event)

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

    def _focus_prompt(self) -> None:
        self.raise_()
        self.activateWindow()
        if IS_WINDOWS:
            try:
                activate_foreground(int(self.winId()))
            except (WindowStyleError, OSError):
                pass
        self.prompt.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _emit_send(self) -> None:
        if self._image.isNull():
            return
        prompt = (
            self.prompt.toPlainText().strip()
            or DEFAULT_SCREEN_RECOGNITION_PROMPT
        )
        self.clear_image()
        self.hide()
        self.send_requested.emit(prompt)
