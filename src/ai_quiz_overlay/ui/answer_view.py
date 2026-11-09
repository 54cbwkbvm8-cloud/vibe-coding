"""显示普通文本和后续流式回答的只读区域。"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QFrame, QTextBrowser, QWidget


class AnswerView(QTextBrowser):
    """无边框只读回答区，提供开始、追加和结束三个清楚的操作。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.document().setDocumentMargin(12)
        self.document().setDefaultStyleSheet(
            "pre, code { font-family: Consolas, monospace; }"
        )
        self._has_answer = False
        self._markdown_text = ""
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(60)
        self._render_timer.timeout.connect(self._render_markdown)
        self.show_placeholder()

    def show_placeholder(self) -> None:
        self._render_timer.stop()
        self._markdown_text = ""
        self._has_answer = False
        self.setHtml(
            '<div style="color:#7f8998; line-height:1.55;">'
            "回答会显示在这里。"
            "</div>"
        )

    def begin_response(self) -> None:
        self._render_timer.stop()
        self._markdown_text = ""
        self._has_answer = False
        self.clear()

    def append_chunk(self, chunk: str) -> None:
        self._markdown_text += chunk
        self._has_answer = True
        if not self._render_timer.isActive():
            self._render_timer.start()

    def end_response(self, completed: bool) -> None:
        self._render_timer.stop()
        if self._markdown_text:
            self._render_markdown()
            return
        if completed and not self._has_answer:
            self.setPlainText("没有可显示的回答。")
        elif not completed and not self._has_answer:
            self.show_placeholder()

    def show_error(self, message: str) -> None:
        self._render_timer.stop()
        suffix = f"\n\n---\n\n**请求失败：** {message}"
        self._markdown_text = f"{self._markdown_text}{suffix}" if self._markdown_text else suffix
        self._has_answer = True
        self._render_markdown()

    @property
    def markdown_text(self) -> str:
        return self._markdown_text

    def _render_markdown(self) -> None:
        if not self._markdown_text:
            return
        self.setMarkdown(self._markdown_text)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()
