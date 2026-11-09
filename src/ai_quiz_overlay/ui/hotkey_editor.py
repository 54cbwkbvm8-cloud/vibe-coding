"""Click-to-record global hotkey editor."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class HotkeyRecorder(QLineEdit):
    recorded = Signal(str)
    recording_started = Signal()
    recording_finished = Signal()
    invalid = Signal(str)

    def __init__(
        self,
        hotkey_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._recording = False
        self._before_recording = hotkey_text
        self.setObjectName("hotkeyRecorder")
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setText(hotkey_text)
        self.setPlaceholderText("点击后按下组合键")
        self.setToolTip("点击输入框，然后直接按 Ctrl/Alt/Shift/Win 组合键")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def recording(self) -> bool:
        return self._recording

    def set_hotkey(self, hotkey_text: str) -> None:
        self._before_recording = hotkey_text
        self.setText(hotkey_text)

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.start_recording()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.stop_recording()
        super().focusOutEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.start_recording()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._recording:
            super().keyPressEvent(event)
            return
        event.accept()
        if event.isAutoRepeat():
            return
        if event.key() == Qt.Key.Key_Escape:
            self.stop_recording()
            return
        if event.key() in {
            Qt.Key.Key_Control,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Meta,
        }:
            return

        modifiers = event.modifiers()
        modifier_bits = (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.MetaModifier
        )
        if not modifiers & modifier_bits:
            self.invalid.emit(
                "快捷键至少需要 Ctrl、Alt、Shift 或 Win 中的一个修饰键。"
            )
            return

        hotkey_text = self._format_hotkey(event)
        if hotkey_text is None:
            self.invalid.emit(
                "当前按键不支持，请使用 A-Z、0-9、F1-F24 或 Space。"
            )
            return

        self._before_recording = hotkey_text
        self.setText(hotkey_text)
        self.stop_recording()
        self.recorded.emit(hotkey_text)

    def start_recording(self) -> None:
        if self._recording or not self.isEnabled():
            return
        self._recording = True
        self._before_recording = self.text()
        self.setProperty("recording", True)
        self.setPlaceholderText("请按下组合键…")
        self.setText("")
        self._refresh_style()
        self.recording_started.emit()

    def stop_recording(self) -> None:
        if not self._recording:
            return
        self._recording = False
        if not self.text():
            self.setText(self._before_recording)
        self.setProperty("recording", False)
        self._refresh_style()
        self.recording_finished.emit()

    def _format_hotkey(self, event: QKeyEvent) -> str | None:
        key = event.key()
        if ord("A") <= key <= ord("Z"):
            key_name = chr(key)
        elif ord("0") <= key <= ord("9"):
            key_name = chr(key)
        elif int(Qt.Key.Key_F1) <= key <= int(Qt.Key.Key_F24):
            key_name = f"F{key - int(Qt.Key.Key_F1) + 1}"
        elif key == Qt.Key.Key_Space:
            key_name = "Space"
        else:
            return None

        modifiers = event.modifiers()
        names: list[str] = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            names.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            names.append("Alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            names.append("Shift")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            names.append("Win")
        return "+".join([*names, key_name])

    def _refresh_style(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class HotkeyEditor(QWidget):
    recorded = Signal(str)
    recording_started = Signal()
    recording_finished = Signal()
    invalid_input = Signal(str)

    def __init__(
        self,
        default_hotkey: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._default = default_hotkey
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.recorder = HotkeyRecorder(default_hotkey, self)
        self.reset_button = QToolButton()
        self.reset_button.setObjectName("hotkeyResetButton")
        self.reset_button.setText("恢复默认")
        self.reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_button.setToolTip(f"恢复为 {default_hotkey}")
        self.reset_button.clicked.connect(self.restore_default)
        row.addWidget(self.recorder, 1)
        row.addWidget(self.reset_button)
        layout.addLayout(row)

        self.error_label = QLabel()
        self.error_label.setObjectName("hotkeyError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self.availability_label = QLabel()
        self.availability_label.setObjectName("hotkeyAvailability")
        self.availability_label.hide()
        layout.addWidget(self.availability_label)

        self.recorder.recorded.connect(self._on_recorded)
        self.recorder.recording_started.connect(
            self.recording_started.emit
        )
        self.recorder.recording_finished.connect(
            self.recording_finished.emit
        )
        self.recorder.invalid.connect(self._on_invalid)

    def value(self) -> str:
        return self.recorder.text().strip()

    def set_value(self, hotkey_text: str) -> None:
        self.recorder.stop_recording()
        self.recorder.set_hotkey(hotkey_text)
        self.clear_error()

    def restore_default(self) -> None:
        self.set_value(self._default)
        self.recorded.emit(self._default)

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()

    def clear_error(self) -> None:
        self.error_label.clear()
        self.error_label.hide()

    def has_error(self) -> bool:
        return not self.error_label.isHidden()

    def set_coming_soon(self, reason: str) -> None:
        self.recorder.stop_recording()
        self.recorder.setEnabled(False)
        self.reset_button.setEnabled(False)
        self.recorder.setToolTip(reason)
        self.reset_button.setToolTip(reason)
        self.availability_label.setText("即将支持")
        self.availability_label.setToolTip(reason)
        self.availability_label.show()

    def _on_invalid(self, message: str) -> None:
        self.set_error(message)
        self.invalid_input.emit(message)

    def _on_recorded(self, hotkey_text: str) -> None:
        self.clear_error()
        self.recorded.emit(hotkey_text)
