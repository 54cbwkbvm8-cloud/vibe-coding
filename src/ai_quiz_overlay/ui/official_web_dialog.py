"""Mandatory risk gate and read-only risk viewer for official web access."""

from __future__ import annotations

from collections.abc import Callable
import time

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeyEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..personalization_runtime import current_brand_runtime
from ..services.official_web import (
    OFFICIAL_LOGIN_PRIVACY_URL,
    OFFICIAL_LOGIN_RISK_ITEMS,
    OFFICIAL_LOGIN_RISK_VERSION,
    OFFICIAL_LOGIN_TERMS_READ_DATE,
    OFFICIAL_LOGIN_TERMS_URL,
)
from ..theme import THEME
from .glass_checkbox import GlassCheckBox
from .personalized_background import GlassSurfaceRenderer


RISK_CONFIRMATION_TEXT = "我已阅读并接受风险"
RISK_COUNTDOWN_SECONDS = 30


class NoPasteLineEdit(QLineEdit):
    """Require the acknowledgement phrase to be typed manually."""

    def paste(self) -> None:
        return

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            event.matches(QKeyEvent.StandardKey.Paste)
            or (
                event.key() == Qt.Key.Key_Insert
                and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            )
        ):
            event.accept()
            return
        super().keyPressEvent(event)


