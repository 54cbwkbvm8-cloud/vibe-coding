"""Central liquid-glass design tokens and Qt stylesheet."""

from __future__ import annotations

from dataclasses import dataclass


GLASS_OPACITY_MIN = 0.20
GLASS_OPACITY_MAX = 1.0
GLASS_PANEL_MIN_ALPHA = 150
GLASS_PANEL_MAX_ALPHA = 226


@dataclass(frozen=True)
class GlassTheme:
    window_radius: int = 28
    panel_radius: int = 20
    control_radius: int = 14
    compact_height: int = 150
    shadow_margin: int = 0
    resize_border: int = 8
    resize_corner: int = 18
    title_height: int = 52
    traffic_size: int = 28
    traffic_dot: int = 13
    animation_ms: int = 150
    text: str = "#f7f8fb"
    text_soft: str = "#d7dbea"
    text_muted: str = "#d2d7e5"
    text_disabled: str = "#9197a6"
    accent: str = "#f0c568"
    accent_hover: str = "#ffd980"
    accent_pressed: str = "#daa949"
    danger: str = "#ff6f68"
    warning: str = "#ffbd4a"
    success: str = "#55d878"
    field_top: str = "#151a2c"
    field_bottom: str = "#111626"
    glass_top: str = "#29365f"
    glass_bottom: str = "#151d36"
    border: str = "rgba(255,255,255,52)"
    border_strong: str = "rgba(255,255,255,86)"
    shadow: str = "rgba(0,0,0,92)"
    control_fill: str = "#B90A0E1A"
    control_hover: str = "#D71B233A"
    control_border: str = "#40FFFFFF"
    check_ink: str = "#292116"
    step_button_fill: str = "#18FFFFFF"
    step_button_hover: str = "#30FFFFFF"


THEME = GlassTheme()


def clamp_glass_opacity(value: float) -> float:
    return max(GLASS_OPACITY_MIN, min(GLASS_OPACITY_MAX, float(value)))


def glass_alpha(value: float) -> int:
    """Map the persisted setting to a readable dark scrim alpha."""
    opacity = clamp_glass_opacity(value)
    progress = (opacity - GLASS_OPACITY_MIN) / (
        GLASS_OPACITY_MAX - GLASS_OPACITY_MIN
    )
    return round(
        GLASS_PANEL_MIN_ALPHA
        + progress * (GLASS_PANEL_MAX_ALPHA - GLASS_PANEL_MIN_ALPHA)
    )


def readability_scrim_alpha(value: float) -> int:
    """Fade label backplates in only when glass opacity is low."""
    opacity = clamp_glass_opacity(value)
    if opacity >= 0.75:
        return 0
    progress = (0.75 - opacity) / (0.75 - GLASS_OPACITY_MIN)
    return round(130 * progress)


