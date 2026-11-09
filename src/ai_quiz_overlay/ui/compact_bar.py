"""One-line input shown while the glass window is compact."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QToolButton, QWidget


class CompactBar(QWidget):
    send_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("compactBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 2, 12, 12)
        layout.setSpacing(8)

        self.input = QLineEdit()
        self.input.setObjectName("compactInput")
        self.input.setPlaceholderText("输入问题，Enter 发送...")
        self.input.returnPressed.connect(lambda: self.send_requested.emit())

        self.send_button = QToolButton()
        self.send_button.setObjectName("compactSendButton")
        self.send_button.setText("发送")
        self.send_button.setToolTip("发送问题")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setFixedHeight(36)
        self.send_button.clicked.connect(lambda: self.send_requested.emit())

        layout.addWidget(self.input, 1)
        layout.addWidget(self.send_button)

    def text(self) -> str:
        return self.input.text()

    def set_text(self, text: str) -> None:
        self.input.setText(text)

    def set_send_enabled(self, enabled: bool) -> None:
        self.send_button.setEnabled(enabled)

    def focus_input(self) -> None:
        self.input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.input.selectAll()