class OfficialWebRiskDialog(QDialog):
    """Blocking, scrollable, timed acknowledgement dialog."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        reading_only: bool = False,
        risk_items=None,
        require_countdown: bool = True,
        require_confirmation: bool = True,
        title: str | None = None,
        terms_read_date: str = OFFICIAL_LOGIN_TERMS_READ_DATE,
        clock: Callable[[], float] | None = None,
        activity_probe: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.reading_only = bool(reading_only)
        self._risk_items = (
            tuple(risk_items)
            if risk_items is not None
            else OFFICIAL_LOGIN_RISK_ITEMS
        )
        self._require_countdown = bool(require_countdown)
        self._require_confirmation = bool(require_confirmation)
        self._title = title
        self._terms_read_date = terms_read_date
        self._clock = clock or time.monotonic
        self._activity_probe = activity_probe
        self._last_tick = self._clock()
        self._remaining_ms = 0 if self.reading_only or not (
            self._require_countdown
        ) else (
            RISK_COUNTDOWN_SECONDS * 1000
        )
        self._scroll_complete = False
        self._showing = False
        self._risk_checkboxes: list[GlassCheckBox] = []
        self._brand_runtime = current_brand_runtime()
        self._glass_renderer = GlassSurfaceRenderer(self)
        self._glass_renderer.configure(self._brand_runtime)
        self._glass_renderer.changed.connect(self.update)
        self.setObjectName("officialRiskDialog")
        self.setWindowTitle(title or "官网账号接入风险说明")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(720, 760)
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)
        if not self.reading_only:
            self._timer.start()
        self._update_accept_state()

    @property
    def risk_checkboxes(self) -> list[GlassCheckBox]:
        return self._risk_checkboxes

    @property
    def remaining_seconds(self) -> int:
        return max(0, (self._remaining_ms + 999) // 1000)

    @property
    def countdown_label(self) -> QLabel:
        return self._countdown_label

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        title_label = QLabel(
            self._title
            or (
                "官网账号接入（实验性）风险说明"
                if self.reading_only
                else "启用官网账号接入（实验性）前请完整阅读"
            )
        )
        title_label.setObjectName("officialRiskTitle")
        title_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(title_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("officialRiskScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content = QWidget()
        content.setMinimumHeight(1000)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 10, 12, 10)
        content_layout.setSpacing(10)
        for item in self._risk_items:
            section = QWidget()
            section.setObjectName("officialRiskSection")
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(0, 0, 0, 4)
            section_layout.setSpacing(4)
            heading = QLabel(item.title)
            heading.setObjectName("officialRiskHeading")
            heading.setTextFormat(Qt.TextFormat.PlainText)
            body = QLabel(item.body)
            body.setObjectName("officialRiskBody")
            body.setTextFormat(Qt.TextFormat.PlainText)
            body.setWordWrap(True)
            section_layout.addWidget(heading)
            section_layout.addWidget(body)
            if not self.reading_only:
                checkbox = GlassCheckBox(
                    f"我已阅读并确认第 {len(self._risk_checkboxes) + 1} 条风险"
                )
                checkbox.toggled.connect(
                    lambda _checked: self._update_accept_state()
                )
                self._risk_checkboxes.append(checkbox)
                section_layout.addWidget(checkbox)
            content_layout.addWidget(section)
            divider = QFrame()
            divider.setObjectName("settingsDivider")
            divider.setFrameShape(QFrame.Shape.HLine)
            divider.setFixedHeight(1)
            content_layout.addWidget(divider)
        self.scroll_area.setWidget(content)
        self.scroll_area.verticalScrollBar().valueChanged.connect(
            self._scroll_changed
        )
        layout.addWidget(self.scroll_area, 1)

        source = QLabel(
            "条款读取日期："
            f"{self._terms_read_date}  ·  "
            f'<a href="{OFFICIAL_LOGIN_TERMS_URL}">用户协议</a>  ·  '
            f'<a href="{OFFICIAL_LOGIN_PRIVACY_URL}">隐私政策</a>'
        )
        source.setObjectName("officialRiskSource")
        source.setTextFormat(Qt.TextFormat.RichText)
        source.setOpenExternalLinks(True)
        source.setWordWrap(True)
        layout.addWidget(source)

        self._countdown_label = QLabel()
        self._countdown_label.setObjectName("officialRiskCountdown")
        layout.addWidget(self._countdown_label)
        if self.reading_only or not self._require_countdown:
            self._countdown_label.hide()

        if not self.reading_only and self._require_confirmation:
            prompt = QLabel(
                f'请手动输入“{RISK_CONFIRMATION_TEXT}”。不允许粘贴。'
            )
            prompt.setObjectName("officialRiskPrompt")
            prompt.setWordWrap(True)
            layout.addWidget(prompt)
            self.confirm_edit = NoPasteLineEdit()
            self.confirm_edit.setObjectName("officialRiskConfirmEdit")
            self.confirm_edit.setPlaceholderText(RISK_CONFIRMATION_TEXT)
            self.confirm_edit.textChanged.connect(
                lambda _text: self._update_accept_state()
            )
            layout.addWidget(self.confirm_edit)
        else:
            self.confirm_edit = None  # type: ignore[assignment]

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("关闭" if self.reading_only else "取消")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        self.accept_button = QPushButton("我已阅读并接受，启用")
        self.accept_button.setObjectName("sendButton")
        self.accept_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.accept_button.clicked.connect(self.accept)
        if self.reading_only:
            self.accept_button.hide()
        else:
            buttons.addWidget(self.accept_button)
        layout.addLayout(buttons)

    def _activity_active(self) -> bool:
        if self._activity_probe is not None:
            return bool(self._activity_probe())
        return (
            self.isVisible()
            and not self.isMinimized()
            and self.isActiveWindow()
        )

    def _tick(self) -> None:
        now = self._clock()
        if self._activity_active():
            elapsed_ms = max(0, round((now - self._last_tick) * 1000))
            self._remaining_ms = max(0, self._remaining_ms - elapsed_ms)
        self._last_tick = now
        if not self._require_countdown:
            self._countdown_label.setText("已完成阅读确认")
        else:
            self._countdown_label.setText(
                "可以启用"
                if self._remaining_ms <= 0
                else f"还需阅读 {self.remaining_seconds} 秒"
            )
        self._update_accept_state()

    def _scroll_changed(self, value: int) -> None:
        bar = self.scroll_area.verticalScrollBar()
        if value >= bar.maximum():
            self._scroll_complete = True
        self._update_accept_state()

    def _update_accept_state(self) -> None:
        if self.reading_only:
            return
        typed = not self._require_confirmation or (
            self.confirm_edit is not None
            and self.confirm_edit.text() == RISK_CONFIRMATION_TEXT
        )
        checked = all(
            checkbox.isChecked() for checkbox in self._risk_checkboxes
        )
        next_enabled = (
            self._remaining_ms <= 0
            and self._scroll_complete
            and checked
            and typed
        )
        if self.accept_button.isEnabled() != next_enabled:
            self.accept_button.setEnabled(next_enabled)
            self.accept_button.style().unpolish(self.accept_button)
            self.accept_button.style().polish(self.accept_button)
            self.accept_button.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        glass = self._glass_renderer.pixmap_for(
            max(1, self.width()),
            max(1, self.height()),
            self.devicePixelRatioF(),
            opacity=0.98,
            active=self.isActiveWindow(),
        )
        if not glass.isNull():
            painter.drawPixmap(0, 0, glass)

    def showEvent(self, event) -> None:
        self._showing = True
        self._last_tick = self._clock()
        super().showEvent(event)
        if not self.reading_only and self._require_countdown:
            self._timer.start()
            if self.confirm_edit is not None:
                self.confirm_edit.setFocus()

    def hideEvent(self, event) -> None:
        self._showing = False
        self._timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._timer.stop()
        super().closeEvent(event)

    def reject(self) -> None:
        self._timer.stop()
        super().reject()


class OfficialWebRiskReader(OfficialWebRiskDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent, reading_only=True)
