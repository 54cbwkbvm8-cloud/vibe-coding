"""Isolated QtWebEngine login host for the experimental access method."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QVBoxLayout,
    QWidget,
)


def emit_event(**payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def self_check() -> int:
    from PySide6.QtWebEngineCore import QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView

    app = QApplication([])
    profile = QWebEngineProfile()
    view = QWebEngineView()
    view.setPage(
        __import__(
            "PySide6.QtWebEngineCore",
            fromlist=["QWebEnginePage"],
        ).QWebEnginePage(profile)
    )
    view.resize(320, 240)
    view.hide()

    def finish() -> None:
        emit_event(status="self_check", ok=True)
        app.quit()

    QTimer.singleShot(1200, finish)
    app.exec()
    return 0


class LoginHostWindow(QWidget):
    def __init__(self, profile, session_dir: Path) -> None:
        super().__init__()
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self._page = QWebEnginePage(profile, self)
        self._view.setPage(self._page)
        self._session_dir = session_dir
        self._last_state = ""
        self.setWindowTitle("DeepSeek 官网账号登录（实验性）")
        self.resize(920, 760)
        self.setStyleSheet(
            "QWidget { background: #14171f; color: #f5f1e8; }"
            "QLabel { padding: 8px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        hint = QLabel(
            "实验性 · 非官方 · 有账号风险。"
            "请只使用自己的账号；验证码和风险提示由官网页面处理。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(self._view, 1)
        self._view.loadFinished.connect(self._load_finished)
        self._view.urlChanged.connect(lambda _url: self._inspect())
        self._view.load(QUrl("https://chat.deepseek.com/"))
        self._poll = QTimer(self)
        self._poll.setInterval(1200)
        self._poll.timeout.connect(self._inspect)
        self._poll.start()

    def _load_finished(self, ok: bool) -> None:
        emit_event(status="loaded" if ok else "load_failed")
        self._inspect()

    def _inspect(self) -> None:
        from ai_quiz_overlay.services.official_web_selectors import (
            LOGIN_PATH,
            LOGIN_SUCCESS_SELECTORS,
        )

        script = (
            "(() => {"
            f"const loginPath={json.dumps(LOGIN_PATH)};"
            f"const selectors={json.dumps(list(LOGIN_SUCCESS_SELECTORS))};"
            "const hasLogin=location.pathname.includes(loginPath);"
            "const hasChat=selectors.some((s)=>!!document.querySelector(s));"
            "return hasLogin ? 'logged_out' : (hasChat ? 'logged_in' : "
            "'unknown');"
            "})()"
        )

        def callback(value) -> None:
            state = str(value or "unknown")
            if state != self._last_state:
                self._last_state = state
                emit_event(login_state=state)

        self._page.runJavaScript(script, callback)

    def closeEvent(self, event) -> None:
        self._poll.stop()
        emit_event(status="stopped")
        super().closeEvent(event)


def run() -> int:
    if "--browser-mode" in sys.argv:
        from official_web_browser_host import run_browser

        return run_browser()
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--profile-dir", type=Path)
    args = parser.parse_args()
    if args.self_check:
        return self_check()
    if args.profile_dir is None:
        parser.error("--profile-dir is required")

    from PySide6.QtWebEngineCore import QWebEngineProfile

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    profile = QWebEngineProfile("official-web", app)
    profile.setPersistentStoragePath(str(args.profile_dir))
    profile.setCachePath(str(args.profile_dir / "cache"))
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
    )
    window = LoginHostWindow(profile, args.profile_dir)
    window.show()
    emit_event(status="started")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
