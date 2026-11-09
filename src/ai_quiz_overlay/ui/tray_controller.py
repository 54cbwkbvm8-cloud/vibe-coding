"""系统托盘图标和托盘菜单。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ..personalization_runtime import BrandRuntime, current_brand_runtime
from .brand_assets import load_app_icon


def _menu_plain(text: str) -> str:
    return text.replace("&", "&&")


class TrayController(QObject):
    """把托盘菜单动作转换成 Qt 信号。"""

    toggle_requested = Signal()
    show_requested = Signal()
    ball_visibility_requested = Signal()
    about_requested = Signal()
    exit_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        runtime = current_brand_runtime()
        self._tray = QSystemTrayIcon(
            load_app_icon(str(runtime.app_icon_path)),
            self,
        )
        self._tray.setToolTip(runtime.software_name)

        self._menu = QMenu()
        self.show_action = self._menu.addAction(
            _menu_plain(f"显示{runtime.interface_name}")
        )
        self.ball_visibility_action = self._menu.addAction(
            "显示/隐藏悬浮球"
        )
        self.about_action = self._menu.addAction(
            _menu_plain(f"关于 {runtime.software_name}")
        )
        self._menu.addSeparator()
        exit_action = self._menu.addAction("退出")

        self.show_action.triggered.connect(
            lambda: self.show_requested.emit()
        )
        self.ball_visibility_action.triggered.connect(
            lambda: self.ball_visibility_requested.emit()
        )
        self.about_action.triggered.connect(
            lambda: self.about_requested.emit()
        )
        exit_action.triggered.connect(lambda: self.exit_requested.emit())
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)

    @property
    def is_available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    @property
    def is_visible(self) -> bool:
        try:
            return self._tray.isVisible()
        except RuntimeError:
            return False

    def show(self) -> None:
        self._tray.show()

    def apply_brand(self, runtime: BrandRuntime) -> None:
        self._tray.setIcon(load_app_icon(str(runtime.app_icon_path)))
        self._tray.setToolTip(runtime.software_name)
        self.show_action.setText(
            _menu_plain(f"显示{runtime.interface_name}")
        )
        self.about_action.setText(
            _menu_plain(f"关于 {runtime.software_name}")
        )

    def hide(self) -> None:
        self._tray.hide()

    def set_ball_visibility_enabled(self, enabled: bool) -> None:
        self.ball_visibility_action.setEnabled(enabled)
        self.ball_visibility_action.setToolTip(
            ""
            if enabled
            else "仅全局助手模式下可显示或隐藏悬浮球。"
        )

    def _on_activated(
        self,
        reason: QSystemTrayIcon.ActivationReason,
    ) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.toggle_requested.emit()
