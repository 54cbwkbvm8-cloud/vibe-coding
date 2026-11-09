"""无边框窗口的自定义标题栏。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from ..personalization_runtime import BrandRuntime, current_brand_runtime
from ..theme import THEME
from .brand_assets import LOGO_LOGICAL_SIZE, title_logo_pixmap


class TrafficLightButton(QAbstractButton):
    """Small macOS-style control with explicit hover and press feedback."""

    def __init__(
        self,
        color: str,
        tooltip: str,
        symbol: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._symbol = symbol
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(THEME.traffic_size, THEME.traffic_size)

    def set_symbol(self, symbol: str) -> None:
        self._symbol = symbol
        self.update()

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QRectF(self.rect()).center()
        radius = THEME.traffic_dot / 2
        if self.isDown():
            radius -= 0.6

        if self.underMouse() or self.isDown():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 40 if self.isDown() else 26))
            painter.drawEllipse(center, radius + 4.2, radius + 4.2)

        color = self._color
        if self.isDown():
            color = color.darker(118)
        painter.setPen(QPen(QColor(255, 255, 255, 58), 0.8))
        painter.setBrush(color)
        painter.drawEllipse(center, radius, radius)

        if not (self.underMouse() or self.isDown()):
            return

        painter.setPen(QPen(QColor(50, 42, 32, 205), 1.5))
        left = center.x() - radius * 0.48
        right = center.x() + radius * 0.48
        top = center.y() - radius * 0.48
        bottom = center.y() + radius * 0.48
        if self._symbol == "close":
            painter.drawLine(QPoint(round(left), round(top)), QPoint(round(right), round(bottom)))
            painter.drawLine(QPoint(round(right), round(top)), QPoint(round(left), round(bottom)))
        elif self._symbol == "minimize":
            painter.drawLine(QPoint(round(left), round(center.y())), QPoint(round(right), round(center.y())))
        elif self._symbol == "compact":
            painter.drawLine(QPoint(round(left), round(top)), QPoint(round(right), round(bottom)))
            painter.drawLine(QPoint(round(right), round(top)), QPoint(round(left), round(bottom)))
        elif self._symbol == "maximize":
            painter.drawRect(
                int(left),
                int(top + radius * 0.12),
                int(right - left),
                int(bottom - top - radius * 0.24),
            )
        elif self._symbol == "restore":
            rect_width = int(right - left)
            rect_height = int(bottom - top - radius * 0.24)
            painter.drawRect(
                int(left),
                int(top + radius * 0.12),
                rect_width,
                rect_height,
            )
            painter.drawRect(
                int(left + 2),
                int(top - 1),
                rect_width,
                rect_height,
            )
        else:
            painter.drawLine(QPoint(round(left), round(center.y())), QPoint(round(right), round(center.y())))
            painter.drawLine(QPoint(round(center.x()), round(top)), QPoint(round(center.x()), round(bottom)))


class TitleBar(QWidget):
    """显示标题、关闭按钮，并让用户拖动整个窗口。"""

    close_requested = Signal()
    minimize_requested = Signal()
    compact_toggle_requested = Signal()
    settings_requested = Signal()
    input_requested = Signal()
    official_risk_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_offset: QPoint | None = None
        self._compact_mode = False
        self._interface_name = current_brand_runtime().interface_name

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(5)

        traffic_row = QWidget()
        traffic_row.setFixedWidth(
            THEME.traffic_size * 3 + 3 * 2
        )
        traffic_layout = QHBoxLayout(traffic_row)
        traffic_layout.setContentsMargins(0, 0, 0, 0)
        traffic_layout.setSpacing(3)

        self.close_button = TrafficLightButton(
            THEME.danger,
            "隐藏到托盘",
            "close",
            self,
        )
        self.minimize_button = TrafficLightButton(
            THEME.warning,
            "最小化",
            "minimize",
            self,
        )
        self.compact_button = TrafficLightButton(
            THEME.success,
            "紧凑模式",
            "compact",
            self,
        )
        traffic_layout.addWidget(self.close_button)
        traffic_layout.addWidget(self.minimize_button)
        traffic_layout.addWidget(self.compact_button)

        self.logo = QLabel()
        self.logo.setObjectName("titleLogo")
        self.logo.setFixedSize(LOGO_LOGICAL_SIZE, LOGO_LOGICAL_SIZE)
        self.logo.setPixmap(title_logo_pixmap())
        self.logo.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )

        self.title_label = QLabel(self._interface_name)
        self.title_label.setObjectName("titleLabel")
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.setMinimumWidth(0)
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.title_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.title_label.setToolTip(self._interface_name)

        self.settings_button = QToolButton()
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setText("设置")
        self.settings_button.setToolTip("设置")
        self.settings_button.setFixedSize(52, 28)
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.clicked.connect(
            lambda: self.settings_requested.emit()
        )

        self.input_button = QToolButton()
        self.input_button.setObjectName("settingsButton")
        self.input_button.setText("输入")
        self.input_button.setToolTip("临时进入可输入模式")
        self.input_button.setFixedSize(52, 28)
        self.input_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.input_button.clicked.connect(
            lambda: self.input_requested.emit()
        )
        self.input_button.hide()

        self.official_badge = QToolButton()
        self.official_badge.setObjectName("officialRiskBadge")
        self.official_badge.setText("实验性·非官方")
        self.official_badge.setToolTip("点击查看官网账号接入风险说明")
        self.official_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.official_badge.setFixedHeight(22)
        self.official_badge.setMaximumWidth(112)
        self.official_badge.clicked.connect(
            self.official_risk_requested.emit
        )
        self.official_badge.hide()

        self.close_button.clicked.connect(lambda: self.close_requested.emit())
        self.minimize_button.clicked.connect(
            lambda: self.minimize_requested.emit()
        )
        self.compact_button.clicked.connect(
            lambda: self.compact_toggle_requested.emit()
        )

        layout.addWidget(traffic_row)
        layout.addWidget(self.logo)
        layout.addWidget(self.title_label, 1)
        layout.addWidget(self.official_badge)
        layout.addStretch()
        layout.addWidget(self.input_button)
        layout.addWidget(self.settings_button)

        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFixedHeight(THEME.title_height)

    @property
    def interface_name(self) -> str:
        return self._interface_name

    def apply_brand(self, runtime: BrandRuntime) -> None:
        self._interface_name = runtime.interface_name
        self.logo.setPixmap(title_logo_pixmap())
        self.title_label.setToolTip(runtime.interface_name)
        QTimer.singleShot(0, self._update_elided_title)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_elided_title)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._update_elided_title)

    def _update_elided_title(self) -> None:
        available = max(0, self.title_label.width())
        if available <= 0:
            self.title_label.setText(self._interface_name)
            return
        metrics = self.title_label.fontMetrics()
        displayed = metrics.elidedText(
            self._interface_name,
            Qt.TextElideMode.ElideRight,
            available,
        )
        self.title_label.setText(displayed)

    def set_no_focus_mode(self, enabled: bool) -> None:
        self.input_button.setVisible(enabled)

    def set_input_mode_active(self, active: bool) -> None:
        self.input_button.setText("输入中" if active else "输入")

    def set_settings_page_active(self, active: bool) -> None:
        self.settings_button.setVisible(not active)

    def set_official_mode_badge(self, visible: bool) -> None:
        self.official_badge.setVisible(bool(visible))

    def set_official_login_state(self, state: str) -> None:
        if state == "logged_in":
            self.official_badge.setToolTip(
                "官网账号已登录。点击查看实验性功能风险说明"
            )
        elif state == "logged_out":
            self.official_badge.setToolTip(
                "官网账号未登录。点击查看实验性功能风险说明"
            )
        else:
            self.official_badge.setToolTip(
                "官网账号接入实验性功能。点击查看风险说明"
            )

    def set_compact_mode(self, enabled: bool) -> None:
        self._compact_mode = enabled
        label = "展开窗口" if enabled else "紧凑模式"
        self.compact_button.setToolTip(label)
        self.compact_button.setAccessibleName(label)
        self.compact_button.set_symbol("expand" if enabled else "compact")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self.window().frameGeometry().topLeft()
            )
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)

        super().mouseReleaseEvent(event)
