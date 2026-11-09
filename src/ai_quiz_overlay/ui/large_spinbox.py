"""Composite numeric editor with two large, high-DPI step buttons."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPaintEvent, QPainter, QPen, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QLineEdit,
    QSizePolicy,
    QWidget,
)

from ..theme import THEME


class SpinStepButton(QAbstractButton):
    def __init__(
        self,
        direction: int,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self._direction = direction
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(28, 24)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("增加" if direction > 0 else "减少")
        self.setAccessibleName(self.toolTip())

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        background = QColor(THEME.step_button_fill)
        if self.isDown():
            background = QColor(THEME.accent)
            background.setAlpha(92)
        elif self.underMouse():
            background = QColor(THEME.step_button_hover)
        painter.setPen(QPen(QColor(THEME.control_border), 1))
        painter.setBrush(background)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)

        center = QPointF(self.width() / 2, self.height() / 2)
        width = 5.0
        height = 3.5
        if self._direction > 0:
            points = [
                QPointF(center.x() - width, center.y() + height),
                QPointF(center.x(), center.y() - height),
                QPointF(center.x() + width, center.y() + height),
            ]
        else:
            points = [
                QPointF(center.x() - width, center.y() - height),
                QPointF(center.x(), center.y() + height),
                QPointF(center.x() + width, center.y() - height),
            ]
        painter.setPen(
            QPen(
                QColor(THEME.accent_hover),
                2.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.drawPolyline(points)


class LargeSpinBox(QWidget):
    valueChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 99
        self._single_step = 1
        self._suffix = ""
        self._value = 0
        self._updating = False

        self.setObjectName("largeSpinBox")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(38)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.editor = QLineEdit(self)
        self.editor.setObjectName("largeSpinEditor")
        self.editor.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.editor.textEdited.connect(self._handle_text_edited)
        self.editor.editingFinished.connect(self._commit_editor)
        self.setFocusProxy(self.editor)

        self._up_button = SpinStepButton(1, self)
        self._down_button = SpinStepButton(-1, self)
        self._up_button.clicked.connect(self.stepUp)
        self._down_button.clicked.connect(self.stepDown)
        self._position_children()
        self.setValue(0)

    def minimum(self) -> int:
        return self._minimum

    def maximum(self) -> int:
        return self._maximum

    def singleStep(self) -> int:
        return self._single_step

    def suffix(self) -> str:
        return self._suffix

    def value(self) -> int:
        self._commit_editor()
        return self._value

    def text(self) -> str:
        return self.editor.text()

    def lineEdit(self) -> QLineEdit:
        return self.editor

    def setRange(self, minimum: int, maximum: int) -> None:
        if minimum > maximum:
            raise ValueError("minimum cannot exceed maximum")
        self._minimum = int(minimum)
        self._maximum = int(maximum)
        self.setValue(self._value)

    def setSingleStep(self, step: int) -> None:
        self._single_step = max(1, int(step))

    def setSuffix(self, suffix: str) -> None:
        self._suffix = suffix
        self._update_editor_text()

    def setValue(self, value: int) -> None:
        self._value = max(self._minimum, min(self._maximum, int(value)))
        self._update_editor_text()
        self.valueChanged.emit(self._value)

    def stepBy(self, steps: int) -> None:
        self.setValue(self._value + steps * self._single_step)

    def stepUp(self) -> None:
        self.stepBy(1)

    def stepDown(self) -> None:
        self.stepBy(-1)

    def step_button_rects(self) -> tuple[QRect, QRect]:
        return self._up_button.geometry(), self._down_button.geometry()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._position_children()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            self.stepBy(1 if delta > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)

    def _position_children(self) -> None:
        button_height = self._up_button.height()
        y = max(1, (self.height() - button_height) // 2)
        right = self.width() - 5
        self._up_button.move(right - 60, y)
        self._down_button.move(right - 30, y)
        self.editor.setGeometry(
            10,
            2,
            max(1, self.width() - 82),
            max(1, self.height() - 4),
        )
        self.editor.raise_()
        self._up_button.raise_()
        self._down_button.raise_()

    def _display_text(self) -> str:
        return f"{self._value}{self._suffix}"

    def _update_editor_text(self) -> None:
        if self._updating:
            return
        self._updating = True
        self.editor.setText(self._display_text())
        self.editor.deselect()
        self.editor.setCursorPosition(len(self.editor.text()))
        self._updating = False

    def _parse_value(self, text: str) -> int | None:
        digits = []
        for character in text.strip():
            if not character.isdigit():
                break
            digits.append(character)
        if not digits:
            return None
        return int("".join(digits))

    def _handle_text_edited(self, text: str) -> None:
        parsed = self._parse_value(text)
        if parsed is None:
            return
        bounded = max(self._minimum, min(self._maximum, parsed))
        if bounded != self._value:
            self._value = bounded
            self.valueChanged.emit(bounded)

    def _commit_editor(self) -> None:
        parsed = self._parse_value(self.editor.text())
        if parsed is not None:
            self._value = max(self._minimum, min(self._maximum, parsed))
        self._update_editor_text()
