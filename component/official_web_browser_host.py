"""Isolated browser-only shell for the official DeepSeek website.

This module intentionally has no page-reading or page-modifying calls. It
only supplies normal browser navigation and user-driven input.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import os
import sys
import threading

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QRect,
    QRectF,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCloseEvent,
    QDesktopServices,
    QFont,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEnginePermission,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

try:
    from PySide6.QtWebEngineCore import qWebEngineChromiumVersion
except ImportError:
    qWebEngineChromiumVersion = None

from ai_quiz_overlay.services.browser_policy import (
    OFFICIAL_BROWSER_URL,
    address_display,
    main_frame_action,
    popup_action,
)
from ai_quiz_overlay.theme import APP_STYLE, THEME
from ai_quiz_overlay.ui.glass_renderer import draw_glass_window
from ai_quiz_overlay.ui.title_bar import TrafficLightButton
from ai_quiz_overlay.win32.native_resize import NativeResizeFilter


HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17


def _event(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=True), flush=True)


class _BrowserPage(QWebEnginePage):
    external_navigation = Signal(str)
    popup_navigation = Signal(str)
    permission_requested = Signal()

    def __init__(self, profile, parent=None) -> None:
        super().__init__(profile, parent)
        self._popup_pages: list[QWebEnginePage] = []
        if hasattr(self, "permissionRequested"):
            self.permissionRequested.connect(self._deny_permission)
        if hasattr(self, "featurePermissionRequested"):
            self.featurePermissionRequested.connect(self._deny_feature)

    def _deny_permission(self, permission) -> None:
        try:
            permission.deny()
        except (RuntimeError, AttributeError):
            pass
        self.permission_requested.emit()

    def _deny_feature(self, origin, feature) -> None:
        try:
            self.setFeaturePermission(
                origin,
                feature,
                QWebEnginePage.PermissionPolicy.PermissionDeniedByUser,
            )
        except (RuntimeError, AttributeError):
            pass
        self.permission_requested.emit()

    def acceptNavigationRequest(
        self,
        url: QUrl,
        _navigation_type,
        is_main_frame: bool,
    ) -> bool:
        if not is_main_frame:
            return True
        action = main_frame_action(url.toString())
        if action == "internal":
            return True
        self.external_navigation.emit(url.toString())
        return False

    def createWindow(self, _window_type):
        popup = _PopupPage(self.profile(), self)
        self._popup_pages.append(popup)
        popup.url_requested.connect(self.popup_navigation.emit)
        popup.destroyed.connect(
            lambda _obj=None, p=popup: self._popup_pages.remove(p)
        )
        return popup


class _PopupPage(QWebEnginePage):
    url_requested = Signal(str)

    def acceptNavigationRequest(
        self,
        url: QUrl,
        _navigation_type,
        is_main_frame: bool,
    ) -> bool:
        if not is_main_frame:
            return True
        self.url_requested.emit(url.toString())
        return False


class _LineReader(QThread):
    line_ready = Signal(str)

    def run(self) -> None:
        for line in sys.stdin:
            self.line_ready.emit(line.rstrip("\r\n"))


class BrowserWindow(QWidget):
    return_requested = Signal()
    hidden_requested = Signal()
    risk_requested = Signal()
    voice_requested = Signal()

    def __init__(
        self,
        *,
        profile: QWebEngineProfile,
        profile_dir: Path,
        interface_name: str,
        logo_path: str | None,
        opacity: float,
    ) -> None:
        super().__init__()
        self._profile = profile
        self._profile_dir = profile_dir
        self._opacity = max(0.2, min(1.0, opacity))
        self._drag_offset: QPoint | None = None
        self._resize_user32 = (
            ctypes.WinDLL("user32", use_last_error=True)
            if sys.platform == "win32"
            else None
        )
        self._native_resize_filter = None
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
        self.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )
        self.setMinimumSize(720, 520)
        screen = QGuiApplication.screenAt(self.pos())
        screen = screen or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(1100, max(720, available.width() - 48))
            height = min(800, max(520, available.height() - 48))
            self.resize(width, height)
            self.move(
                available.center().x() - width // 2,
                available.center().y() - height // 2,
            )
        else:
            self.resize(1100, 800)
        self.setWindowTitle(interface_name)
        self.setWindowOpacity(self._opacity)
        self._interface_name = interface_name
        self._logo_path = logo_path
        self._build_ui()
        self._install_resize_filter()
        self._view.urlChanged.connect(self._url_changed)
        self._view.load(QUrl(OFFICIAL_BROWSER_URL))

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(4)

        title_row = QWidget()
        title_row.setObjectName("browserTitleRow")
        title_layout = QHBoxLayout(title_row)
        title_layout.setContentsMargins(6, 2, 6, 2)
        title_layout.setSpacing(6)

        close_button = TrafficLightButton(
            THEME.danger,
            "隐藏到托盘",
            "close",
        )
        close_button.clicked.connect(self.hidden_requested.emit)
        minimize_button = TrafficLightButton(
            THEME.warning,
            "最小化",
            "minimize",
        )
        minimize_button.clicked.connect(self.showMinimized)
        maximize_button = TrafficLightButton(
            THEME.success,
            "最大化/还原",
            "maximize",
        )
        maximize_button.clicked.connect(self._toggle_maximized)
        self._maximize_button = maximize_button
        for button in (close_button, minimize_button, maximize_button):
            title_layout.addWidget(button)

        logo = QLabel()
        if self._logo_path and Path(self._logo_path).is_file():
            pixmap = QPixmap(self._logo_path)
            if not pixmap.isNull():
                logo.setPixmap(
                    pixmap.scaled(
                        28,
                        28,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        logo.setFixedSize(30, 30)
        self._logo_label = logo
        title_layout.addWidget(logo)
        title = QLabel(self._interface_name)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setObjectName("browserTitle")
        self._title_label = title
        title_layout.addWidget(title, 1)
        risk_badge = QToolButton()
        risk_badge.setText("实验性·非官方")
        risk_badge.setToolTip("点击重新阅读浏览器模式风险说明")
        risk_badge.setObjectName("browserRiskBadge")
        risk_badge.clicked.connect(self.risk_requested.emit)
        title_layout.addWidget(risk_badge)
        return_button = QPushButton("返回软件")
        return_button.setObjectName("browserReturnButton")
        return_button.clicked.connect(self.return_requested.emit)
        title_layout.addWidget(return_button)
        title_row.installEventFilter(self)
        self._title_row = title_row
        outer.addWidget(title_row)

        toolbar = QWidget()
        toolbar.setObjectName("browserToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(4, 0, 4, 4)
        toolbar_layout.setSpacing(4)
        back = QToolButton()
        back.setText("←")
        back.setToolTip("后退")
        back.clicked.connect(lambda: self._view.back())
        forward = QToolButton()
        forward.setText("→")
        forward.setToolTip("前进")
        forward.clicked.connect(lambda: self._view.forward())
        reload_button = QToolButton()
        reload_button.setText("↻")
        reload_button.setToolTip("刷新")
        reload_button.clicked.connect(lambda: self._view.reload())
        toolbar_layout.addWidget(back)
        toolbar_layout.addWidget(forward)
        toolbar_layout.addWidget(reload_button)
        self._address = QLineEdit()
        self._address.setReadOnly(True)
        self._address.setObjectName("browserAddress")
        toolbar_layout.addWidget(self._address, 1)
        self._voice_status = QLabel()
        self._voice_status.setObjectName("browserVoiceStatus")
        self._voice_status.hide()
        toolbar_layout.addWidget(self._voice_status)
        voice_button = QPushButton("语音转文字")
        voice_button.setToolTip("转写完成后只复制到剪贴板")
        voice_button.clicked.connect(self.voice_requested.emit)
        self._voice_button = voice_button
        toolbar_layout.addWidget(voice_button)
        outer.addWidget(toolbar)

        content_frame = QWidget()
        content_frame.setObjectName("browserContentFrame")
        self._content_frame = content_frame
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(20, 4, 20, 20)
        content_layout.setSpacing(0)
        self._view = QWebEngineView()
        self._page = _BrowserPage(self._profile, self)
        self._view.setPage(self._page)
        settings = self._view.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
        True,
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
            False,
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanPaste,
            False,
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.ScreenCaptureEnabled,
            False,
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.AllowWindowActivationFromJavaScript,
            False,
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.AllowRunningInsecureContent,
            False,
        )
        self._page.external_navigation.connect(self._open_external)
        self._page.popup_navigation.connect(self._open_popup)
        self._page.permission_requested.connect(
            lambda: _event({"event": "permission_denied"})
        )
        if hasattr(self._profile, "permissionRequested"):
            self._profile.permissionRequested.connect(
                self._deny_profile_permission
            )
        self._profile.downloadRequested.connect(self._reject_download)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(
            self._show_context_menu
        )
        content_layout.addWidget(self._view)
        outer.addWidget(content_frame, 1)

    def _deny_profile_permission(self, permission) -> None:
        try:
            permission.deny()
        except (RuntimeError, AttributeError):
            pass
        _event({"event": "permission_denied"})

    def _url_changed(self, url: QUrl) -> None:
        self._address.setText(address_display(url.toString()))

    def _open_external(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))
        _event({"event": "external_navigation"})

    def _open_popup(self, url: str) -> None:
        if popup_action(url) == "internal":
            self._view.load(QUrl(url))
        else:
            self._open_external(url)

    def _reject_download(self, download) -> None:
        try:
            download.cancel()
        except (RuntimeError, AttributeError):
            pass
        _event({"event": "download_rejected"})

    def _show_context_menu(self, position: QPoint) -> None:
        menu = QMenu(self)
        for label, action in (
            ("复制", QWebEnginePage.WebAction.Copy),
            ("粘贴", QWebEnginePage.WebAction.Paste),
            ("剪切", QWebEnginePage.WebAction.Cut),
            ("全选", QWebEnginePage.WebAction.SelectAll),
        ):
            menu_action = menu.addAction(label)
            menu_action.triggered.connect(
                lambda _checked=False, a=action: self._page.triggerAction(a)
            )
        menu.exec(self._view.mapToGlobal(position))

    def set_window_opacity(self, value: float) -> None:
        self._opacity = max(0.2, min(1.0, value))
        self.setWindowOpacity(self._opacity)

    def set_brand(self, interface_name: str, logo_path: str | None) -> None:
        self._interface_name = interface_name
        self._logo_path = logo_path
        self.setWindowTitle(interface_name)
        self._title_label.setText(interface_name)
        pixmap = QPixmap(logo_path) if logo_path else QPixmap()
        if not pixmap.isNull():
            self._logo_label.setPixmap(
                pixmap.scaled(
                    28,
                    28,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def set_voice_state(self, state: str) -> None:
        listening = state == "listening"
        self._voice_status.setText("正在聆听…" if listening else "")
        self._voice_status.setVisible(listening)
        self._voice_button.setText(
            "停止聆听" if listening else "语音转文字"
        )

    def set_message(self, message: str) -> None:
        if not message:
            return
        self._voice_status.setText(message)
        self._voice_status.show()
        QTimer.singleShot(
            6000,
            lambda text=message: (
                self._voice_status.hide()
                if self._voice_status.text() == text
                else None
            ),
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        draw_glass_window(
            painter,
            self.rect(),
            opacity=self._opacity,
            acrylic_active=False,
            active=self.isActiveWindow(),
        )

    def _toggle_maximized(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self._maximize_button.set_symbol("maximize")
        else:
            self.showMaximized()
            self._maximize_button.set_symbol("restore")

    def eventFilter(self, watched, event) -> bool:
        if watched is self._title_row:
            if event.type() == QEvent.Type.MouseButtonPress:
                mouse = event
                if mouse.button() == Qt.MouseButton.LeftButton:
                    self._drag_offset = (
                        mouse.globalPosition().toPoint()
                        - self.frameGeometry().topLeft()
                    )
                    return True
            elif event.type() == QEvent.Type.MouseMove:
                mouse = event
                if (
                    self._drag_offset is not None
                    and mouse.buttons() & Qt.MouseButton.LeftButton
                ):
                    self.move(
                        mouse.globalPosition().toPoint() - self._drag_offset
                    )
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._drag_offset = None
                    return True
        return super().eventFilter(watched, event)

    def _install_resize_filter(self) -> None:
        if self._resize_user32 is None:
            return
        app = QApplication.instance()
        if app is None:
            return
        self._native_resize_filter = NativeResizeFilter(
            int(self.winId()),
            self._native_hit_test,
        )
        app.installNativeEventFilter(self._native_resize_filter)

    def _native_hit_test(self, global_position: QPoint) -> int:
        if self._resize_user32 is None:
            return 0
        native = wintypes.RECT()
        if not self._resize_user32.GetWindowRect(
            wintypes.HWND(int(self.winId())),
            ctypes.byref(native),
        ):
            return 0
        width = max(1, native.right - native.left)
        height = max(1, native.bottom - native.top)
        local = QPoint(
            min(
                self.width() - 1,
                max(0, round(
                    (global_position.x() - native.left)
                    * self.width()
                    / width
                )),
            ),
            min(
                self.height() - 1,
                max(0, round(
                    (global_position.y() - native.top)
                    * self.height()
                    / height
                )),
            ),
        )
        return self._resize_hit_test_local(local)

    def _resize_hit_test_local(self, position: QPoint) -> int:
        x, y = position.x(), position.y()
        width, height = self.width(), self.height()
        border = 8
        corner = 18
        left, right = x < border, x >= width - border
        top, bottom = y < border, y >= height - border
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

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._native_resize_filter is not None:
            app = QApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(self._native_resize_filter)
            self._native_resize_filter = None
        _event({"event": "browser_closed"})
        super().closeEvent(event)


def run_browser() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-dir", type=Path, required=True)
    parser.add_argument("--interface-name", default="超级奶蛙助手")
    parser.add_argument("--logo-path", default="")
    parser.add_argument("--opacity", type=float, default=1.0)
    args, _ = parser.parse_known_args()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    profile = QWebEngineProfile("official-browser", app)
    profile.setPersistentStoragePath(str(args.profile_dir))
    profile.setCachePath(str(args.profile_dir / "cache"))
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
    )
    window = BrowserWindow(
        profile=profile,
        profile_dir=args.profile_dir,
        interface_name=args.interface_name,
        logo_path=args.logo_path or None,
        opacity=args.opacity,
    )
    reader = _LineReader()

    def command(line: str) -> None:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return
        command_name = payload.get("command")
        if command_name == "show":
            window.show()
            window.raise_()
            window.activateWindow()
        elif command_name == "hide":
            window.hide()
        elif command_name == "toggle":
            if window.isVisible():
                window.hide()
            else:
                window.show()
                window.raise_()
                window.activateWindow()
        elif command_name == "set_opacity":
            window.set_window_opacity(float(payload.get("value", 1.0)))
        elif command_name == "set_voice_state":
            window.set_voice_state(str(payload.get("state", "")))
        elif command_name == "set_message":
            window.set_message(str(payload.get("message", "")))
        elif command_name == "set_brand":
            window.set_brand(
                str(payload.get("interface_name", "超级奶蛙助手")),
                str(payload.get("logo_path", "")) or None,
            )
        elif command_name == "shutdown":
            window.close()
            app.quit()

    reader.line_ready.connect(command)
    reader.start()
    window.return_requested.connect(
        lambda: (_event({"event": "return_to_main"}))
    )
    window.hidden_requested.connect(
        lambda: (_event({"event": "hidden_to_tray"}))
    )
    window.risk_requested.connect(
        lambda: (_event({"event": "risk_requested"}))
    )
    window.voice_requested.connect(
        lambda: (_event({"event": "voice_requested"}))
    )
    window.show()
    chromium_version = ""
    if qWebEngineChromiumVersion is not None:
        try:
            chromium_version = qWebEngineChromiumVersion()
        except (AttributeError, RuntimeError):
            chromium_version = ""
    _event(
        {
            "event": "browser_ready",
            "chromium_version": chromium_version,
        }
    )
    return app.exec()
