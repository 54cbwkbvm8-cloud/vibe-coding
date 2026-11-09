"""无边框聊天悬浮窗、DeepSeek 流式状态和窗口内设置页。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QRect,
    QSize,
    QThread,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QCloseEvent,
    QGuiApplication,
    QHideEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig, WindowGeometry
from ..platform_support import IS_WINDOWS
from ..personalization_runtime import BrandRuntime, current_brand_runtime
from ..services.chat_session import ChatSession
from ..services.chat_provider import (
    ChatRequest,
    ProviderUnavailableError,
)
from ..services.image_payload import ImagePayloadError, image_to_data_url
from ..services.provider_registry import create_chat_provider
from ..services.provider_worker import ProviderChatWorker
from ..services.window_geometry import restore_window_rect
from ..theme import THEME, clamp_glass_opacity, readability_scrim_alpha
from ..win32.acrylic import (
    acrylic_availability,
    apply_acrylic_material,
    current_windows_build,
)
from ..win32.native_resize import (
    NativeResizeFilter,
)
from ..win32.session_lock import SessionLockFilter
from ..win32.topmost import TopmostError, apply_topmost
from ..win32.window_style import WindowStyleError, set_no_activate
from .answer_view import AnswerView
from .brand_assets import load_app_icon
from .compact_bar import CompactBar
from .glass_renderer import draw_glass_window
from .personalized_background import GlassSurfaceRenderer
from .question_input import QuestionInput
from .screenshot_preview import ScreenshotPreview
from .settings_panel import SettingsPanel, SettingsValues
from .styles import APP_STYLE
from .title_bar import TitleBar


HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17


class MainWindow(QWidget):
    """协调界面、对话历史和工作线程，不直接持久化 API Key。"""

    settings_requested = Signal()
    screenshot_requested = Signal()
    settings_save_requested = Signal()
    shutdown_complete = Signal()
    compact_mode_changed = Signal(bool)
    hotkey_recording_started = Signal()
    hotkey_recording_finished = Signal()
    settings_back_requested = Signal()
    assistant_ball_size_preview = Signal(int)
    screen_consent_revoked = Signal()
    voice_consent_revoked = Signal()
    voice_model_download_requested = Signal()
    voice_model_import_requested = Signal()
    session_locked = Signal()
    personalization_preview = Signal(object)
    background_select_requested = Signal()
    icon_select_requested = Signal(str)
    backgrounds_icons_same_requested = Signal()
    reset_personalization_requested = Signal(str)
    create_shortcut_requested = Signal()
    delete_shortcut_requested = Signal()
    official_risk_requested = Signal()
    official_login_requested = Signal()
    official_component_import_zip_requested = Signal()
    official_component_import_folder_requested = Signal()
    official_consent_revoked = Signal()
    browser_mode_requested = Signal()
    browser_risk_requested = Signal()
    browser_consent_revoked = Signal()
    browser_screen_consent_revoked = Signal()
    browser_voice_consent_revoked = Signal()
    access_method_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._thread: QThread | None = None
        self._worker: ProviderChatWorker | None = None
        self._chat_session = ChatSession()
        self._api_config: AppConfig | None = None
        self._api_key: str | None = None
        self._pending_question = ""
        self._active_screen_recognition = False
        self._stream_kind = ""
        self._stream_message = ""
        self._closing_after_stop = False
        self._after_stop_callback = None
        self._allow_close = False
        self._no_focus_mode = False
        self._temporary_input_focus = False
        self._glass_opacity = 1.0
        self._acrylic_requested = True
        self._acrylic_active = False
        self._acrylic_reason = ""
        self._compact_mode = False
        self._expanded_size = QSize(420, 560)
        self._glass_cache: QPixmap | None = None
        self._glass_cache_key: tuple | None = None
        self._brand_runtime = current_brand_runtime()
        self._background_renderer = GlassSurfaceRenderer(self)
        self._background_renderer.configure(self._brand_runtime)
        self._background_renderer.changed.connect(self.update)
        self._resize_user32 = (
            ctypes.WinDLL("user32", use_last_error=True)
            if IS_WINDOWS
            else None
        )
        if self._resize_user32 is not None:
            self._resize_user32.GetWindowRect.argtypes = [
                wintypes.HWND,
                ctypes.POINTER(wintypes.RECT),
            ]

        self.setObjectName("mainWindow")
        self.setWindowTitle(self._brand_runtime.software_name)
        self.setWindowIcon(
            load_app_icon(str(self._brand_runtime.app_icon_path))
        )
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.resize(420, 560)
        self.setStyleSheet(APP_STYLE)

        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(1500)
        self._topmost_timer.timeout.connect(self._apply_topmost)

        self._build_ui()
        self._apply_readability_opacity(1.0)
        self._expanded_minimum_size = self._derive_expanded_minimum_size()
        self.setMinimumSize(self._expanded_minimum_size)
        self._connect_signals()
        self._native_resize_filter = NativeResizeFilter(
            int(self.winId()),
            self._native_resize_hit_test,
        )
        self._session_lock_filter = SessionLockFilter(
            int(self.winId()),
            self.session_locked.emit,
        )
        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._native_resize_filter)
            app.installNativeEventFilter(self._session_lock_filter)
            app_ref = app
            filter_ref = self._native_resize_filter
            session_filter_ref = self._session_lock_filter
            self.destroyed.connect(
                lambda: (
                    app_ref.removeNativeEventFilter(filter_ref),
                    session_filter_ref.close(),
                    app_ref.removeNativeEventFilter(session_filter_ref),
                )
            )

    def _build_ui(self) -> None:
        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(
            THEME.shadow_margin,
            THEME.shadow_margin,
            THEME.shadow_margin,
            THEME.shadow_margin,
        )
        window_layout.setSpacing(0)

        self.title_bar = TitleBar()
        window_layout.addWidget(self.title_bar)

        self._compact_bar = CompactBar()
        self._compact_bar.setFixedHeight(64)
        self._compact_bar.hide()
        window_layout.addWidget(self._compact_bar)

        self._body = QWidget()
        self._body.setObjectName("contentBody")
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._page_stack = QStackedWidget()
        self._chat_page = self._build_chat_page()
        self.settings_panel = SettingsPanel()
        self._page_stack.addWidget(self._chat_page)
        self._page_stack.addWidget(self.settings_panel)

        body_layout.addWidget(self._page_stack)
        window_layout.addWidget(self._body, 1)

    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(16, 8, 16, 12)
        page_layout.setSpacing(8)

        self._notice_label = QLabel()
        self._notice_label.setObjectName("noticeLabel")
        self._notice_label.setWordWrap(True)
        self._notice_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._notice_label.hide()
        page_layout.addWidget(self._notice_label)

        self._answer_label = QLabel("回答")
        self._answer_label.setObjectName("sectionLabel")
        page_layout.addWidget(self._answer_label)

        self.answer_view = AnswerView()
        page_layout.addWidget(self.answer_view, 1)

        self._question_label = QLabel("问题")
        self._question_label.setObjectName("sectionLabel")
        page_layout.addWidget(self._question_label)

        self._screenshot_preview = ScreenshotPreview()
        page_layout.addWidget(self._screenshot_preview)

        self._question_input = QuestionInput()
        page_layout.addWidget(self._question_input)

        footer = QVBoxLayout()
        footer.setSpacing(5)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self._status_label = QLabel("等待设置")
        self._status_label.setObjectName("statusLabel")
        self._screenshot_button = QPushButton("截图")
        self._screenshot_button.setObjectName("secondaryButton")
        self._screenshot_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._screenshot_button.setMinimumWidth(56)
        self._new_conversation_button = QPushButton("新对话")
        self._new_conversation_button.setObjectName("secondaryButton")
        self._new_conversation_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_button = QPushButton("发送")
        self._send_button.setObjectName("sendButton")
        self._send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_button.setMinimumWidth(76)

        action_row.addWidget(self._status_label)
        action_row.addStretch()
        action_row.addWidget(self._screenshot_button)
        action_row.addWidget(self._new_conversation_button)
        action_row.addWidget(self._send_button)

        self._hotkey_hint_label = QLabel(
            "问答 Ctrl+Alt+Q · 截图 Ctrl+Alt+A"
        )
        self._hotkey_hint_label.setObjectName("hotkeyHint")
        self._hotkey_hint_label.setWordWrap(True)

        hint_row = QHBoxLayout()
        hint_row.setSpacing(8)
        shortcut_label = QLabel("Enter 发送  Shift+Enter 换行")
        shortcut_label.setObjectName("shortcutLabel")
        hint_row.addWidget(shortcut_label)
        hint_row.addStretch()

        footer.addLayout(action_row)
        footer.addWidget(self._hotkey_hint_label)
        footer.addLayout(hint_row)
        page_layout.addLayout(footer)
        return page

    def _derive_expanded_minimum_size(self) -> QSize:
        self.layout().activate()
        title_size = self.title_bar.minimumSizeHint()
        chat_size = self._chat_page.minimumSizeHint()
        chat_preferred = self._chat_page.sizeHint()
        compact_size = self._compact_bar.minimumSizeHint()
        return QSize(
            max(title_size.width(), chat_size.width(), compact_size.width()),
            THEME.title_height
            + max(chat_size.height(), chat_preferred.height()),
        )

    def _refresh_expanded_minimum_size(self) -> None:
        self._expanded_minimum_size = self._derive_expanded_minimum_size()
        if self._compact_mode:
            return
        self.setMinimumSize(self._expanded_minimum_size)
        self.resize(
            max(self._expanded_minimum_size.width(), self.width()),
            max(self._expanded_minimum_size.height(), self.height()),
        )

    def _connect_signals(self) -> None:
        self.title_bar.close_requested.connect(self.hide_overlay)
        self.title_bar.minimize_requested.connect(self.minimize_overlay)
        self.title_bar.compact_toggle_requested.connect(
            self.toggle_compact_mode
        )
        self.title_bar.settings_requested.connect(self._open_settings)
        self.title_bar.input_requested.connect(self.enter_input_mode)
        self.title_bar.official_risk_requested.connect(
            self.official_risk_requested.emit
        )
        self._question_input.send_requested.connect(self._handle_enter)
        self._compact_bar.send_requested.connect(self._handle_compact_send)
        self._send_button.clicked.connect(self._handle_send_or_stop)
        self._screenshot_button.clicked.connect(
            lambda: self.screenshot_requested.emit()
        )
        self._new_conversation_button.clicked.connect(self.start_new_conversation)
        self._screenshot_preview.remove_requested.connect(
            self._remove_pending_screenshot
        )
        self.settings_panel.back_requested.connect(
            self.settings_back_requested.emit
        )
        self.settings_panel.save_requested.connect(
            self.settings_save_requested.emit
        )
        self.settings_panel.opacity_preview.connect(self.set_window_opacity)
        self.settings_panel.hotkey_recording_started.connect(
            self.hotkey_recording_started.emit
        )
        self.settings_panel.hotkey_recording_finished.connect(
            self.hotkey_recording_finished.emit
        )
        self.settings_panel.assistant_ball_size_preview.connect(
            self.assistant_ball_size_preview.emit
        )
        self.settings_panel.screen_consent_revoked.connect(
            self.screen_consent_revoked.emit
        )
        self.settings_panel.voice_consent_revoked.connect(
            self.voice_consent_revoked.emit
        )
        self.settings_panel.voice_model_download_requested.connect(
            self.voice_model_download_requested.emit
        )
        self.settings_panel.voice_model_import_requested.connect(
            self.voice_model_import_requested.emit
        )
        self.settings_panel.personalization_preview.connect(
            self.personalization_preview.emit
        )
        self.settings_panel.background_select_requested.connect(
            self.background_select_requested.emit
        )
        self.settings_panel.icon_select_requested.connect(
            self.icon_select_requested.emit
        )
        self.settings_panel.backgrounds_icons_same_requested.connect(
            self.backgrounds_icons_same_requested.emit
        )
        self.settings_panel.reset_personalization_requested.connect(
            self.reset_personalization_requested.emit
        )
        self.settings_panel.create_shortcut_requested.connect(
            self.create_shortcut_requested.emit
        )
        self.settings_panel.delete_shortcut_requested.connect(
            self.delete_shortcut_requested.emit
        )
        self.settings_panel.access_method_requested.connect(
            self.access_method_requested.emit
        )
        self.settings_panel.official_login_requested.connect(
            self.official_login_requested.emit
        )
        self.settings_panel.official_component_import_zip_requested.connect(
            self.official_component_import_zip_requested.emit
        )
        self.settings_panel.official_component_import_folder_requested.connect(
            self.official_component_import_folder_requested.emit
        )
        self.settings_panel.official_risk_read_requested.connect(
            self.official_risk_requested.emit
        )
        self.settings_panel.official_consent_revoked.connect(
            self.official_consent_revoked.emit
        )
        self.settings_panel.browser_mode_requested.connect(
            self.browser_mode_requested.emit
        )
        self.settings_panel.browser_risk_read_requested.connect(
            self.browser_risk_requested.emit
        )
        self.settings_panel.browser_consent_revoked.connect(
            self.browser_consent_revoked.emit
        )
        self.settings_panel.browser_screen_consent_revoked.connect(
            self.browser_screen_consent_revoked.emit
        )
        self.settings_panel.browser_voice_consent_revoked.connect(
            self.browser_voice_consent_revoked.emit
        )
    @Slot()
    def show_overlay(self) -> None:
        """显示窗口、激活并聚焦问题输入框。"""
        if self.isMinimized():
            self.setWindowState(
                self.windowState() & ~Qt.WindowState.WindowMinimized
            )
        show_without_activating = (
            self._no_focus_mode and not self._temporary_input_focus
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating,
            show_without_activating,
        )
        self.show()
        if show_without_activating:
            QTimer.singleShot(0, self._apply_no_activate)
        else:
            self.raise_()
            self.activateWindow()
            if self._compact_mode:
                self._compact_bar.focus_input()
            elif self._page_stack.currentWidget() is self._chat_page:
                self._question_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
            else:
                self.settings_panel.focus_api_key(
                    Qt.FocusReason.ShortcutFocusReason
                )
        QTimer.singleShot(0, self._apply_topmost)

    @Slot()
    def minimize_overlay(self) -> None:
        self._temporary_input_focus = False
        self.title_bar.set_input_mode_active(False)
        self.showMinimized()

    @Slot()
    def _open_settings(self) -> None:
        if self._compact_mode:
            self.set_compact_mode(False)
        self.settings_requested.emit()

    @Slot()
    def toggle_compact_mode(self) -> None:
        self.set_compact_mode(not self._compact_mode)

    def set_compact_mode(self, enabled: bool) -> None:
        if enabled == self._compact_mode:
            return

        if enabled:
            self._expanded_size = self.size()
            self._compact_bar.set_text(self._question_input.toPlainText())
            self._compact_bar.show()
            self._body.hide()
            self._compact_mode = True
            self.setMaximumSize(16777215, THEME.compact_height)
            compact_width = max(
                self.title_bar.minimumSizeHint().width(),
                self._compact_bar.minimumSizeHint().width(),
            )
            self.setMinimumSize(compact_width, THEME.compact_height)
            self.resize(max(compact_width, self.width()), THEME.compact_height)
            self.title_bar.set_compact_mode(True)
        else:
            compact_text = self._compact_bar.text()
            self._compact_mode = False
            self._compact_bar.hide()
            self._body.show()
            self.setMaximumSize(16777215, 16777215)
            self.setMinimumSize(self._expanded_minimum_size)
            screens = [
                screen.availableGeometry()
                for screen in QGuiApplication.screens()
            ]
            restored = restore_window_rect(
                WindowGeometry(
                    self.x(),
                    self.y(),
                    max(
                        self._expanded_minimum_size.width(),
                        self._expanded_size.width(),
                    ),
                    max(
                        self._expanded_minimum_size.height(),
                        self._expanded_size.height(),
                    ),
                ),
                screens,
                QSize(420, 560),
            )
            self.setGeometry(restored)
            if compact_text:
                self._question_input.setPlainText(compact_text)
            self.title_bar.set_compact_mode(False)

        self._apply_acrylic_material()
        self.compact_mode_changed.emit(self._compact_mode)
        self.update()

    @Slot()
    def hide_overlay(self) -> None:
        self._temporary_input_focus = False
        self.title_bar.set_input_mode_active(False)
        if self._no_focus_mode:
            self.setAttribute(
                Qt.WidgetAttribute.WA_ShowWithoutActivating,
                True,
            )
        self.hide()
        if self._no_focus_mode:
            QTimer.singleShot(0, self._apply_no_activate)

    @Slot()
    def enter_input_mode(self) -> None:
        """No-focus 模式下由用户明确进入临时输入状态。"""
        if not self._no_focus_mode:
            return
        self._temporary_input_focus = True
        self.title_bar.set_input_mode_active(True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        try:
            set_no_activate(int(self.winId()), False)
        except WindowStyleError:
            pass
        self.show()
        self.raise_()
        self.activateWindow()
        if self._compact_mode:
            self._compact_bar.focus_input()
        elif self._page_stack.currentWidget() is self.settings_panel:
            self.settings_panel.focus_api_key(
                Qt.FocusReason.ActiveWindowFocusReason
            )
        else:
            self._question_input.setFocus(
                Qt.FocusReason.ActiveWindowFocusReason
            )

    @Slot(bool)
    def set_no_focus_mode(self, enabled: bool) -> None:
        self._no_focus_mode = enabled
        self._temporary_input_focus = False
        self.setAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating,
            enabled,
        )
        self.title_bar.set_no_focus_mode(enabled)
        self.title_bar.set_input_mode_active(False)
        self._refresh_expanded_minimum_size()
        self._apply_no_activate()

    @Slot(float)
    def set_window_opacity(self, opacity: float) -> None:
        self._glass_opacity = clamp_glass_opacity(opacity)
        self._apply_readability_opacity(self._glass_opacity)
        self._invalidate_glass_cache()

    def apply_brand(self, runtime: BrandRuntime) -> None:
        self._brand_runtime = runtime
        self.setWindowTitle(runtime.software_name)
        self.setWindowIcon(load_app_icon(str(runtime.app_icon_path)))
        self.title_bar.apply_brand(runtime)
        self._background_renderer.configure(runtime)
        self._invalidate_glass_cache()
        self.update()

    def _apply_readability_opacity(self, opacity: float) -> None:
        alpha = readability_scrim_alpha(opacity)
        style = (
            "background-color: transparent;"
            if alpha == 0
            else f"background-color: rgba(6, 9, 18, {alpha});"
        )
        for label in (
            self.title_bar.title_label,
            self._answer_label,
            self._question_label,
        ):
            label.setStyleSheet(style)
        self.settings_panel.set_readability_opacity(opacity)

    def set_acrylic_enabled(self, enabled: bool) -> None:
        self._acrylic_requested = enabled
        if IS_WINDOWS:
            availability = acrylic_availability(
                windows_build=current_windows_build(),
            )
            supported = availability.supported
            reason = availability.reason
        else:
            supported = False
            reason = "当前操作系统不支持 Windows Acrylic，已使用 Qt 自绘玻璃。"
        self._acrylic_reason = reason
        self.settings_panel.set_acrylic_availability(supported, reason)
        self._apply_acrylic_material()
        self._invalidate_glass_cache()

    @property
    def glass_opacity(self) -> float:
        return self._glass_opacity

    @property
    def acrylic_active(self) -> bool:
        return self._acrylic_active

    @property
    def acrylic_requested(self) -> bool:
        return self._acrylic_requested

    @property
    def acrylic_reason(self) -> str:
        return self._acrylic_reason

    @property
    def is_compact(self) -> bool:
        return self._compact_mode

    @Slot()
    def _apply_acrylic_material(self) -> None:
        if not self.isVisible() or not IS_WINDOWS:
            self._acrylic_active = False
            return
        self._acrylic_active = apply_acrylic_material(
            int(self.winId()),
            self._acrylic_requested,
        )
        self._invalidate_glass_cache()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        self._glass_cache = self._background_renderer.pixmap_for(
            max(1, self.width()),
            max(1, self.height()),
            self.devicePixelRatioF(),
            opacity=self._glass_opacity,
            active=self.isActiveWindow(),
            acrylic_active=self._acrylic_active,
        )
        if not self._glass_cache.isNull():
            painter.drawPixmap(0, 0, self._glass_cache)

    def _native_resize_hit_test(self, global_position: QPoint) -> int:
        if self._resize_user32 is None:
            return 0
        native_rect = wintypes.RECT()
        if not self._resize_user32.GetWindowRect(
            wintypes.HWND(int(self.winId())),
            ctypes.byref(native_rect),
        ):
            return 0
        native_width = max(1, native_rect.right - native_rect.left)
        native_height = max(1, native_rect.bottom - native_rect.top)
        scale_x = self.width() / native_width
        scale_y = self.height() / native_height
        position = QPoint(
            min(
                self.width() - 1,
                max(0, round((global_position.x() - native_rect.left) * scale_x)),
            ),
            min(
                self.height() - 1,
                max(0, round((global_position.y() - native_rect.top) * scale_y)),
            ),
        )
        return self._resize_hit_test_local(position)

    def _resize_hit_test_local(self, position: QPoint) -> int:
        x = position.x()
        y = position.y()
        width = self.width()
        height = self.height()
        if not (0 <= x < width and 0 <= y < height):
            return 0

        border = THEME.resize_border
        if self._compact_mode:
            if x < border:
                return HTLEFT
            if x >= width - border:
                return HTRIGHT
            return 0

        corner = THEME.resize_corner
        left = x < border
        right = x >= width - border
        top = y < border
        bottom = y >= height - border
        if x < corner and y < corner:
            return HTTOPLEFT
        if x >= width - corner and y < corner:
            return HTTOPRIGHT
        if x < corner and y >= height - corner:
            return HTBOTTOMLEFT
        if x >= width - corner and y >= height - corner:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
        return 0

    def _invalidate_glass_cache(self) -> None:
        self._glass_cache = None
        self._glass_cache_key = None
        self.update()

    def restore_saved_geometry(self, geometry: WindowGeometry | None) -> None:
        screens = [
            screen.availableGeometry()
            for screen in QGuiApplication.screens()
        ]
        restored = restore_window_rect(
            geometry,
            screens,
            QSize(420, 560),
        )
        self.setGeometry(restored)
        self._expanded_size = restored.size()

    def current_window_geometry(self) -> WindowGeometry:
        rect = self.geometry()
        width = max(
            self._expanded_minimum_size.width(),
            self._expanded_size.width(),
        )
        height = max(
            self._expanded_minimum_size.height(),
            self._expanded_size.height(),
        )
        return WindowGeometry(
            x=rect.x(),
            y=rect.y(),
            width=width if self._compact_mode else rect.width(),
            height=height if self._compact_mode else rect.height(),
        )

    @Slot()
    def show_settings_page(self) -> None:
        if self._compact_mode:
            self.set_compact_mode(False)
        self.title_bar.set_settings_page_active(True)
        self._page_stack.setCurrentWidget(self.settings_panel)
        self.settings_panel.focus_api_key(
            Qt.FocusReason.ShortcutFocusReason
        )

    @Slot()
    def show_chat_page(self) -> None:
        if self._api_config is not None:
            self.set_window_opacity(self._api_config.opacity)
        self.title_bar.set_settings_page_active(False)
        self._page_stack.setCurrentWidget(self._chat_page)
        if self._compact_mode:
            self._compact_bar.focus_input()
        else:
            self._question_input.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def current_settings_values(self) -> SettingsValues:
        return self.settings_panel.values()

    @property
    def is_busy(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    @property
    def auto_send_screenshot(self) -> bool:
        return bool(
            self._api_config and self._api_config.auto_send_screenshot
        )

    def set_pending_screenshot(self, image) -> None:
        if self._compact_mode:
            self.set_compact_mode(False)
        self._screenshot_preview.set_image(image)
        self.show_chat_page()
        self._question_input.setFocus()

    def pending_screenshot(self):
        return self._screenshot_preview.image()

    @Slot()
    def send_pending_screenshot(self) -> None:
        self._start_request()

    def send_screen_recognition(
        self,
        image,
        prompt: str,
    ) -> bool:
        if self.is_busy:
            return False
        self.set_pending_screenshot(image)
        self._question_input.setPlainText(prompt)
        self.show_overlay()
        self._start_request(screen_recognition=True)
        return self.is_busy

    @Slot()
    def _remove_pending_screenshot(self) -> None:
        if self.is_busy:
            return
        self._screenshot_preview.clear_image()
        self._status_label.setText("已删除截图")

    def load_api_settings(self, config: AppConfig, api_key: str | None) -> None:
        self._api_config = config
        self._api_key = api_key
        self.settings_panel.set_values(config, api_key)
        self.set_no_focus_mode(config.no_focus_mode)
        self.set_window_opacity(config.opacity)
        self.set_acrylic_enabled(config.acrylic_enabled)
        self.set_hotkey_hint(config.hotkey, config.screenshot_hotkey)
        self.set_compact_mode(config.compact_mode)

    def update_api_settings(self, config: AppConfig, api_key: str) -> None:
        self._api_config = config
        self._api_key = api_key
        self.set_no_focus_mode(config.no_focus_mode)
        self.set_window_opacity(config.opacity)
        self.set_acrylic_enabled(config.acrylic_enabled)
        self.set_hotkey_hint(config.hotkey, config.screenshot_hotkey)
        self.hide_notice()
        self.show_status("设置已更新")

    def set_hotkey_hint(self, chat: str, screenshot: str) -> None:
        self._hotkey_hint_label.setText(
            f"问答 {chat} · 截图 {screenshot}"
        )

    @Slot(str)
    def show_status(self, message: str) -> None:
        self._status_label.setText(message)

    @Slot(str)
    def show_notice(self, message: str) -> None:
        self._notice_label.setText(message)
        self._notice_label.show()

    @Slot()
    def hide_notice(self) -> None:
        self._notice_label.clear()
        self._notice_label.hide()

    def set_settings_status(self, message: str, is_error: bool = False) -> None:
        self.settings_panel.set_status(message, is_error)

    def set_official_mode_badge(self, visible: bool) -> None:
        self.title_bar.set_official_mode_badge(visible)

    def set_official_login_state(self, state: str) -> None:
        self.title_bar.set_official_login_state(state)

    @Slot()
    def prepare_exit(self) -> None:
        self._allow_close = True
        self.close()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._topmost_timer.start()
        QTimer.singleShot(0, self._apply_topmost)
        QTimer.singleShot(0, self._apply_acrylic_material)
        if self._no_focus_mode and not self._temporary_input_focus:
            QTimer.singleShot(0, self._apply_no_activate)

    def hideEvent(self, event: QHideEvent) -> None:
        self._topmost_timer.stop()
        super().hideEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.ActivationChange,
            QEvent.Type.WindowStateChange,
        ):
            self.update()
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.isVisible()
            and not self.isMinimized()
        ):
            QTimer.singleShot(0, self._apply_acrylic_material)
        if event.type() == QEvent.Type.WindowDeactivate and self.isVisible():
            QTimer.singleShot(0, self._apply_topmost)

    def handle_application_state(self, state: Qt.ApplicationState) -> None:
        if state == Qt.ApplicationState.ApplicationInactive and self.isVisible():
            if self._no_focus_mode:
                self._temporary_input_focus = False
                self.title_bar.set_input_mode_active(False)
                self.setAttribute(
                    Qt.WidgetAttribute.WA_ShowWithoutActivating,
                    True,
                )
                QTimer.singleShot(0, self._apply_no_activate)
            QTimer.singleShot(0, self._apply_topmost)

    @Slot()
    def _apply_topmost(self) -> None:
        if not self.isVisible() or not IS_WINDOWS:
            return
        try:
            apply_topmost(int(self.winId()))
            if self._no_focus_mode and not self._temporary_input_focus:
                set_no_activate(int(self.winId()), True)
        except TopmostError as exc:
            self._status_label.setText("置顶失败")
            self._status_label.setToolTip(str(exc))
        except WindowStyleError:
            self._status_label.setText("不抢焦点设置失败")

    @Slot()
    def _apply_no_activate(self) -> None:
        if not IS_WINDOWS:
            return
        try:
            set_no_activate(
                int(self.winId()),
                self._no_focus_mode and not self._temporary_input_focus,
            )
        except WindowStyleError:
            self._status_label.setText("不抢焦点设置失败")

    @Slot()
    def _handle_enter(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self._start_request()

    @Slot()
    def _handle_compact_send(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self.set_compact_mode(False)
        self._start_request()

    @Slot()
    def _handle_send_or_stop(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._request_stop()
        else:
            self._start_request()

    @Slot()
    def _start_request(
        self,
        screen_recognition: bool = False,
    ) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        if self._compact_mode:
            self.set_compact_mode(False)

        question = self._question_input.toPlainText().strip()
        pending_image = self.pending_screenshot()
        if not question and pending_image is None:
            self._status_label.setText("请先输入问题")
            self._question_input.setFocus()
            return

        if (
            self._api_config is not None
            and self._api_config.access_method == "official_browser"
        ):
            if screen_recognition:
                self._screenshot_preview.clear_image()
            self.show_notice(
                "当前是官网浏览器模式：本软件不会向 API 发送问题。"
                "请直接在官网页面输入，或切换回 API 接入。"
            )
            self._status_label.setText("浏览器模式不经过本软件聊天框")
            self.settings_requested.emit()
            return
        if not self._api_config or not self._api_key:
            if screen_recognition:
                self._screenshot_preview.clear_image()
            self.show_notice("尚未配置 API Key，请先打开设置并保存。")
            self.settings_requested.emit()
            return

        try:
            provider = create_chat_provider(self._api_config.access_method)
        except ProviderUnavailableError as exc:
            if screen_recognition:
                self._screenshot_preview.clear_image()
            self.show_notice(str(exc))
            self._status_label.setText("接入方式不可用")
            return

        image_data_url: str | None = None
        if pending_image is not None:
            model_error = provider.image_support_error(
                self._api_config.model
            )
            if model_error:
                if screen_recognition:
                    self._screenshot_preview.clear_image()
                self.show_notice(model_error)
                self._status_label.setText("当前模型不能发送图片")
                return
            try:
                image_data_url = image_to_data_url(
                    pending_image,
                    max_edge=(
                        self._api_config.screen_recognition_image_max_edge
                        if screen_recognition
                        else self._api_config.image_max_edge
                    ),
                )
            except ImagePayloadError as exc:
                if screen_recognition:
                    self._screenshot_preview.clear_image()
                self.show_notice(str(exc))
                self._status_label.setText("截图处理失败")
                return

        if not question:
            question = "请解答这张截图中的题目。"

        try:
            messages = self._chat_session.begin_turn(
                question,
                image_data_url=image_data_url,
            )
        except (RuntimeError, ValueError) as exc:
            if screen_recognition:
                self._screenshot_preview.clear_image()
            self._status_label.setText(str(exc))
            return

        self._pending_question = question
        self._question_input.clear()
        self._compact_bar.set_text("")
        self.hide_notice()
        self.answer_view.begin_response()
        self._stream_kind = ""
        self._stream_message = ""
        self._active_screen_recognition = screen_recognition
        self._set_busy(True)
        if screen_recognition:
            self._status_label.setText("正在识别当前屏幕")

        self._thread = QThread(self)
        self._worker = ProviderChatWorker(
            provider,
            ChatRequest(
                config=self._api_config,
                credential=self._api_key,
                messages=messages,
            ),
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.chunk_ready.connect(self.answer_view.append_chunk)
        self._worker.completed.connect(self._remember_completed)
        self._worker.cancelled.connect(self._remember_cancelled)
        self._worker.failed.connect(self._remember_failed)
        self._worker.completed.connect(self._worker.deleteLater)
        self._worker.cancelled.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._worker.completed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    @Slot()
    def _request_stop(self) -> None:
        if self._worker is None:
            return
        self._worker.request_stop()
        self._send_button.setEnabled(False)
        self._send_button.setText("正在停止...")
        self._status_label.setText("正在停止生成")

    def stop_request_then(self, callback) -> None:
        """Safely stop generation and run an action after cleanup."""
        if self._thread is None or not self._thread.isRunning():
            QTimer.singleShot(0, callback)
            return
        self._after_stop_callback = callback
        self._request_stop()

    @Slot(str)
    def _remember_completed(self, answer: str) -> None:
        self._stream_kind = "completed"
        self._stream_message = answer

    @Slot(str)
    def _remember_cancelled(self, partial_answer: str) -> None:
        self._stream_kind = "cancelled"
        self._stream_message = partial_answer

    @Slot(str)
    def _remember_failed(self, message: str) -> None:
        self._stream_kind = "failed"
        self._stream_message = message

    @Slot()
    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        screen_recognition = self._active_screen_recognition
        self._active_screen_recognition = False
        self._screenshot_preview.clear_image()

        if self._closing_after_stop:
            self._closing_after_stop = False
            self.close()
            return

        if self._stream_kind == "completed":
            self._chat_session.complete_turn(self._stream_message)
            self.answer_view.end_response(True)
            self._status_label.setText(
                "屏幕识别完成"
                if screen_recognition
                else f"回答完成 · 第 {self._chat_session.turn_count} 轮"
            )
        elif self._stream_kind == "cancelled":
            self._chat_session.cancel_turn()
            self.answer_view.end_response(False)
            self._question_input.setPlainText(self._pending_question)
            self._status_label.setText(
                "已取消屏幕识别"
                if screen_recognition
                else "已停止生成"
            )
        else:
            self._chat_session.cancel_turn()
            self.answer_view.show_error(self._stream_message)
            self._question_input.setPlainText(self._pending_question)
            self._status_label.setText(
                "屏幕识别失败"
                if screen_recognition
                else "请求失败"
            )

        self._set_busy(False)
        callback = self._after_stop_callback
        self._after_stop_callback = None
        if callback is not None:
            QTimer.singleShot(0, callback)
            return
        if self._compact_mode:
            self._compact_bar.focus_input()
        else:
            self._question_input.setFocus()

    @Slot()
    def start_new_conversation(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._status_label.setText("请先停止当前生成")
            return
        self._chat_session.clear()
        self.answer_view.show_placeholder()
        self._question_input.clear()
        self._compact_bar.set_text("")
        self._screenshot_preview.clear_image()
        self.hide_notice()
        self._status_label.setText("新对话")
        self._question_input.setFocus()

    def _set_busy(self, busy: bool) -> None:
        self._question_input.setEnabled(not busy)
        self._compact_bar.input.setEnabled(not busy)
        self._compact_bar.set_send_enabled(not busy)
        self._screenshot_button.setEnabled(not busy)
        self._screenshot_preview.remove_button.setEnabled(not busy)
        self._new_conversation_button.setEnabled(not busy)
        self._send_button.setEnabled(True)
        self._send_button.setText("停止" if busy else "发送")
        self._send_button.setProperty("danger", busy)
        self._send_button.style().unpolish(self._send_button)
        self._send_button.style().polish(self._send_button)
        self._status_label.setText("正在生成" if busy else self._status_label.text())

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._allow_close:
            self.hide()
            event.ignore()
            return

        if self._thread is not None and self._thread.isRunning():
            self._closing_after_stop = True
            if self._worker is not None:
                self._worker.request_stop()
            self._send_button.setEnabled(False)
            self._status_label.setText("正在停止...")
            event.ignore()
            return

        event.accept()
        self._background_renderer.shutdown()
        self._screenshot_preview.clear_image()
        self.shutdown_complete.emit()
