"""Checkbox with a painted, high-contrast check mark."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QCheckBox, QWidget

from ..theme import THEME


class GlassCheckBox(QCheckBox):
    """Draw the indicator explicitly so checked state never looks solid-only."""

    def __init__(
        self,
        text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(28)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        indicator_size = 20.0
        indicator = QRectF(
            1.0,
            (self.height() - indicator_size) / 2,
            indicator_size,
            indicator_size,
        )
        checked = self.checkState() == Qt.CheckState.Checked
        hovered = self.underMouse() or self.hasFocus()

        fill = (
            QColor(THEME.accent)
            if checked
            else QColor(THEME.control_fill)
        )
        if checked and self.isDown():
            fill = QColor(THEME.accent_pressed)
        elif not checked and hovered:
            fill = QColor(THEME.control_hover)

        border = (
            QColor("#ffe3a1")
            if checked
            else QColor(THEME.control_border)
        )
        if hovered and not checked:
            border = QColor(THEME.accent)
        if not self.isEnabled():
            fill.setAlpha(100)
            border.setAlpha(70)

        painter.setPen(QPen(border, 1.0))
        painter.setBrush(fill)
        painter.drawRoundedRect(indicator, 5.0, 5.0)

        if checked:
            check_color = QColor(THEME.check_ink)
            if not self.isEnabled():
                check_color.setAlpha(110)
            check_pen = QPen(
                check_color,
                2.2,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
            painter.setPen(check_pen)
            painter.drawPolyline(
                [
                    QPointF(indicator.left() + 4.5, indicator.center().y()),
                    QPointF(indicator.left() + 8.5, indicator.bottom() - 4.5),
                    QPointF(indicator.right() - 3.8, indicator.top() + 5.0),
                ]
            )

        text_color = QColor(
            THEME.text_soft if self.isEnabled() else THEME.text_disabled
        )
        text_rect = QRectF(
            indicator.right() + 8,
            0,
            max(0, self.width() - indicator.right() - 8),
            self.height(),
        )
        shadow_color = QColor(0, 0, 0, 185)
        painter.setPen(shadow_color)
        painter.drawText(
            text_rect.translated(1.0, 1.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.text(),
        )
        painter.setPen(text_color)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.text(),
        )
