"""Main-process controller for the isolated Official WebEngine host."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .official_web_component import ComponentStatus


class OfficialWebProcessManager(QObject):
    """Own one external host process; never import QtWebEngine in the parent."""

    state_changed = Signal(str, str)
    login_state_changed = Signal(str)
    browser_event = Signal(str)
    chromium_version_changed = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        *,
        parent: QObject | None = None,
        process_factory=None,
    ) -> None:
        super().__init__(parent)
        self._process_factory = process_factory or QProcess
        self._process = None
        self._status: ComponentStatus | None = None
        self._session_dir: Path | None = None
        self._login_state = "unknown"
        self._browser_mode = False
        self._browser_visible = False
        self._chromium_version = ""
        self._buffer = b""

    @property
    def is_running(self) -> bool:
        return self._process is not None

    @property
    def login_state(self) -> str:
        return self._login_state

    @property
    def browser_mode(self) -> bool:
        return self._browser_mode

    @property
    def browser_visible(self) -> bool:
        return self._browser_visible

    @property
    def chromium_version(self) -> str:
        return self._chromium_version

    def start(
        self,
        status: ComponentStatus,
        *,
        session_dir: Path,
        browser_mode: bool = False,
        interface_name: str = "",
        logo_path: str = "",
        opacity: float = 1.0,
    ) -> bool:
        if self._process is not None:
            return True
        if not status.installed or status.entrypoint is None:
            self.failed.emit(status.message)
            return False
        session_dir.mkdir(parents=True, exist_ok=True)
        process = self._process_factory()
        process.setProgram(str(status.entrypoint))
        arguments = [
            "--profile-dir",
            str(session_dir),
        ]
        if browser_mode:
            arguments.extend(
                (
                    "--browser-mode",
                    "--interface-name",
                    interface_name or "超级奶蛙助手",
                    "--logo-path",
                    logo_path,
                    "--opacity",
                    f"{max(0.2, min(1.0, float(opacity))):.3f}",
                )
            )
        process.setArguments(arguments)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_output)
        process.started.connect(self._on_started)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)
        self._process = process
        self._status = status
        self._session_dir = session_dir
        self._browser_mode = bool(browser_mode)
        self._browser_visible = False
        self._chromium_version = ""
        self._login_state = "starting"
        self.state_changed.emit(
            "starting",
            (
                "正在启动 DeepSeek 官网浏览器…"
                if browser_mode
                else "正在启动实验性官网组件…"
            ),
        )
        process.start()
        return True

    def stop(self) -> None:
        process = self._process
        if process is None:
            return
        self._send_command({"command": "shutdown"})
        try:
            process.terminate()
        except (OSError, RuntimeError):
            pass
        if getattr(process, "waitForFinished", lambda _timeout: False)(1500):
            self._clear_process()
            return
        try:
            process.kill()
            process.waitForFinished(2000)
        except (OSError, RuntimeError):
            pass
        self._clear_process()

    def show(self) -> bool:
        sent = self._send_command({"command": "show"})
        if sent:
            self._browser_visible = True
        return sent

    def hide(self) -> bool:
        sent = self._send_command({"command": "hide"})
        if sent:
            self._browser_visible = False
        return sent

    def toggle(self) -> bool:
        if not self.is_running:
            return False
        return self.hide() if self._browser_visible else self.show()

    def set_window_opacity(self, opacity: float) -> bool:
        return self._send_command(
            {
                "command": "set_opacity",
                "value": max(0.2, min(1.0, float(opacity))),
            }
        )

    def set_voice_state(self, state: str) -> bool:
        return self._send_command(
            {"command": "set_voice_state", "state": state}
        )

    def set_brand(self, interface_name: str, logo_path: str) -> bool:
        return self._send_command(
            {
                "command": "set_brand",
                "interface_name": interface_name,
                "logo_path": logo_path,
            }
        )

    def set_message(self, message: str) -> bool:
        return self._send_command(
            {"command": "set_message", "message": message}
        )

    def _send_command(self, payload: dict[str, object]) -> bool:
        process = self._process
        if process is None:
            return False
        try:
            encoded = (
                json.dumps(payload, ensure_ascii=True) + "\n"
            ).encode("utf-8")
            if process.write(encoded) < 0:
                return False
            if hasattr(process, "waitForBytesWritten"):
                process.waitForBytesWritten(200)
            return True
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            return False

    def _read_output(self) -> None:
        process = self._process
        if process is None:
            return
        data = bytes(process.readAllStandardOutput())
        if not data:
            return
        self._buffer += data
        while b"\n" in self._buffer:
            raw, self._buffer = self._buffer.split(b"\n", 1)
            self._handle_event(raw.strip())

    def _handle_event(self, raw: bytes) -> None:
        if not raw:
            return
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(event, dict):
            return
        state = str(event.get("login_state", ""))
        if state in {"logged_in", "logged_out", "expired", "unknown"}:
            self._login_state = state
            self.login_state_changed.emit(state)
        status = str(event.get("status", ""))
        if status:
            self.state_changed.emit(status, str(event.get("message", "")))
        event_name = str(event.get("event", ""))
        if event_name == "browser_ready":
            self._browser_visible = True
            self.browser_event.emit("browser_ready")
            version = str(event.get("chromium_version", "")).strip()
            if version:
                self._chromium_version = version
                self.chromium_version_changed.emit(version)
        elif event_name == "browser_closed":
            self._browser_visible = False
        elif event_name in {
            "return_to_main",
            "hidden_to_tray",
            "risk_requested",
            "voice_requested",
            "external_navigation",
            "download_rejected",
            "permission_denied",
        }:
            self.browser_event.emit(event_name)

    def _on_started(self) -> None:
        self.state_changed.emit("started", "官网组件已启动。")

    def _on_finished(self, _exit_code: int, _status) -> None:
        self._login_state = "stopped"
        self._browser_visible = False
        self.state_changed.emit("stopped", "官网组件已退出。")
        self._clear_process()

    def _on_error(self, _error) -> None:
        self.failed.emit("官网组件启动失败，请检查组件是否完整。")

    def _clear_process(self) -> None:
        process = self._process
        self._process = None
        self._browser_visible = False
        if process is not None:
            process.deleteLater()
