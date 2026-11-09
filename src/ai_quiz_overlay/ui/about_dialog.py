"""About dialog containing the interface and software names."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QWidget

from ..branding import APP_VERSION
from ..personalization_runtime import current_brand_runtime
from .brand_assets import load_app_icon


def show_about_dialog(parent: QWidget | None = None) -> None:
    runtime = current_brand_runtime()
    dialog = QMessageBox(parent)
    dialog.setWindowTitle(f"关于 {runtime.software_name}")
    dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    dialog.setIconPixmap(
        load_app_icon(str(runtime.app_icon_path)).pixmap(72, 72)
    )
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    dialog.setText(f"{runtime.software_name}\n版本 {APP_VERSION}")
    dialog.setInformativeText(
        f"界面名称：{runtime.interface_name}\n"
        "Windows 桌面 AI 搜题悬浮窗\n\n"
        "设置与 API Key 密文仍保存在原 AIQuizOverlay 配置目录。\n\n"
        "官网账号接入为实验性非官方功能，可能导致账号受限或关闭；"
        "使用前请阅读应用内风险说明。\n\n"
        "官网浏览器模式只显示官网页面，不读取页面内容；截图和语音结果"
        "只复制到系统剪贴板。它不是官方客户端，使用风险由使用者自行承担。"
    )
    dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
    ok_button = dialog.button(QMessageBox.StandardButton.Ok)
    if ok_button is not None:
        ok_button.setText("确定")
    dialog.exec()