def build_stylesheet() -> str:
    return f"""
QWidget#mainWindow {{
    background: transparent;
}}

QWidget#glassSurface,
QWidget#contentBody,
QWidget#compactBar,
QStackedWidget {{
    background: transparent;
    border: none;
}}

QLabel {{
    color: {THEME.text};
    background: transparent;
}}

QLabel#titleLabel {{
    color: {THEME.text};
    font-size: 16px;
    font-weight: 700;
    border-radius: 7px;
    padding: 2px 7px;
}}

QLabel#sectionLabel {{
    color: {THEME.text_muted};
    font-size: 11px;
    font-weight: 600;
    border-radius: 6px;
    padding: 2px 6px;
}}

QLabel#shortcutLabel {{
    color: #e1e5ef;
    font-size: 10px;
    background-color: rgba(6, 9, 18, 86);
    border-radius: 6px;
    padding: 1px 5px;
}}

QLabel#hotkeyHint {{
    color: #edf1fb;
    background-color: rgba(6, 9, 18, 96);
    border: 1px solid rgba(255,255,255,20);
    border-radius: 7px;
    padding: 3px 7px;
    font-size: 10px;
}}

QLabel#statusLabel {{
    color: #ffe3a3;
    background-color: rgba(6, 9, 18, 92);
    border-radius: 8px;
    padding: 2px 7px;
    font-size: 10px;
}}

QLabel#noticeLabel {{
    color: #ffe8b6;
    background-color: rgba(112, 74, 16, 180);
    border: 1px solid rgba(240, 197, 104, 150);
    border-radius: 13px;
    padding: 9px 11px;
    font-size: 11px;
}}

QWidget#resizeGrip {{
    background: transparent;
}}

QToolButton#settingsButton {{
    color: {THEME.text_soft};
    background-color: rgba(255,255,255,16);
    border: 1px solid rgba(255,255,255,34);
    border-radius: 14px;
    padding: 0 14px;
    font-size: 11px;
    min-height: 28px;
}}

QToolButton#settingsButton:hover {{
    color: #ffffff;
    background-color: rgba(255,255,255,34);
    border-color: rgba(255,255,255,62);
}}

QToolButton#settingsButton:pressed {{
    background-color: rgba(255,255,255,48);
}}

QToolButton#officialRiskBadge {{
    color: #ffe1a0;
    background-color: rgba(112, 74, 16, 185);
    border: 1px solid rgba(240, 197, 104, 150);
    border-radius: 8px;
    padding: 1px 6px;
    font-size: 9px;
    font-weight: 700;
}}

QToolButton#officialRiskBadge:hover {{
    color: #fff5d5;
    background-color: rgba(139, 92, 18, 220);
    border-color: {THEME.accent_hover};
}}

QDialog#officialRiskDialog {{
    color: {THEME.text};
    background: transparent;
}}

QLabel#officialRiskTitle {{
    color: #fff3c4;
    font-size: 18px;
    font-weight: 700;
    padding: 2px 0 6px 0;
}}

QScrollArea#officialRiskScroll,
QScrollArea#officialRiskScroll > QWidget > QWidget {{
    background-color: rgba(8, 12, 24, 165);
    border: 1px solid rgba(255,255,255,38);
    border-radius: 13px;
}}

QLabel#officialRiskHeading {{
    color: #ffd980;
    font-size: 13px;
    font-weight: 700;
}}

QLabel#officialRiskBody {{
    color: #edf1fb;
    font-size: 12px;
    line-height: 1.45;
}}

QLabel#officialRiskSource,
QLabel#officialRiskPrompt {{
    color: #d7dbea;
    font-size: 11px;
}}

QLabel#officialRiskCountdown {{
    color: #ffe1a0;
    background-color: rgba(112, 74, 16, 145);
    border-radius: 7px;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: 700;
}}

QTextBrowser,
QPlainTextEdit,
QLineEdit,
QSpinBox,
QDoubleSpinBox,
QComboBox {{
    color: {THEME.text};
    background-color: rgba(11, 16, 30, 176);
    border: 1px solid rgba(255,255,255,34);
    border-radius: 16px;
    selection-background-color: rgba(75, 108, 168, 205);
    selection-color: #ffffff;
}}

QTextBrowser {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(38, 46, 78, 145),
        stop:0.55 rgba(17, 23, 43, 172),
        stop:1 rgba(24, 31, 55, 158)
    );
    border: 1px solid rgba(202, 212, 244, 50);
    padding: 4px;
}}

QPlainTextEdit,
QLineEdit,
QSpinBox,
QDoubleSpinBox,
QComboBox {{
    padding: 8px 10px;
    font-size: 13px;
}}

QWidget#largeSpinBox {{
    background-color: rgba(11, 16, 30, 176);
    border: 1px solid rgba(255,255,255,34);
    border-radius: 16px;
}}

QWidget#largeSpinBox:focus {{
    border-color: {THEME.accent};
    background-color: rgba(9, 13, 25, 205);
}}

QLineEdit#largeSpinEditor {{
    color: {THEME.text};
    background: transparent;
    border: none;
    padding: 0;
    font-size: 13px;
    selection-background-color: rgba(75, 108, 168, 205);
    selection-color: #ffffff;
}}

QPlainTextEdit:focus,
QLineEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QComboBox:focus {{
    border: 1px solid {THEME.accent};
    background-color: rgba(9, 13, 25, 205);
}}

QComboBox::drop-down {{
    border: none;
    width: 28px;
}}

QComboBox QAbstractItemView {{
    color: #f7f8fb;
    background-color: #171d30;
    border: 1px solid rgba(255, 221, 145, 130);
    selection-background-color: rgba(240, 197, 104, 105);
    outline: 0;
}}

QProgressBar {{
    color: #f7f8fb;
    background-color: rgba(9, 13, 25, 190);
    border: 1px solid rgba(255,255,255,42);
    border-radius: 9px;
    min-height: 22px;
    text-align: center;
}}

QProgressBar::chunk {{
    border-radius: 8px;
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #d7a846,
        stop:1 #ffe09a
    );
}}

QLabel#listeningLabel {{
    color: #d9f8ff;
    background-color: rgba(30, 103, 125, 150);
    border: 1px solid rgba(111, 228, 255, 135);
    border-radius: 9px;
    padding: 3px 8px;
    font-size: 10px;
}}

QLineEdit#largeSpinEditor:focus {{
    border: none;
    background: transparent;
}}

QLineEdit#compactInput {{
    min-height: 34px;
    border-radius: 14px;
    padding: 5px 12px;
    background-color: rgba(9, 13, 25, 190);
}}

QLineEdit#hotkeyRecorder {{
    background-color: rgba(11, 16, 30, 186);
    border: 1px solid rgba(255,255,255,40);
}}

QLineEdit#hotkeyRecorder:disabled {{
    color: #7f8594;
    background-color: rgba(11, 16, 30, 92);
    border: 1px dashed rgba(255,255,255,34);
}}

QLineEdit#hotkeyRecorder[recording="true"] {{
    border: 2px solid {THEME.accent};
    background-color: rgba(18, 24, 43, 225);
}}

QToolButton#hotkeyResetButton {{
    color: {THEME.text_soft};
    background-color: rgba(255,255,255,18);
    border: 1px solid rgba(255,255,255,42);
    border-radius: 11px;
    padding: 6px 10px;
    min-height: 24px;
}}

QToolButton#hotkeyResetButton:hover {{
    color: #ffffff;
    background-color: rgba(255,255,255,34);
}}

QToolButton#hotkeyResetButton:disabled {{
    color: #777d8b;
    background-color: rgba(255,255,255,8);
    border: 1px dashed rgba(255,255,255,28);
}}

QLabel#hotkeyError {{
    color: #ffc0c0;
    background-color: rgba(93, 28, 34, 165);
    border-radius: 6px;
    padding: 3px 6px;
    font-size: 10px;
}}

QLabel#hotkeyAvailability {{
    color: #c3c9d6;
    background-color: rgba(255,255,255,16);
    border: 1px dashed rgba(255,255,255,42);
    border-radius: 6px;
    padding: 3px 6px;
    font-size: 10px;
}}

QPushButton#sendButton,
QToolButton#compactSendButton {{
    color: #191814;
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {THEME.accent_hover},
        stop:1 {THEME.accent_pressed}
    );
    border: 1px solid rgba(255, 232, 171, 170);
    border-radius: 15px;
    padding: 7px 18px;
    font-size: 12px;
    font-weight: 700;
}}

QPushButton#sendButton:hover,
QToolButton#compactSendButton:hover {{
    background: {THEME.accent_hover};
    border-color: rgba(255, 240, 199, 210);
}}

QPushButton#sendButton:pressed,
QToolButton#compactSendButton:pressed {{
    background: {THEME.accent_pressed};
}}

QPushButton#sendButton:disabled,
QToolButton#compactSendButton:disabled {{
    color: #8c8d92;
    background: rgba(91, 92, 99, 120);
    border-color: rgba(255,255,255,24);
}}

QPushButton#sendButton[danger="true"] {{
    color: #ffffff;
    background-color: #b34b4b;
    border-color: rgba(255,190,190,120);
}}

QPushButton#secondaryButton,
QToolButton#secondaryButton {{
    color: {THEME.text_soft};
    background-color: rgba(255,255,255,18);
    border: 1px solid rgba(255,255,255,40);
    border-radius: 15px;
    padding: 7px 14px;
}}

QPushButton#secondaryButton:hover,
QToolButton#secondaryButton:hover {{
    color: #ffffff;
    background-color: rgba(255,255,255,34);
}}

QPushButton#secondaryButton:pressed,
QToolButton#secondaryButton:pressed {{
    background-color: rgba(255,255,255,48);
}}

QLabel#settingsTitle {{
    color: {THEME.text};
    font-size: 18px;
    font-weight: 700;
    background-color: rgba(6, 9, 18, 105);
    border-radius: 8px;
    padding: 2px 8px;
}}

QTabBar#settingsTabs {{
    background-color: transparent;
    qproperty-drawBase: 0;
}}

QTabBar#settingsTabs::tab {{
    color: {THEME.text_muted};
    background-color: rgba(255,255,255,14);
    border: 1px solid rgba(255,255,255,30);
    border-radius: 10px;
    padding: 8px 3px;
    margin: 6px 2px;
    min-width: 62px;
}}

QTabBar#settingsTabs::tab:selected {{
    color: #ffffff;
    background-color: rgba(240,197,104,42);
    border-color: rgba(240,197,104,150);
}}

QTabBar#settingsTabs::tab:hover:!selected {{
    background-color: rgba(255,255,255,28);
}}

QLabel#settingsGroupTitle {{
    color: {THEME.text};
    font-size: 14px;
    font-weight: 700;
}}

QFrame#settingsDivider {{
    color: rgba(255,255,255,54);
    background-color: rgba(255,255,255,54);
    border: none;
    max-height: 1px;
}}

QPushButton#selectionOption {{
    color: {THEME.text_soft};
    text-align: left;
    background-color: rgba(11, 16, 30, 176);
    border: 1px solid rgba(255,255,255,38);
    border-radius: 13px;
    padding: 8px 10px;
    font-size: 12px;
}}

QPushButton#selectionOption:hover {{
    background-color: rgba(30, 39, 64, 205);
    border-color: rgba(255,255,255,72);
}}

QPushButton#selectionOption:checked {{
    color: #fff3c4;
    background-color: rgba(240,197,104,42);
    border: 1px solid rgba(240,197,104,170);
}}

QPushButton#selectionOption:disabled {{
    color: #9197a6;
    background-color: rgba(11, 16, 30, 92);
    border: 1px dashed rgba(255,255,255,36);
}}

QLabel#settingsFieldLabel {{
    color: {THEME.text_soft};
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 12px;
}}

QLabel#settingsStatus {{
    color: #9be5aa;
    font-size: 11px;
}}

QLabel#settingsStatus[error="true"] {{
    color: #ffaaaa;
}}

QLabel#settingsHint {{
    color: #f0d49a;
    background-color: rgba(8, 12, 24, 110);
    border: 1px solid rgba(240, 197, 104, 50);
    border-radius: 9px;
    padding: 6px 8px;
    font-size: 10px;
}}

QScrollArea#settingsScroll,
QWidget#settingsContent,
QScrollArea#settingsScroll > QWidget > QWidget {{
    background-color: transparent;
    border: none;
}}

QSlider::groove:horizontal {{
    height: 5px;
    background: rgba(255,255,255,38);
    border-radius: 2px;
}}

QSlider::sub-page:horizontal {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(240,197,104,145),
        stop:1 {THEME.accent}
    );
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    width: 18px;
    margin: -7px 0;
    background: {THEME.accent};
    border: 1px solid rgba(255,244,205,210);
    border-radius: 9px;
}}

QCheckBox {{
    color: {THEME.text_soft};
    spacing: 9px;
    font-size: 12px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    background-color: rgba(10, 14, 26, 180);
    border: 1px solid rgba(255,255,255,58);
    border-radius: 5px;
}}

QCheckBox::indicator:checked {{
    background-color: {THEME.accent};
    border: 1px solid #ffe3a1;
}}

QWidget#screenshotPreview {{
    background-color: rgba(255,255,255,14);
    border: 1px solid rgba(255,255,255,36);
    border-radius: 14px;
}}

QWidget#settingsFooter {{
    background-color: rgba(7, 11, 22, 176);
    border-top: 1px solid rgba(255,255,255,38);
}}

QLabel#screenshotThumbnail {{
    background-color: rgba(5, 8, 16, 180);
    border: 1px solid rgba(255,255,255,42);
    border-radius: 10px;
}}

QToolButton#deleteScreenshotButton {{
    color: #ffc6c6;
    background-color: rgba(116, 40, 46, 150);
    border: 1px solid rgba(255,140,140,72);
    border-radius: 12px;
    padding: 6px 10px;
}}

QToolButton#deleteScreenshotButton:hover {{
    background-color: rgba(150, 54, 60, 180);
}}

QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 3px;
}}

QScrollBar::handle:vertical {{
    background: rgba(255,255,255,52);
    min-height: 24px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background: rgba(255,255,255,82);
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QWidget#browserTitleRow,
QWidget#browserToolbar {{
    background-color: rgba(9, 13, 24, 132);
    border: 1px solid rgba(255,255,255,24);
    border-radius: 10px;
}}

QLabel#browserTitle {{
    color: {THEME.text};
    font-size: 13px;
    font-weight: 600;
}}

QWidget#browserContentFrame {{
    background-color: rgba(12, 16, 28, 150);
    border: 1px solid rgba(255,255,255,32);
    border-radius: 18px;
}}

QLineEdit#browserAddress {{
    color: {THEME.text_soft};
    background-color: rgba(4, 8, 18, 150);
    border: 1px solid rgba(255,255,255,36);
    border-radius: 8px;
    padding: 5px 8px;
}}

QLabel#browserVoiceStatus {{
    color: #ffe2a1;
    background-color: rgba(45, 34, 12, 180);
    border: 1px solid rgba(255, 222, 142, 70);
    border-radius: 8px;
    padding: 4px 7px;
}}

QToolButton#browserRiskBadge {{
    color: #ffe2a1;
    background-color: rgba(82, 55, 18, 155);
    border: 1px solid rgba(255, 214, 126, 72);
    border-radius: 8px;
    padding: 3px 7px;
    font-size: 10px;
}}
"""


APP_STYLE = build_stylesheet()
