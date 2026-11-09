"""支持 Enter 发送和 Shift+Enter 换行的输入框。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QPlainTextEdit, QWidget


class QuestionInput(QPlainTextEdit):
    """把键盘操作转换成明确的应用信号。"""

    send_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("输入问题...")
        self.setFixedHeight(108)
        self.setTabChangesFocus(True)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        is_enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        has_shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if is_enter and not has_shift:
            self.send_requested.emit()
            event.accept()
            return

        super().keyPressEvent(event)
