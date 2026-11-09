"""创建 Qt 应用并启动主窗口。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from .config import AppConfig, ConfigError, get_config_path, load_config
from .controller import ApplicationController
from .logging_config import (
    configure_logging,
    install_exception_hook,
    log_event,
)
from .platform_support import IS_WINDOWS
from .personalization_runtime import (
    runtime_from_config,
    set_brand_runtime,
)
from .ui.brand_assets import load_app_icon
from .win32.single_instance import SingleInstanceGuard


def run() -> int:
    """启动桌面应用，返回进程退出码。"""
    if os.environ.get("NAIWA_VOICE_BUNDLE_SELFTEST") == "1":
        return _run_voice_bundle_selftest()
    configure_logging()
    app = QApplication(sys.argv)
    install_exception_hook()
    startup_config = AppConfig()
    try:
        startup_config = load_config(get_config_path())
    except ConfigError:
        pass
    runtime = runtime_from_config(startup_config)
    set_brand_runtime(runtime)
    app.setApplicationName("NaiwaGlory")
    app.setApplicationDisplayName(runtime.software_name)
    app.setOrganizationName("LocalStudyTools")
    app.setWindowIcon(load_app_icon(str(runtime.app_icon_path)))
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setQuitOnLastWindowClosed(False)

    instance_guard = SingleInstanceGuard() if IS_WINDOWS else None
    if instance_guard is not None and not instance_guard.acquire():
        log_event("duplicate_instance_blocked")
        dialog = QMessageBox()
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowTitle(runtime.software_name)
        dialog.setText("程序已经在运行。")
        dialog.setInformativeText("请使用现有悬浮窗或托盘图标。")
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.exec()
        return 0

    controller = ApplicationController(app)
    controller.start()
    log_event("app_started")

    try:
        return app.exec()
    finally:
        if instance_guard is not None:
            instance_guard.release()
        log_event("app_exited")


def _run_voice_bundle_selftest() -> int:
    """Verify packaged native audio/ASR dependencies without networking."""
    output_path = os.environ.get("NAIWA_VOICE_SELFTEST_OUTPUT")
    result: dict[str, object] = {"ok": False}
    try:
        import sherpa_onnx
        import sounddevice
        import webrtcvad

        from .services.voice_audio import list_microphone_devices

        devices = list_microphone_devices()
        result = {
            "ok": True,
            "sherpa_onnx_loaded": bool(sherpa_onnx),
            "sounddevice_loaded": bool(sounddevice),
            "webrtcvad_version": getattr(
                webrtcvad,
                "__version__",
                "loaded",
            ),
            "microphone_devices": len(devices),
        }
        return_code = 0
    except Exception as exc:
        result = {
            "ok": False,
            "error_type": type(exc).__name__,
        }
        return_code = 1
    if output_path:
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(result, ensure_ascii=True),
                encoding="utf-8",
            )
        except OSError:
            return_code = 1
    return return_code
