"""Exclusive glass-style option buttons for access methods and modes."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class SelectionOption:
    key: str
    label: str
    enabled: bool
    subtitle: str = ""
    unavailable_reason: str = ""


class SelectionGroup(QWidget):
    changed = Signal(str)

    def __init__(
        self,
        options: tuple[SelectionOption, ...],
        parent: QWidget | None = None,
        *,
        vertical: bool = False,
    ) -> None:
        super().__init__(parent)
        self._options = options
        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = (
            QVBoxLayout(self)
            if vertical
            else QHBoxLayout(self)
        )
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for option in options:
            button = QPushButton()
            button.setObjectName("selectionOption")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(58)
            subtitle = option.subtitle
            if not option.enabled:
                subtitle = "即将支持"
                button.setToolTip(
                    option.unavailable_reason or "将在后续阶段实现"
                )
            button.setText(f"{option.label}\n{subtitle}".strip())
            button.setAccessibleName(option.label)
            button.setAccessibleDescription(subtitle)
            button.setEnabled(option.enabled)
            button.clicked.connect(
                lambda _checked=False, key=option.key: self.changed.emit(key)
            )
            self._group.addButton(button)
            self._buttons[option.key] = button
            layout.addWidget(button, 1)

    def selected_key(self) -> str:
        for key, button in self._buttons.items():
            if button.isChecked():
                return key
        return ""

    def set_selected(self, key: str) -> None:
        button = self._buttons.get(key)
        if button is None or not button.isEnabled():
            return
        button.setChecked(True)

    def button_for(self, key: str) -> QPushButton:
        return self._buttons[key]

    def set_option_enabled(
        self,
        key: str,
        enabled: bool,
        subtitle: str,
        reason: str = "",
    ) -> None:
        button = self._buttons.get(key)
        if button is None:
            return
        option = next(
            option for option in self._options if option.key == key
        )
        button.setEnabled(enabled)
        button.setText(f"{option.label}\n{subtitle}".strip())
        button.setToolTip(reason if not enabled else "")
        button.setAccessibleDescription(subtitle)
