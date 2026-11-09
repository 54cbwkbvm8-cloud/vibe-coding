"""Tabbed access, hotkey, and appearance settings panel."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..config import (
    DEFAULT_ACCESS_METHOD,
    DEFAULT_ASSISTANT_BALL_SIZE,
    DEFAULT_BROWSER_CLIPBOARD_AUTO_CLEAR,
    DEFAULT_BROWSER_CLIPBOARD_CLEAR_SECONDS,
    DEFAULT_SCREEN_RECOGNITION_IMAGE_MAX_EDGE,
    DEFAULT_SCREEN_RECOGNITION_PROMPT,
    DEFAULT_VOICE_AUTO_LISTEN,
    DEFAULT_VOICE_AUTO_SEND,
    DEFAULT_VOICE_ENABLED,
    DEFAULT_VOICE_LANGUAGE,
    DEFAULT_VOICE_MAX_RECORD_SECONDS,
    DEFAULT_VOICE_SILENCE_SECONDS,
    DEFAULT_VOICE_START_TONE_ENABLED,
    DEFAULT_WORK_MODE,
    DEFAULT_BACKGROUND_BLUR,
    DEFAULT_BACKGROUND_DIM,
    DEFAULT_BACKGROUND_MODE,
    MAX_BACKGROUND_DIM,
    MAX_INTERFACE_NAME_LENGTH,
    MAX_SOFTWARE_NAME_LENGTH,
    MIN_BACKGROUND_DIM,
    MAX_ASSISTANT_BALL_SIZE,
    MIN_ASSISTANT_BALL_SIZE,
    AppConfig,
    PersonalizationConfig,
)
from ..hotkey_definitions import HOTKEY_BY_KEY, HOTKEY_DEFINITIONS
from ..services.provider_registry import ACCESS_METHODS
from ..services.official_web import (
    BROWSER_MODE_RISK_VERSION,
    BROWSER_MODE_TERMS_READ_DATE,
    OFFICIAL_LOGIN_RISK_VERSION,
    OFFICIAL_LOGIN_TERMS_READ_DATE,
)
from ..theme import GLASS_OPACITY_MIN, readability_scrim_alpha
from ..win32.hotkey import HotkeyConfigError, parse_hotkey
from ..work_modes import WORK_MODES
from .glass_checkbox import GlassCheckBox
from .hotkey_editor import HotkeyEditor
from .large_spinbox import LargeSpinBox
from .selection_options import SelectionGroup, SelectionOption


PAGE_ACCESS = 0
PAGE_HOTKEYS = 1
PAGE_APPEARANCE = 2
PAGE_RECOGNITION = 3
PAGE_PERSONALIZATION = 4


class KeyboardTabBar(QTabBar):
    """Tab bar with scroll fallback and explicit keyboard cycling."""

    def keyPressEvent(self, event: QKeyEvent) -> None:
        modifiers = event.modifiers()
        if event.key() == Qt.Key.Key_Tab and (
            modifiers & Qt.KeyboardModifier.ControlModifier
        ):
            direction = (
                -1
                if modifiers & Qt.KeyboardModifier.ShiftModifier
                else 1
            )
            self.setCurrentIndex(
                (self.currentIndex() + direction) % self.count()
            )
            event.accept()
            return
        super().keyPressEvent(event)


@dataclass(frozen=True)
class SettingsValues:
    api_key: str
    access_method: str
    work_mode: str
    base_url: str
    model: str
    timeout_seconds: int
    hotkeys: dict[str, str]
    image_max_edge: int
    auto_send_screenshot: bool
    no_focus_mode: bool
    opacity: float
    acrylic_enabled: bool
    assistant_ball_persistent: bool
    assistant_auto_hide_seconds: int
    assistant_ball_size: int
    screen_recognition_auto_send: bool
    screen_recognition_prompt: str
    screen_recognition_image_max_edge: int
    screen_recognition_consent_version: int
    voice_enabled: bool = DEFAULT_VOICE_ENABLED
    voice_auto_listen: bool = DEFAULT_VOICE_AUTO_LISTEN
    voice_auto_send: bool = DEFAULT_VOICE_AUTO_SEND
    voice_language: str = DEFAULT_VOICE_LANGUAGE
    voice_microphone_device: str = ""
    voice_silence_seconds: float = DEFAULT_VOICE_SILENCE_SECONDS
    voice_max_record_seconds: int = DEFAULT_VOICE_MAX_RECORD_SECONDS
    voice_start_tone_enabled: bool = DEFAULT_VOICE_START_TONE_ENABLED
    voice_consent_version: int = 0
    official_login_consent_version: int = 0
    official_login_terms_read_date: str = ""
    official_login_consent_at: str = ""
    browser_mode_consent_version: int = 0
    browser_mode_terms_read_date: str = ""
    browser_mode_consent_at: str = ""
    browser_clipboard_auto_clear_enabled: bool = True
    browser_clipboard_clear_seconds: int = 60
    browser_screen_capture_consent_version: int = 0
    browser_voice_consent_version: int = 0
    personalization: PersonalizationConfig = field(
        default_factory=PersonalizationConfig
    )

    @property
    def hotkey(self) -> str:
        return self.hotkeys["chat"]

    @property
    def screenshot_hotkey(self) -> str:
        return self.hotkeys["screenshot"]


class SettingsPanel(QWidget):
    save_requested = Signal()
    back_requested = Signal()
    opacity_preview = Signal(float)
    hotkey_recording_started = Signal()
    hotkey_recording_finished = Signal()
    assistant_ball_size_preview = Signal(int)
    screen_consent_revoked = Signal()
    voice_consent_revoked = Signal()
    voice_model_download_requested = Signal()
    voice_model_import_requested = Signal()
    background_select_requested = Signal()
    icon_select_requested = Signal(str)
    backgrounds_icons_same_requested = Signal()
    reset_personalization_requested = Signal(str)
    create_shortcut_requested = Signal()
    delete_shortcut_requested = Signal()
    personalization_preview = Signal(object)
    access_method_requested = Signal(str)
    official_component_import_zip_requested = Signal()
    official_component_import_folder_requested = Signal()
    official_login_requested = Signal()
    official_risk_read_requested = Signal()
    official_consent_revoked = Signal()
    browser_mode_requested = Signal()
    browser_risk_read_requested = Signal()
    browser_consent_revoked = Signal()
    browser_screen_consent_revoked = Signal()
    browser_voice_consent_revoked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._acrylic_desired_enabled = True
        self._hotkeys_valid = True
        self._screen_consent_granted = False
        self._voice_consent_granted = False
        self._loading_personalization = False
        self._loading_settings = False
        self._official_component_installed = False
        self._official_consent_current = False
        self._official_login_consent_version = 0
        self._official_login_terms_read_date = ""
        self._official_login_consent_at = ""
        self._browser_mode_consent_version = 0
        self._browser_mode_terms_read_date = ""
        self._browser_mode_consent_at = ""
        self._browser_clipboard_auto_clear_enabled = True
        self._browser_clipboard_clear_seconds = 60
        self._browser_screen_capture_consent_version = 0
        self._browser_voice_consent_version = 0
        self._browser_consent_current = False
        self._browser_chromium_version = ""
        self._app_icon_asset_id = ""
        self._title_logo_asset_id = ""
        self._ball_image_asset_id = ""
        self._background_asset_id = ""
        self._scrim_labels: list[QLabel] = []
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Ignored,
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.tabs_row = QWidget()
        tabs_row_layout = QHBoxLayout(self.tabs_row)
        tabs_row_layout.setContentsMargins(16, 0, 16, 0)
        tabs_row_layout.setSpacing(0)
        self.tabs = KeyboardTabBar()
        self.tabs.setObjectName("settingsTabs")
        self.tabs.setExpanding(True)
        self.tabs.setDrawBase(False)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)
        self.tabs.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tabs.setAccessibleName("设置页导航")
        self.tabs.addTab("接入")
        self.tabs.addTab("快捷键")
        self.tabs.addTab("外观")
        self.tabs.addTab("识别与语音")
        self.tabs.addTab("个性化")
        tabs_row_layout.addWidget(self.tabs)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("settingsPages")
        self.scroll_areas: dict[int, QScrollArea] = {}
        self.page_stack.addWidget(self._build_access_page())
        self.page_stack.addWidget(self._build_hotkey_page())
        self.page_stack.addWidget(self._build_appearance_page())
        self.page_stack.addWidget(
            self._build_screen_recognition_page()
        )
        self.page_stack.addWidget(self._build_personalization_page())
        self.tabs.currentChanged.connect(self.page_stack.setCurrentIndex)
        self.page_stack.currentChanged.connect(self.tabs.setCurrentIndex)
        outer.addWidget(self.tabs_row)
        outer.addWidget(self.page_stack, 1)

        self.status_label = QLabel()
        self.status_label.setObjectName("settingsStatus")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        outer.addWidget(self.status_label)

        footer = QWidget()
        footer.setObjectName("settingsFooter")
        buttons = QHBoxLayout(footer)
        buttons.setContentsMargins(16, 8, 16, 10)
        self.back_button = QPushButton("返回")
        self.back_button.setObjectName("secondaryButton")
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(self.back_requested.emit)
        self.save_button = QPushButton("保存")
        self.save_button.setObjectName("sendButton")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(self.save_requested.emit)
        buttons.addWidget(self.back_button)
        buttons.addStretch()
        buttons.addWidget(self.save_button)
        outer.addWidget(footer)

        self.scroll_area = self.scroll_areas[PAGE_APPEARANCE]
        self._update_tab_scroll_mode()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_tab_scroll_mode()

    def _update_tab_scroll_mode(self) -> None:
        available = max(1, self.tabs.width())
        required = sum(
            self.tabs.tabSizeHint(index).width()
            for index in range(self.tabs.count())
        )
        self.tabs.setUsesScrollButtons(required > available)

    def _build_access_page(self) -> QScrollArea:
        scroll, layout = self._new_page(PAGE_ACCESS)
        layout.addWidget(self._group_title("接入方式"))
        access_options = tuple(
            SelectionOption(
                key=definition.key,
                label=definition.label,
                enabled=definition.enabled,
                subtitle=(
                    "实验性 · 非官方 · 有账号风险"
                    if definition.key == "official_login"
                    else "独立浏览器 · 不读取页面"
                    if definition.key == "official_browser"
                    else "当前可用"
                ),
                unavailable_reason=definition.unavailable_reason,
            )
            for definition in ACCESS_METHODS
        )
        self.access_selection = SelectionGroup(
            access_options,
            vertical=True,
        )
        self.access_selection.set_selected(DEFAULT_ACCESS_METHOD)
        self.access_selection.changed.connect(
            self._access_selection_changed
        )
        layout.addWidget(self.access_selection)

        layout.addWidget(self._group_title("实验性官网组件"))
        official_intro = QLabel(
            "两种官网方式都使用同一个独立可选组件，主程序不会加载 "
            "QtWebEngine。组件必须由本机构建并手动导入，不接受联网下载。"
        )
        official_intro.setObjectName("settingsHint")
        official_intro.setWordWrap(True)
        layout.addWidget(official_intro)
        self.official_component_status_label = QLabel(
            "实验性官网组件尚未导入。"
        )
        self.official_component_status_label.setObjectName("settingsHint")
        self.official_component_status_label.setWordWrap(True)
        layout.addWidget(self.official_component_status_label)

        component_buttons = QHBoxLayout()
        component_buttons.setSpacing(6)
        self.official_import_zip_button = QToolButton()
        self.official_import_zip_button.setObjectName("secondaryButton")
        self.official_import_zip_button.setText("导入组件 ZIP")
        self.official_import_zip_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.official_import_zip_button.clicked.connect(
            self.official_component_import_zip_requested.emit
        )
        self.official_import_folder_button = QToolButton()
        self.official_import_folder_button.setObjectName("secondaryButton")
        self.official_import_folder_button.setText("导入组件文件夹")
        self.official_import_folder_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.official_import_folder_button.clicked.connect(
            self.official_component_import_folder_requested.emit
        )
        component_buttons.addWidget(self.official_import_zip_button)
        component_buttons.addWidget(self.official_import_folder_button)
        layout.addLayout(component_buttons)

        login_buttons = QHBoxLayout()
        login_buttons.setSpacing(6)
        self.official_login_button = QPushButton("打开官网登录面板")
        self.official_login_button.setObjectName("sendButton")
        self.official_login_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.official_login_button.clicked.connect(
            self.official_login_requested.emit
        )
        self.official_risk_button = QToolButton()
        self.official_risk_button.setObjectName("secondaryButton")
        self.official_risk_button.setText("查看风险说明")
        self.official_risk_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.official_risk_button.clicked.connect(
            self.official_risk_read_requested.emit
        )
        login_buttons.addWidget(self.official_login_button)
        login_buttons.addWidget(self.official_risk_button)
        layout.addLayout(login_buttons)
        self.official_revoke_button = QPushButton(
            "撤销同意并清除登录数据"
        )
        self.official_revoke_button.setObjectName("secondaryButton")
        self.official_revoke_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.official_revoke_button.clicked.connect(
            self.official_consent_revoked.emit
        )
        layout.addWidget(self.official_revoke_button)
        self.set_official_web_state(
            installed=False,
            message="实验性官网组件尚未导入。",
            consent_current=False,
        )

        layout.addWidget(
            self._group_title("DeepSeek 官网（浏览器模式）")
        )
        browser_intro = QLabel(
            "只提供浏览器显示和普通鼠标键盘操作。软件不注入脚本、不读取"
            "页面或 Cookie、不自动粘贴或发送；截图和语音结果只复制到"
            "系统剪贴板。"
        )
        browser_intro.setObjectName("settingsHint")
        browser_intro.setWordWrap(True)
        layout.addWidget(browser_intro)
        browser_login_hint = QLabel(
            "当前版本内嵌窗口可用：手机号、微信扫码。"
            "内嵌窗口不支持 Apple 登录；Apple 会跳转到 appleid.apple.com，"
            "当前会交给系统默认浏览器。"
        )
        browser_login_hint.setObjectName("settingsHint")
        browser_login_hint.setWordWrap(True)
        layout.addWidget(browser_login_hint)
        self.browser_status_label = QLabel(
            "接受浏览器模式风险说明并导入组件后才能使用。"
        )
        self.browser_status_label.setObjectName("settingsHint")
        self.browser_status_label.setWordWrap(True)
        layout.addWidget(self.browser_status_label)
        self.browser_chromium_label = QLabel(
            "内嵌 Chromium 版本：启动浏览器后显示"
        )
        self.browser_chromium_label.setObjectName("settingsHint")
        self.browser_chromium_label.setWordWrap(True)
        layout.addWidget(self.browser_chromium_label)
        browser_buttons = QHBoxLayout()
        browser_buttons.setSpacing(6)
        self.browser_open_button = QPushButton("打开官网浏览器")
        self.browser_open_button.setObjectName("sendButton")
        self.browser_open_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.browser_open_button.clicked.connect(
            self.browser_mode_requested.emit
        )
        self.browser_risk_button = QToolButton()
        self.browser_risk_button.setObjectName("secondaryButton")
        self.browser_risk_button.setText("查看浏览器风险")
        self.browser_risk_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.browser_risk_button.clicked.connect(
            self.browser_risk_read_requested.emit
        )
        browser_buttons.addWidget(self.browser_open_button)
        browser_buttons.addWidget(self.browser_risk_button)
        layout.addLayout(browser_buttons)
        self.browser_revoke_button = QPushButton(
            "撤销浏览器同意并清除登录数据"
        )
        self.browser_revoke_button.setObjectName("secondaryButton")
        self.browser_revoke_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.browser_revoke_button.clicked.connect(
            self.browser_consent_revoked.emit
        )
        layout.addWidget(self.browser_revoke_button)
        self._update_browser_controls()

        layout.addWidget(self._group_title("API 配置"))
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(7)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        def add_field(label_text: str, field: QWidget) -> None:
            label = QLabel(label_text)
            label.setObjectName("settingsFieldLabel")
            self._scrim_labels.append(label)
            form.addRow(label, field)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("填写自己的 API Key")
        self.key_toggle_button = QToolButton()
        self.key_toggle_button.setObjectName("secondaryButton")
        self.key_toggle_button.setText("显示")
        self.key_toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.key_toggle_button.clicked.connect(self._toggle_key_visibility)
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(6)
        key_layout.addWidget(self.api_key_edit, 1)
        key_layout.addWidget(self.key_toggle_button)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("https://api.deepseek.com")
        self.base_url_edit.setReadOnly(True)
        self.base_url_edit.setToolTip("1.0.0 起固定为 DeepSeek 官方 API 地址")
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("deepseek-flash")
        self.timeout_spin = LargeSpinBox()
        self.timeout_spin.setObjectName("largeSpinBox")
        self.timeout_spin.setRange(1, 300)
        self.timeout_spin.setSuffix(" 秒")

        add_field("API Key", key_row)
        add_field("Base URL", self.base_url_edit)
        add_field("模型名", self.model_edit)
        add_field("超时", self.timeout_spin)
        layout.addLayout(form)

        layout.addWidget(self._group_title("工作模式"))
        mode_options = tuple(
            SelectionOption(
                key=definition.key,
                label=definition.label,
                enabled=definition.enabled,
                subtitle="当前可用" if definition.enabled else "即将支持",
                unavailable_reason=definition.unavailable_reason,
            )
            for definition in WORK_MODES
        )
        self.work_mode_selection = SelectionGroup(mode_options)
        self.work_mode_selection.set_selected(DEFAULT_WORK_MODE)
        self.work_mode_selection.changed.connect(
            lambda _key: self._update_assistant_controls()
        )
        layout.addWidget(self.work_mode_selection)

        layout.addWidget(self._group_title("助手显示"))
        self.assistant_ball_persistent_checkbox = GlassCheckBox(
            "进入助手模式时默认显示悬浮球"
        )
        layout.addWidget(self.assistant_ball_persistent_checkbox)
        ball_visibility_hint = QLabel(
            "关闭后仍可按助手唤出键提问；显示/隐藏快捷键只临时改变"
            "本次运行中的球显示状态。"
        )
        ball_visibility_hint.setObjectName("settingsHint")
        ball_visibility_hint.setWordWrap(True)
        layout.addWidget(ball_visibility_hint)

        ball_size_label = QLabel("悬浮球大小")
        ball_size_label.setObjectName("settingsFieldLabel")
        self._scrim_labels.append(ball_size_label)
        layout.addWidget(ball_size_label)
        ball_size_row = QWidget()
        ball_size_layout = QHBoxLayout(ball_size_row)
        ball_size_layout.setContentsMargins(0, 0, 0, 0)
        ball_size_layout.setSpacing(8)
        self.assistant_ball_size_slider = QSlider(
            Qt.Orientation.Horizontal
        )
        self.assistant_ball_size_slider.setRange(
            MIN_ASSISTANT_BALL_SIZE,
            MAX_ASSISTANT_BALL_SIZE,
        )
        self.assistant_ball_size_slider.setValue(
            DEFAULT_ASSISTANT_BALL_SIZE
        )
        self.assistant_ball_size_value_label = QLabel(
            f"{DEFAULT_ASSISTANT_BALL_SIZE} px"
        )
        self.assistant_ball_size_value_label.setMinimumWidth(58)
        self.assistant_ball_size_reset_button = QToolButton()
        self.assistant_ball_size_reset_button.setObjectName(
            "hotkeyResetButton"
        )
        self.assistant_ball_size_reset_button.setText("恢复默认")
        self.assistant_ball_size_reset_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.assistant_ball_size_slider.valueChanged.connect(
            self._ball_size_changed
        )
        self.assistant_ball_size_reset_button.clicked.connect(
            lambda: self.assistant_ball_size_slider.setValue(
                DEFAULT_ASSISTANT_BALL_SIZE
            )
        )
        ball_size_layout.addWidget(self.assistant_ball_size_slider, 1)
        ball_size_layout.addWidget(self.assistant_ball_size_value_label)
        ball_size_layout.addWidget(self.assistant_ball_size_reset_button)
        layout.addWidget(ball_size_row)

        self.assistant_auto_hide_spin = LargeSpinBox()
        self.assistant_auto_hide_spin.setObjectName("largeSpinBox")
        self.assistant_auto_hide_spin.setRange(5, 600)
        self.assistant_auto_hide_spin.setSingleStep(5)
        self.assistant_auto_hide_spin.setSuffix(" 秒")
        auto_hide_label = QLabel("气泡无操作自动收起")
        auto_hide_label.setObjectName("settingsFieldLabel")
        self._scrim_labels.append(auto_hide_label)
        layout.addWidget(auto_hide_label)
        layout.addWidget(self.assistant_auto_hide_spin)
        self._update_assistant_controls()
        layout.addStretch()
        return scroll

    def _build_hotkey_page(self) -> QScrollArea:
        scroll, layout = self._new_page(PAGE_HOTKEYS)
        layout.addWidget(self._group_title("全局快捷键"))
        intro = QLabel(
            "点击输入框后直接按下组合键。必须包含 "
            "Ctrl、Alt、Shift 或 Win 中至少一个修饰键。"
        )
        intro.setObjectName("settingsHint")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.hotkey_editors: dict[str, HotkeyEditor] = {}
        for definition in HOTKEY_DEFINITIONS:
            label = QLabel(definition.label)
            label.setObjectName("settingsFieldLabel")
            editor = HotkeyEditor(definition.default, self)
            editor.recorded.connect(
                lambda _text: self._validate_hotkey_editors()
            )
            editor.invalid_input.connect(self._handle_hotkey_invalid)
            editor.recording_started.connect(
                self.hotkey_recording_started.emit
            )
            editor.recording_finished.connect(
                self.hotkey_recording_finished.emit
            )
            if not definition.implemented:
                editor.set_coming_soon("将在后续阶段实现")
            elif definition.key in {"chat", "screenshot"}:
                editor.availability_label.setText(
                    "搜题模式和官网浏览器模式下生效"
                )
                editor.availability_label.show()
            elif definition.key == "ball_visibility":
                editor.availability_label.setText(
                    "仅全局助手模式下生效；浏览器接入时不生效"
                )
                editor.availability_label.show()
            elif definition.key == "assistant":
                editor.availability_label.setText(
                    "仅全局助手模式下生效；浏览器接入时不生效"
                )
                editor.availability_label.show()
            elif definition.key == "screen_recognition":
                editor.availability_label.setText(
                    "两种接入方式和工作模式下都可使用"
                )
                editor.availability_label.show()
            self.hotkey_editors[definition.key] = editor
            row = QVBoxLayout()
            row.setSpacing(3)
            row.addWidget(label)
            row.addWidget(editor)
            layout.addLayout(row)

        self.hotkey_editor = self.hotkey_editors["chat"]
        self.screenshot_hotkey_editor = self.hotkey_editors["screenshot"]
        self.hotkey_edit = self.hotkey_editor.recorder
        self.screenshot_hotkey_edit = self.screenshot_hotkey_editor.recorder
        layout.addStretch()
        return scroll

    def _build_appearance_page(self) -> QScrollArea:
        scroll, layout = self._new_page(PAGE_APPEARANCE)
        layout.addWidget(self._group_title("外观与行为"))

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(7)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        def add_field(label_text: str, field: QWidget) -> None:
            label = QLabel(label_text)
            label.setObjectName("settingsFieldLabel")
            self._scrim_labels.append(label)
            form.addRow(label, field)

        self.image_max_edge_spin = LargeSpinBox()
        self.image_max_edge_spin.setObjectName("largeSpinBox")
        self.image_max_edge_spin.setRange(512, 4096)
        self.image_max_edge_spin.setSingleStep(100)
        self.image_max_edge_spin.setSuffix(" px")

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(round(GLASS_OPACITY_MIN * 100), 100)
        self.opacity_value_label = QLabel(
            f"{round(GLASS_OPACITY_MIN * 100)}%"
        )
        self.opacity_value_label.setMinimumWidth(44)
        self.opacity_slider.valueChanged.connect(
            lambda value: self.opacity_value_label.setText(f"{value}%")
        )
        self.opacity_slider.valueChanged.connect(
            lambda value: self.opacity_preview.emit(value / 100)
        )
        opacity_row = QWidget()
        opacity_layout = QHBoxLayout(opacity_row)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.addWidget(self.opacity_slider, 1)
        opacity_layout.addWidget(self.opacity_value_label)

        add_field("图片长边", self.image_max_edge_spin)
        add_field("透明度", opacity_row)
        layout.addLayout(form)

        self.auto_send_checkbox = GlassCheckBox("截图确定后自动发送")
        self.no_focus_checkbox = GlassCheckBox(
            "不抢焦点（点击“输入”后编辑）"
        )
        self.acrylic_checkbox = GlassCheckBox("系统毛玻璃（Acrylic）")
        self.acrylic_checkbox.setToolTip(
            "系统材质不可用时会显示原因并使用 Qt 自绘玻璃。"
        )
        self.acrylic_checkbox.toggled.connect(
            self._remember_acrylic_preference
        )
        self.acrylic_status_label = QLabel()
        self.acrylic_status_label.setObjectName("settingsHint")
        self.acrylic_status_label.setWordWrap(True)
        self.acrylic_status_label.hide()
        layout.addWidget(self.auto_send_checkbox)
        layout.addWidget(self.no_focus_checkbox)
        layout.addWidget(self.acrylic_checkbox)
        layout.addWidget(self.acrylic_status_label)

        layout.addStretch()
        return scroll

    def _build_screen_recognition_page(self) -> QScrollArea:
        scroll, layout = self._new_page(PAGE_RECOGNITION)
        layout.addWidget(self._group_title("一键识别屏幕"))
        intro = QLabel(
            "按快捷键后只截取鼠标所在屏幕一次。截图仅保存在内存中，"
            "确认隐私说明后才会启用。"
        )
        intro.setObjectName("settingsHint")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.screen_auto_send_checkbox = GlassCheckBox(
            "按键后直接发送"
        )
        self.screen_auto_send_checkbox.setToolTip(
            "关闭时先显示缩略图和可编辑提示词。"
        )
        layout.addWidget(self.screen_auto_send_checkbox)

        image_edge_label = QLabel("屏幕识别图片长边")
        image_edge_label.setObjectName("settingsFieldLabel")
        self._scrim_labels.append(image_edge_label)
        layout.addWidget(image_edge_label)
        self.screen_image_max_edge_spin = LargeSpinBox()
        self.screen_image_max_edge_spin.setObjectName("largeSpinBox")
        self.screen_image_max_edge_spin.setRange(512, 4096)
        self.screen_image_max_edge_spin.setSingleStep(128)
        self.screen_image_max_edge_spin.setSuffix(" px")
        self.screen_image_max_edge_spin.setValue(
            DEFAULT_SCREEN_RECOGNITION_IMAGE_MAX_EDGE
        )
        layout.addWidget(self.screen_image_max_edge_spin)

        prompt_label = QLabel("预设提示词")
        prompt_label.setObjectName("settingsFieldLabel")
        self._scrim_labels.append(prompt_label)
        layout.addWidget(prompt_label)
        self.screen_prompt_edit = QPlainTextEdit()
        self.screen_prompt_edit.setObjectName("screenPromptEdit")
        self.screen_prompt_edit.setPlaceholderText(
            DEFAULT_SCREEN_RECOGNITION_PROMPT
        )
        self.screen_prompt_edit.setMinimumHeight(116)
        self.screen_prompt_edit.setPlainText(
            DEFAULT_SCREEN_RECOGNITION_PROMPT
        )
        layout.addWidget(self.screen_prompt_edit)
        self.screen_prompt_reset_button = QToolButton()
        self.screen_prompt_reset_button.setObjectName(
            "hotkeyResetButton"
        )
        self.screen_prompt_reset_button.setText("恢复默认提示词")
        self.screen_prompt_reset_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.screen_prompt_reset_button.clicked.connect(
            lambda: self.screen_prompt_edit.setPlainText(
                DEFAULT_SCREEN_RECOGNITION_PROMPT
            )
        )
        layout.addWidget(self.screen_prompt_reset_button)

        layout.addWidget(self._group_title("隐私同意"))
        privacy = QLabel(
            "截图会发送给 DeepSeek。屏幕上如果有密码、验证码、聊天记录或"
            "其他隐私内容，请不要使用一键屏幕识别。"
        )
        privacy.setObjectName("settingsHint")
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        self.screen_consent_label = QLabel()
        self.screen_consent_label.setObjectName("settingsHint")
        self.screen_consent_label.setWordWrap(True)
        layout.addWidget(self.screen_consent_label)
        self.screen_revoke_button = QPushButton("撤销同意")
        self.screen_revoke_button.setObjectName("secondaryButton")
        self.screen_revoke_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.screen_revoke_button.clicked.connect(
            self._revoke_screen_consent
        )
        layout.addWidget(self.screen_revoke_button)
        self.set_screen_consent_state(False)

        layout.addWidget(self._group_title("浏览器模式隐私同意"))
        browser_privacy = QLabel(
            "浏览器模式下，截图只复制到系统剪贴板，不经本软件发送。"
            "你自己在官网页面粘贴并发送后，图片会进入 DeepSeek。"
            "语音转写也只在本地完成后复制到剪贴板。"
        )
        browser_privacy.setObjectName("settingsHint")
        browser_privacy.setWordWrap(True)
        layout.addWidget(browser_privacy)
        self.browser_screen_consent_label = QLabel()
        self.browser_screen_consent_label.setObjectName("settingsHint")
        self.browser_screen_consent_label.setWordWrap(True)
        layout.addWidget(self.browser_screen_consent_label)
        self.browser_screen_revoke_button = QPushButton(
            "撤销浏览器截图复制同意"
        )
        self.browser_screen_revoke_button.setObjectName("secondaryButton")
        self.browser_screen_revoke_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.browser_screen_revoke_button.clicked.connect(
            self.browser_screen_consent_revoked.emit
        )
        layout.addWidget(self.browser_screen_revoke_button)
        self.browser_voice_consent_label = QLabel()
        self.browser_voice_consent_label.setObjectName("settingsHint")
        self.browser_voice_consent_label.setWordWrap(True)
        layout.addWidget(self.browser_voice_consent_label)
        self.browser_voice_revoke_button = QPushButton(
            "撤销浏览器语音复制同意"
        )
        self.browser_voice_revoke_button.setObjectName("secondaryButton")
        self.browser_voice_revoke_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.browser_voice_revoke_button.clicked.connect(
            self.browser_voice_consent_revoked.emit
        )
        layout.addWidget(self.browser_voice_revoke_button)
        self.set_browser_screen_consent_state(False)
        self.set_browser_voice_consent_state(False)

        layout.addWidget(self._group_title("语音提问（本地离线）"))
        voice_intro = QLabel(
            "音频只在内存中处理，不写盘，也不会离开这台电脑。"
            "必须先安装本地 SenseVoice 模型。"
        )
        voice_intro.setObjectName("settingsHint")
        voice_intro.setWordWrap(True)
        layout.addWidget(voice_intro)

        self.voice_enabled_checkbox = GlassCheckBox("启用语音")
        layout.addWidget(self.voice_enabled_checkbox)
        self.voice_auto_listen_checkbox = GlassCheckBox(
            "唤出后自动开始聆听"
        )
        self.voice_auto_send_checkbox = GlassCheckBox(
            "识别完自动发送"
        )
        self.voice_start_tone_checkbox = GlassCheckBox(
            "聆听开始时播放轻提示音"
        )
        self.voice_enabled_checkbox.toggled.connect(
            self._update_voice_controls
        )
        layout.addWidget(self.voice_auto_listen_checkbox)
        layout.addWidget(self.voice_auto_send_checkbox)
        layout.addWidget(self.voice_start_tone_checkbox)

        microphone_label = QLabel("麦克风设备")
        microphone_label.setObjectName("settingsFieldLabel")
        self._scrim_labels.append(microphone_label)
        layout.addWidget(microphone_label)
        self.microphone_combo = QComboBox()
        self.microphone_combo.addItem("系统默认输入", "")
        layout.addWidget(self.microphone_combo)

        language_label = QLabel("识别语言")
        language_label.setObjectName("settingsFieldLabel")
        self._scrim_labels.append(language_label)
        layout.addWidget(language_label)
        self.voice_language_combo = QComboBox()
        for key, label in (
            ("zh", "中文"),
            ("auto", "自动"),
            ("en", "English"),
            ("ja", "日本語"),
            ("ko", "한국어"),
            ("yue", "粤语"),
        ):
            self.voice_language_combo.addItem(label, key)
        layout.addWidget(self.voice_language_combo)

        voice_form = QFormLayout()
        voice_form.setContentsMargins(0, 0, 0, 0)
        voice_form.setHorizontalSpacing(12)
        voice_form.setVerticalSpacing(7)
        silence_label = QLabel("静音判定")
        silence_label.setObjectName("settingsFieldLabel")
        self._scrim_labels.append(silence_label)
        self.voice_silence_spin = QDoubleSpinBox()
        self.voice_silence_spin.setRange(0.3, 5.0)
        self.voice_silence_spin.setDecimals(1)
        self.voice_silence_spin.setSingleStep(0.1)
        self.voice_silence_spin.setSuffix(" 秒")
        self.voice_silence_spin.setValue(DEFAULT_VOICE_SILENCE_SECONDS)
        voice_form.addRow(silence_label, self.voice_silence_spin)
        max_record_label = QLabel("最长录音")
        max_record_label.setObjectName("settingsFieldLabel")
        self._scrim_labels.append(max_record_label)
        self.voice_max_record_spin = LargeSpinBox()
        self.voice_max_record_spin.setObjectName("largeSpinBox")
        self.voice_max_record_spin.setRange(5, 120)
        self.voice_max_record_spin.setSuffix(" 秒")
        self.voice_max_record_spin.setValue(
            DEFAULT_VOICE_MAX_RECORD_SECONDS
        )
        voice_form.addRow(max_record_label, self.voice_max_record_spin)
        layout.addLayout(voice_form)

        layout.addWidget(self._group_title("本地模型"))
        self.voice_model_status_label = QLabel("模型未安装")
        self.voice_model_status_label.setObjectName("settingsHint")
        self.voice_model_status_label.setWordWrap(True)
        layout.addWidget(self.voice_model_status_label)
        model_hint = QLabel(
            "模型约 228.4 MiB，不随 exe 打包。只有点击“下载模型”并"
            "再次点击“开始下载”后才会联网。"
        )
        model_hint.setObjectName("settingsHint")
        model_hint.setWordWrap(True)
        layout.addWidget(model_hint)
        model_buttons = QHBoxLayout()
        self.voice_model_download_button = QPushButton("下载模型")
        self.voice_model_download_button.setObjectName("sendButton")
        self.voice_model_download_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.voice_model_download_button.clicked.connect(
            self.voice_model_download_requested.emit
        )
        self.voice_model_import_button = QToolButton()
        self.voice_model_import_button.setObjectName("secondaryButton")
        self.voice_model_import_button.setText("手动导入模型文件夹")
        self.voice_model_import_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.voice_model_import_button.clicked.connect(
            self.voice_model_import_requested.emit
        )
        model_buttons.addWidget(self.voice_model_download_button)
        model_buttons.addWidget(self.voice_model_import_button)
        layout.addLayout(model_buttons)

        layout.addWidget(self._group_title("麦克风隐私同意"))
        voice_privacy = QLabel(
            "录音会使用麦克风，但仅在本机内存中交给 SenseVoice 转写，"
            "日志和配置不会保存音频或识别文字。"
        )
        voice_privacy.setObjectName("settingsHint")
        voice_privacy.setWordWrap(True)
        layout.addWidget(voice_privacy)
        self.voice_consent_label = QLabel()
        self.voice_consent_label.setObjectName("settingsHint")
        self.voice_consent_label.setWordWrap(True)
        layout.addWidget(self.voice_consent_label)
        self.voice_revoke_button = QPushButton("撤销麦克风同意")
        self.voice_revoke_button.setObjectName("secondaryButton")
        self.voice_revoke_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.voice_revoke_button.clicked.connect(
            self._revoke_voice_consent
        )
        layout.addWidget(self.voice_revoke_button)
        self.set_voice_consent_state(False)
        self._update_voice_controls(False)

        layout.addWidget(self._group_title("浏览器剪贴板"))
        clipboard_hint = QLabel(
            "截图和文字复制后会在系统剪贴板中短暂存在。Windows 支持时会"
            "同时标记为不进入剪贴板历史、不上传云剪贴板、不交给剪贴板"
            "监视器处理。自动清除只会删除本软件最后放入且未被替换的内容。"
        )
        clipboard_hint.setObjectName("settingsHint")
        clipboard_hint.setWordWrap(True)
        layout.addWidget(clipboard_hint)
        self.browser_clipboard_auto_clear_checkbox = GlassCheckBox(
            "复制后自动清除剪贴板"
        )
        self.browser_clipboard_auto_clear_checkbox.setChecked(
            DEFAULT_BROWSER_CLIPBOARD_AUTO_CLEAR
        )
        self.browser_clipboard_auto_clear_checkbox.toggled.connect(
            self._update_browser_clipboard_controls
        )
        layout.addWidget(self.browser_clipboard_auto_clear_checkbox)
        clipboard_seconds_label = QLabel("自动清除时间")
        clipboard_seconds_label.setObjectName("settingsFieldLabel")
        self._scrim_labels.append(clipboard_seconds_label)
        layout.addWidget(clipboard_seconds_label)
        self.browser_clipboard_seconds_spin = LargeSpinBox()
        self.browser_clipboard_seconds_spin.setObjectName("largeSpinBox")
        self.browser_clipboard_seconds_spin.setRange(5, 300)
        self.browser_clipboard_seconds_spin.setSuffix(" 秒")
        self.browser_clipboard_seconds_spin.setValue(
            DEFAULT_BROWSER_CLIPBOARD_CLEAR_SECONDS
        )
        layout.addWidget(self.browser_clipboard_seconds_spin)
        self._update_browser_clipboard_controls(
            self.browser_clipboard_auto_clear_checkbox.isChecked()
        )

        layout.addStretch()
        return scroll

    def _build_personalization_page(self) -> QScrollArea:
        scroll, layout = self._new_page(PAGE_PERSONALIZATION)
        layout.addWidget(self._group_title("名称"))
        interface_label = QLabel("界面名称")
        interface_label.setObjectName("settingsFieldLabel")
        self._scrim_labels.append(interface_label)
        layout.addWidget(interface_label)
        self.interface_name_edit = QLineEdit()
        self.interface_name_edit.setMaxLength(MAX_INTERFACE_NAME_LENGTH)
        self.interface_name_edit.setPlaceholderText("超级奶蛙助手")
        layout.addWidget(self.interface_name_edit)
        interface_hint = QLabel(
            f"显示在标题栏，最多 {MAX_INTERFACE_NAME_LENGTH} 个字符；"
            "留空恢复默认。"
        )
        interface_hint.setObjectName("settingsHint")
        interface_hint.setWordWrap(True)
        layout.addWidget(interface_hint)
        software_label = QLabel("软件名称")
        software_label.setObjectName("settingsFieldLabel")
        self._scrim_labels.append(software_label)
        layout.addWidget(software_label)
        self.software_name_edit = QLineEdit()
        self.software_name_edit.setMaxLength(MAX_SOFTWARE_NAME_LENGTH)
        self.software_name_edit.setPlaceholderText("奶蛙的荣光")
        layout.addWidget(self.software_name_edit)
        software_hint = QLabel(
            f"用于托盘、任务栏活动窗口、关于和弹窗，最多 "
            f"{MAX_SOFTWARE_NAME_LENGTH} 个字符；留空恢复默认。"
        )
        software_hint.setObjectName("settingsHint")
        software_hint.setWordWrap(True)
        layout.addWidget(software_hint)

        layout.addWidget(self._group_title("背景"))
        self.background_status_label = QLabel("使用主题默认背景")
        self.background_status_label.setObjectName("settingsHint")
        self.background_status_label.setWordWrap(True)
        layout.addWidget(self.background_status_label)
        background_buttons = QHBoxLayout()
        self.background_select_button = QPushButton("选择背景图")
        self.background_select_button.setObjectName("sendButton")
        self.background_select_button.clicked.connect(
            self.background_select_requested.emit
        )
        self.background_reset_button = QToolButton()
        self.background_reset_button.setObjectName("secondaryButton")
        self.background_reset_button.setText("恢复默认背景")
        self.background_reset_button.clicked.connect(
            lambda: self.reset_personalization_requested.emit("background")
        )
        background_buttons.addWidget(self.background_select_button)
        background_buttons.addWidget(self.background_reset_button)
        layout.addLayout(background_buttons)

        mode_row = QFormLayout()
        mode_label = QLabel("显示方式")
        mode_label.setObjectName("settingsFieldLabel")
        self._scrim_labels.append(mode_label)
        self.background_mode_combo = QComboBox()
        self.background_mode_combo.addItem("填充（等比裁剪）", "cover")
        self.background_mode_combo.addItem("适应（完整显示）", "contain")
        self.background_mode_combo.addItem("居中（不缩放）", "center")
        mode_row.addRow(mode_label, self.background_mode_combo)
        layout.addLayout(mode_row)

        self.background_blur_slider = QSlider(Qt.Orientation.Horizontal)
        self.background_blur_slider.setRange(0, 20)
        self.background_blur_slider.setValue(DEFAULT_BACKGROUND_BLUR)
        self.background_blur_value = QLabel(
            f"{DEFAULT_BACKGROUND_BLUR} px"
        )
        blur_row = QWidget()
        blur_layout = QHBoxLayout(blur_row)
        blur_layout.setContentsMargins(0, 0, 0, 0)
        blur_layout.addWidget(self.background_blur_slider, 1)
        blur_layout.addWidget(self.background_blur_value)
        self.background_dim_slider = QSlider(Qt.Orientation.Horizontal)
        self.background_dim_slider.setRange(
            MIN_BACKGROUND_DIM,
            MAX_BACKGROUND_DIM,
        )
        self.background_dim_slider.setValue(DEFAULT_BACKGROUND_DIM)
        self.background_dim_value = QLabel(
            f"{DEFAULT_BACKGROUND_DIM}%"
        )
        dim_row = QWidget()
        dim_layout = QHBoxLayout(dim_row)
        dim_layout.setContentsMargins(0, 0, 0, 0)
        dim_layout.addWidget(self.background_dim_slider, 1)
        dim_layout.addWidget(self.background_dim_value)
        background_form = QFormLayout()
        background_form.addRow("模糊", blur_row)
        background_form.addRow("暗化", dim_row)
        layout.addLayout(background_form)
        self.background_dim_warning = QLabel(
            "背景较亮时文字可能不够清晰"
        )
        self.background_dim_warning.setObjectName("settingsWarning")
        self.background_dim_warning.setWordWrap(True)
        layout.addWidget(self.background_dim_warning)

        layout.addWidget(self._group_title("图标"))
        self.icon_status_labels: dict[str, QLabel] = {}
        self.icon_select_buttons: dict[str, QPushButton] = {}
        for key, label_text in (
            ("app", "应用图标"),
            ("title_logo", "标题栏圆形 logo"),
            ("ball", "悬浮球形象"),
        ):
            label = QLabel(label_text)
            label.setObjectName("settingsFieldLabel")
            self._scrim_labels.append(label)
            layout.addWidget(label)
            status = QLabel("使用默认图标")
            status.setObjectName("settingsHint")
            status.setWordWrap(True)
            self.icon_status_labels[key] = status
            row = QHBoxLayout()
            row.addWidget(status, 1)
            select_button = QPushButton("选择图片")
            select_button.setObjectName("secondaryButton")
            select_button.clicked.connect(
                lambda _checked=False, key=key: (
                    self.icon_select_requested.emit(key)
                )
            )
            reset_button = QToolButton()
            reset_button.setObjectName("secondaryButton")
            reset_button.setText("恢复默认")
            reset_button.clicked.connect(
                lambda _checked=False, key=key: (
                    self.reset_personalization_requested.emit(
                        f"icon:{key}"
                    )
                )
            )
            row.addWidget(select_button)
            row.addWidget(reset_button)
            self.icon_select_buttons[key] = select_button
            layout.addLayout(row)
        self.all_icons_button = QPushButton("全部使用同一张图")
        self.all_icons_button.setObjectName("sendButton")
        self.all_icons_button.clicked.connect(
            self.backgrounds_icons_same_requested.emit
        )
        layout.addWidget(self.all_icons_button)

        layout.addWidget(self._group_title("桌面快捷方式"))
        self.shortcut_hint_label = QLabel(
            "快捷方式直接调用 Windows IShellLink；不会通过 PowerShell、"
            "VBS 或 cmd 拼接命令。桌面可能由 Parallels 共享到 Mac。"
            "移动程序文件夹后需重新创建。"
        )
        self.shortcut_hint_label.setObjectName("settingsHint")
        self.shortcut_hint_label.setWordWrap(True)
        layout.addWidget(self.shortcut_hint_label)
        self.shortcut_status_label = QLabel()
        self.shortcut_status_label.setObjectName("settingsHint")
        self.shortcut_status_label.setWordWrap(True)
        layout.addWidget(self.shortcut_status_label)
        shortcut_buttons = QHBoxLayout()
        self.create_shortcut_button = QPushButton(
            "创建/更新桌面快捷方式"
        )
        self.create_shortcut_button.setObjectName("sendButton")
        self.create_shortcut_button.clicked.connect(
            self.create_shortcut_requested.emit
        )
        self.delete_shortcut_button = QToolButton()
        self.delete_shortcut_button.setObjectName("secondaryButton")
        self.delete_shortcut_button.setText("删除本软件快捷方式")
        self.delete_shortcut_button.clicked.connect(
            self.delete_shortcut_requested.emit
        )
        shortcut_buttons.addWidget(self.create_shortcut_button)
        shortcut_buttons.addWidget(self.delete_shortcut_button)
        layout.addLayout(shortcut_buttons)

        self.reset_all_personalization_button = QPushButton(
            "全部恢复默认"
        )
        self.reset_all_personalization_button.setObjectName(
            "secondaryButton"
        )
        self.reset_all_personalization_button.clicked.connect(
            lambda: self.reset_personalization_requested.emit("all")
        )
        layout.addWidget(self.reset_all_personalization_button)

        self.interface_name_edit.editingFinished.connect(
            self._emit_personalization_preview
        )
        self.software_name_edit.editingFinished.connect(
            self._emit_personalization_preview
        )
        self.background_mode_combo.currentIndexChanged.connect(
            self._emit_personalization_preview
        )
        self.background_blur_slider.valueChanged.connect(
            self._background_controls_changed
        )
        self.background_dim_slider.valueChanged.connect(
            self._background_controls_changed
        )
        layout.addStretch()
        return scroll

    def _new_page(self, index: int) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Ignored,
        )
        content = QWidget()
        content.setObjectName("settingsContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)
        scroll.setWidget(content)
        self.scroll_areas[index] = scroll
        return scroll, layout

    def _group_title(self, text: str) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(text)
        label.setObjectName("settingsGroupTitle")
        divider = QFrame()
        divider.setObjectName("settingsDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        layout.addWidget(label)
        layout.addWidget(divider)
        return container

    def set_values(self, config: AppConfig, api_key: str | None) -> None:
        self._loading_settings = True
        try:
            self._set_values(config, api_key)
        finally:
            self._loading_settings = False

    def _set_values(self, config: AppConfig, api_key: str | None) -> None:
        self.api_key_edit.setText(api_key or "")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.deselect()
        self.api_key_edit.setCursorPosition(len(api_key or ""))
        self.key_toggle_button.setText("显示")
        self.access_selection.set_selected(config.access_method)
        self._official_login_consent_version = (
            config.official_login_consent_version
        )
        self._official_login_terms_read_date = (
            config.official_login_terms_read_date
        )
        self._official_login_consent_at = config.official_login_consent_at
        self._official_consent_current = (
            self._official_login_consent_version
            == OFFICIAL_LOGIN_RISK_VERSION
            and self._official_login_terms_read_date
            == OFFICIAL_LOGIN_TERMS_READ_DATE
            and bool(self._official_login_consent_at)
        )
        self._browser_mode_consent_version = (
            config.browser_mode_consent_version
        )
        self._browser_mode_terms_read_date = (
            config.browser_mode_terms_read_date
        )
        self._browser_mode_consent_at = config.browser_mode_consent_at
        self._browser_consent_current = (
            self._browser_mode_consent_version
            == BROWSER_MODE_RISK_VERSION
            and self._browser_mode_terms_read_date
            == BROWSER_MODE_TERMS_READ_DATE
            and bool(self._browser_mode_consent_at)
        )
        self._browser_clipboard_auto_clear_enabled = (
            config.browser_clipboard_auto_clear_enabled
        )
        self._browser_clipboard_clear_seconds = (
            config.browser_clipboard_clear_seconds
        )
        self._browser_screen_capture_consent_version = (
            config.browser_screen_capture_consent_version
        )
        self._browser_voice_consent_version = (
            config.browser_voice_consent_version
        )
        self.work_mode_selection.set_selected(config.work_mode)
        self.base_url_edit.setText(config.base_url)
        self.model_edit.setText(config.model)
        self.timeout_spin.setValue(config.timeout_seconds)
        for definition in HOTKEY_DEFINITIONS:
            self.hotkey_editors[definition.key].set_value(
                config.hotkeys.get(definition.key, definition.default)
            )
        self.image_max_edge_spin.setValue(config.image_max_edge)
        opacity_percent = round(config.opacity * 100)
        self.opacity_slider.setValue(opacity_percent)
        self.opacity_value_label.setText(f"{opacity_percent}%")
        self.auto_send_checkbox.setChecked(config.auto_send_screenshot)
        self.no_focus_checkbox.setChecked(config.no_focus_mode)
        self.assistant_ball_persistent_checkbox.setChecked(
            config.assistant_ball_persistent
        )
        self.assistant_auto_hide_spin.setValue(
            config.assistant_auto_hide_seconds
        )
        with QSignalBlocker(self.assistant_ball_size_slider):
            self.assistant_ball_size_slider.setValue(
                config.assistant_ball_size
            )
        self.assistant_ball_size_value_label.setText(
            f"{config.assistant_ball_size} px"
        )
        self.screen_auto_send_checkbox.setChecked(
            config.screen_recognition_auto_send
        )
        self.screen_image_max_edge_spin.setValue(
            config.screen_recognition_image_max_edge
        )
        self.screen_prompt_edit.setPlainText(
            config.screen_recognition_prompt
        )
        self.set_screen_consent_state(
            config.screen_recognition_consent_version >= 1
        )
        with QSignalBlocker(self.voice_enabled_checkbox):
            self.voice_enabled_checkbox.setChecked(config.voice_enabled)
        self.voice_auto_listen_checkbox.setChecked(
            config.voice_auto_listen
        )
        self.voice_auto_send_checkbox.setChecked(config.voice_auto_send)
        self.voice_start_tone_checkbox.setChecked(
            config.voice_start_tone_enabled
        )
        self._set_combo_data(
            self.voice_language_combo,
            config.voice_language,
        )
        self._set_combo_data(
            self.microphone_combo,
            config.voice_microphone_device,
        )
        self.voice_silence_spin.setValue(config.voice_silence_seconds)
        self.voice_max_record_spin.setValue(
            config.voice_max_record_seconds
        )
        self.set_voice_consent_state(config.voice_consent_version >= 1)
        self.set_browser_screen_consent_state(
            config.browser_screen_capture_consent_version >= 1
        )
        self.set_browser_voice_consent_state(
            config.browser_voice_consent_version >= 1
        )
        self.browser_clipboard_auto_clear_checkbox.setChecked(
            config.browser_clipboard_auto_clear_enabled
        )
        self.browser_clipboard_seconds_spin.setValue(
            config.browser_clipboard_clear_seconds
        )
        self._update_browser_clipboard_controls(
            config.browser_clipboard_auto_clear_enabled
        )
        self._update_voice_controls(
            self.voice_enabled_checkbox.isChecked()
        )
        self.set_personalization_values(config.personalization)
        self._acrylic_desired_enabled = config.acrylic_enabled
        with QSignalBlocker(self.acrylic_checkbox):
            self.acrylic_checkbox.setChecked(config.acrylic_enabled)
        self.acrylic_checkbox.setEnabled(True)
        self.acrylic_status_label.clear()
        self.acrylic_status_label.hide()
        self.clear_status()
        for scroll in self.scroll_areas.values():
            scroll.verticalScrollBar().setValue(0)
        self.tabs.setCurrentIndex(PAGE_ACCESS)
        self._update_assistant_controls()
        self._update_official_controls()
        self._update_browser_controls()
        self._validate_hotkey_editors()

    def values(self) -> SettingsValues:
        return SettingsValues(
            api_key=self.api_key_edit.text().strip(),
            access_method=(
                self.access_selection.selected_key()
                or DEFAULT_ACCESS_METHOD
            ),
            work_mode=(
                self.work_mode_selection.selected_key()
                or DEFAULT_WORK_MODE
            ),
            base_url=self.base_url_edit.text().strip(),
            model=self.model_edit.text().strip(),
            timeout_seconds=self.timeout_spin.value(),
            hotkeys={
                key: editor.value()
                for key, editor in self.hotkey_editors.items()
            },
            image_max_edge=self.image_max_edge_spin.value(),
            auto_send_screenshot=self.auto_send_checkbox.isChecked(),
            no_focus_mode=self.no_focus_checkbox.isChecked(),
            opacity=self.opacity_slider.value() / 100,
            acrylic_enabled=self._acrylic_desired_enabled,
            assistant_ball_persistent=(
                self.assistant_ball_persistent_checkbox.isChecked()
            ),
            assistant_auto_hide_seconds=self.assistant_auto_hide_spin.value(),
            assistant_ball_size=self.assistant_ball_size_slider.value(),
            screen_recognition_auto_send=(
                self.screen_auto_send_checkbox.isChecked()
            ),
            screen_recognition_prompt=(
                self.screen_prompt_edit.toPlainText().strip()
            ),
            screen_recognition_image_max_edge=(
                self.screen_image_max_edge_spin.value()
            ),
            screen_recognition_consent_version=(
                1 if self._screen_consent_granted else 0
            ),
            voice_enabled=self.voice_enabled_checkbox.isChecked(),
            voice_auto_listen=self.voice_auto_listen_checkbox.isChecked(),
            voice_auto_send=self.voice_auto_send_checkbox.isChecked(),
            voice_language=str(
                self.voice_language_combo.currentData()
                or DEFAULT_VOICE_LANGUAGE
            ),
            voice_microphone_device=str(
                self.microphone_combo.currentData() or ""
            ),
            voice_silence_seconds=round(
                self.voice_silence_spin.value(),
                1,
            ),
            voice_max_record_seconds=(
                self.voice_max_record_spin.value()
            ),
            voice_start_tone_enabled=(
                self.voice_start_tone_checkbox.isChecked()
            ),
            voice_consent_version=(
                1 if self._voice_consent_granted else 0
            ),
            official_login_consent_version=(
                self._official_login_consent_version
            ),
            official_login_terms_read_date=(
                self._official_login_terms_read_date
            ),
            official_login_consent_at=self._official_login_consent_at,
            browser_mode_consent_version=(
                self._browser_mode_consent_version
            ),
            browser_mode_terms_read_date=(
                self._browser_mode_terms_read_date
            ),
            browser_mode_consent_at=self._browser_mode_consent_at,
            browser_clipboard_auto_clear_enabled=(
                self.browser_clipboard_auto_clear_checkbox.isChecked()
            ),
            browser_clipboard_clear_seconds=(
                self.browser_clipboard_seconds_spin.value()
            ),
            browser_screen_capture_consent_version=(
                self._browser_screen_capture_consent_version
            ),
            browser_voice_consent_version=(
                self._browser_voice_consent_version
            ),
            personalization=self.personalization_values(),
        )

    def set_personalization_values(
        self,
        personalization: PersonalizationConfig,
    ) -> None:
        self._loading_personalization = True
        try:
            self.interface_name_edit.setText(
                personalization.interface_name
            )
            self.software_name_edit.setText(
                personalization.software_name
            )
            self._set_combo_data(
                self.background_mode_combo,
                personalization.background_mode,
            )
            self.background_blur_slider.setValue(
                personalization.background_blur
            )
            self.background_dim_slider.setValue(
                personalization.background_dim
            )
            self._background_asset_id = (
                personalization.background_asset
            )
            self._app_icon_asset_id = (
                personalization.app_icon_asset
            )
            self._title_logo_asset_id = (
                personalization.title_logo_asset
            )
            self._ball_image_asset_id = (
                personalization.ball_image_asset
            )
            self._update_asset_statuses()
        finally:
            self._loading_personalization = False

    def personalization_values(self) -> PersonalizationConfig:
        return PersonalizationConfig(
            interface_name=self.interface_name_edit.text().strip(),
            software_name=self.software_name_edit.text().strip(),
            background_asset=self._background_asset_id,
            background_mode=str(
                self.background_mode_combo.currentData()
                or DEFAULT_BACKGROUND_MODE
            ),
            background_blur=self.background_blur_slider.value(),
            background_dim=self.background_dim_slider.value(),
            app_icon_asset=self._app_icon_asset_id,
            title_logo_asset=self._title_logo_asset_id,
            ball_image_asset=self._ball_image_asset_id,
        )

    def set_asset_selected(
        self,
        kind: str,
        asset_id: str,
    ) -> None:
        if kind == "background":
            self._background_asset_id = asset_id
        elif kind == "app":
            self._app_icon_asset_id = asset_id
        elif kind == "title_logo":
            self._title_logo_asset_id = asset_id
        elif kind == "ball":
            self._ball_image_asset_id = asset_id
        self._update_asset_statuses()
        self._emit_personalization_preview()

    def clear_asset(self, kind: str) -> None:
        if kind == "background":
            self._background_asset_id = ""
        elif kind == "app":
            self._app_icon_asset_id = ""
        elif kind == "title_logo":
            self._title_logo_asset_id = ""
        elif kind == "ball":
            self._ball_image_asset_id = ""
        self._update_asset_statuses()
        self._emit_personalization_preview()

    def set_shortcut_status(
        self,
        message: str,
        *,
        is_error: bool = False,
    ) -> None:
        self.shortcut_status_label.setText(message)
        self.shortcut_status_label.setProperty("error", is_error)
        self.shortcut_status_label.style().unpolish(
            self.shortcut_status_label
        )
        self.shortcut_status_label.style().polish(
            self.shortcut_status_label
        )

    def _update_asset_statuses(self) -> None:
        self.background_status_label.setText(
            "已选择自定义背景"
            if self._background_asset_id
            else "使用主题默认背景"
        )
        states = {
            "app": bool(self._app_icon_asset_id),
            "title_logo": bool(self._title_logo_asset_id),
            "ball": bool(self._ball_image_asset_id),
        }
        for key, selected in states.items():
            self.icon_status_labels[key].setText(
                "已选择自定义图片" if selected else "使用默认图标"
            )
        self._background_controls_changed()

    def _background_controls_changed(self, _value: int = 0) -> None:
        blur = self.background_blur_slider.value()
        dim = self.background_dim_slider.value()
        self.background_blur_value.setText(f"{blur} px")
        self.background_dim_value.setText(f"{dim}%")
        self.background_dim_warning.setVisible(dim < 35)
        self._emit_personalization_preview()

    def _emit_personalization_preview(self) -> None:
        if self._loading_personalization:
            return
        self.personalization_preview.emit(
            self.personalization_values()
        )

    def set_acrylic_availability(self, available: bool, reason: str) -> None:
        self.acrylic_checkbox.setEnabled(available)
        with QSignalBlocker(self.acrylic_checkbox):
            self.acrylic_checkbox.setChecked(
                self._acrylic_desired_enabled if available else False
            )
        if available:
            self.acrylic_status_label.clear()
            self.acrylic_status_label.hide()
        else:
            self.acrylic_status_label.setText(reason)
            self.acrylic_status_label.show()

    def set_readability_opacity(self, opacity: float) -> None:
        alpha = readability_scrim_alpha(opacity)
        style = (
            "background-color: transparent;"
            if alpha == 0
            else f"background-color: rgba(6, 9, 18, {alpha});"
        )
        for label in self._scrim_labels:
            label.setStyleSheet(style)

    def _remember_acrylic_preference(self, checked: bool) -> None:
        self._acrylic_desired_enabled = checked

    def _update_assistant_controls(self) -> None:
        enabled = (
            self.work_mode_selection.selected_key()
            == "global_assistant"
        )
        self.assistant_ball_persistent_checkbox.setEnabled(enabled)
        self.assistant_auto_hide_spin.setEnabled(enabled)
        self.assistant_ball_size_slider.setEnabled(enabled)
        self.assistant_ball_size_reset_button.setEnabled(enabled)

    def _access_selection_changed(self, key: str) -> None:
        if self._loading_settings:
            return
        self._update_official_controls()
        self.access_method_requested.emit(key)

    def set_official_web_state(
        self,
        *,
        installed: bool,
        message: str,
        consent_current: bool,
        consent_version: int | None = None,
        terms_read_date: str | None = None,
        consent_at: str | None = None,
    ) -> None:
        self._official_component_installed = bool(installed)
        self._official_consent_current = bool(consent_current)
        if consent_version is not None:
            self._official_login_consent_version = consent_version
        if terms_read_date is not None:
            self._official_login_terms_read_date = terms_read_date
        if consent_at is not None:
            self._official_login_consent_at = consent_at
        self.official_component_status_label.setText(message)
        self._update_official_controls()

    def select_access_method(self, key: str) -> None:
        self._loading_settings = True
        try:
            self.access_selection.set_selected(key)
        finally:
            self._loading_settings = False

    def set_official_consent(
        self,
        *,
        version: int,
        terms_read_date: str,
        consent_at: str,
    ) -> None:
        self._official_login_consent_version = version
        self._official_login_terms_read_date = terms_read_date
        self._official_login_consent_at = consent_at
        self._official_consent_current = (
            version == OFFICIAL_LOGIN_RISK_VERSION
            and terms_read_date == OFFICIAL_LOGIN_TERMS_READ_DATE
            and bool(consent_at)
        )
        self._update_official_controls()

    def clear_official_consent(self) -> None:
        self._official_login_consent_version = 0
        self._official_login_terms_read_date = ""
        self._official_login_consent_at = ""
        self._official_consent_current = False
        self._update_official_controls()

    def set_browser_mode_state(
        self,
        *,
        installed: bool,
        message: str,
        consent_current: bool,
        consent_version: int | None = None,
        terms_read_date: str | None = None,
        consent_at: str | None = None,
    ) -> None:
        self._official_component_installed = bool(installed)
        self._browser_consent_current = bool(consent_current)
        if consent_version is not None:
            self._browser_mode_consent_version = consent_version
        if terms_read_date is not None:
            self._browser_mode_terms_read_date = terms_read_date
        if consent_at is not None:
            self._browser_mode_consent_at = consent_at
        self.browser_status_label.setText(message)
        self._update_browser_controls()
        self._update_official_controls()

    def set_browser_consent(
        self,
        *,
        version: int,
        terms_read_date: str,
        consent_at: str,
    ) -> None:
        self._browser_mode_consent_version = version
        self._browser_mode_terms_read_date = terms_read_date
        self._browser_mode_consent_at = consent_at
        self._browser_consent_current = (
            version == BROWSER_MODE_RISK_VERSION
            and terms_read_date == BROWSER_MODE_TERMS_READ_DATE
            and bool(consent_at)
        )
        self._update_browser_controls()

    def clear_browser_consent(self) -> None:
        self._browser_mode_consent_version = 0
        self._browser_mode_terms_read_date = ""
        self._browser_mode_consent_at = ""
        self._browser_consent_current = False
        self._update_browser_controls()

    def set_browser_chromium_version(self, version: str) -> None:
        self._browser_chromium_version = version.strip()
        self.browser_chromium_label.setText(
            (
                f"内嵌 Chromium 版本：{self._browser_chromium_version}"
                if self._browser_chromium_version
                else "内嵌 Chromium 版本：启动浏览器后显示"
            )
        )

    def _update_official_controls(self) -> None:
        if hasattr(self, "access_selection"):
            self.access_selection.set_option_enabled(
                "official_login",
                self._official_component_installed,
                (
                    "实验性 · 非官方 · 有账号风险"
                    if self._official_component_installed
                    else "需先导入实验性组件"
                ),
                "请先导入由本机构建并通过校验的官网组件。",
            )
            self.access_selection.set_option_enabled(
                "official_browser",
                self._official_component_installed,
                (
                    "独立浏览器 · 不读取页面"
                    if self._official_component_installed
                    else "需先导入实验性组件"
                ),
                "请先导入由本机构建并通过校验的官网组件。",
            )
        enabled = self._official_component_installed and (
            self._official_consent_current
        )
        if hasattr(self, "official_login_button"):
            self.official_login_button.setEnabled(enabled)
            self.official_revoke_button.setEnabled(
                self._official_consent_current
            )

    def _update_browser_controls(self) -> None:
        if not hasattr(self, "browser_open_button"):
            return
        ready = (
            self._official_component_installed
            and self._browser_consent_current
        )
        self.browser_open_button.setEnabled(ready)
        self.browser_revoke_button.setEnabled(
            self._browser_consent_current
        )
        self.browser_open_button.setToolTip(
            ""
            if ready
            else (
                "请先选择该接入方式并完成浏览器模式风险确认。"
                if self._official_component_installed
                else "请先导入由本机构建并通过校验的官网组件。"
            )
        )

    def _update_browser_clipboard_controls(
        self,
        enabled: bool | None = None,
    ) -> None:
        checked = (
            self.browser_clipboard_auto_clear_checkbox.isChecked()
            if enabled is None
            else bool(enabled)
        )
        if hasattr(self, "browser_clipboard_seconds_spin"):
            self.browser_clipboard_seconds_spin.setEnabled(checked)

    def _ball_size_changed(self, value: int) -> None:
        self.assistant_ball_size_value_label.setText(f"{value} px")
        self.assistant_ball_size_preview.emit(value)

    def set_screen_consent_state(self, granted: bool) -> None:
        self._screen_consent_granted = bool(granted)
        self.screen_consent_label.setText(
            "已同意：可按快捷键截取当前屏幕并发送给 DeepSeek。"
            if granted
            else "尚未同意：快捷键不会截屏，只会显示隐私说明。"
        )
        self.screen_revoke_button.setEnabled(granted)
        if granted:
            self.screen_revoke_button.setText("撤销同意")
        else:
            self.screen_revoke_button.setText("已撤销")

    def _revoke_screen_consent(self) -> None:
        self.set_screen_consent_state(False)
        self.screen_consent_revoked.emit()

    def set_browser_screen_consent_state(self, granted: bool) -> None:
        self._browser_screen_capture_consent_version = 1 if granted else 0
        self.browser_screen_consent_label.setText(
            "已同意：浏览器模式截图只复制到剪贴板，不发送网络请求。"
            if granted
            else "尚未同意：浏览器模式不会截屏，只会显示独立隐私说明。"
        )
        self.browser_screen_revoke_button.setEnabled(bool(granted))
        self.browser_screen_revoke_button.setText(
            "撤销浏览器截图复制同意"
            if granted
            else "浏览器截图复制同意已撤销"
        )

    def set_browser_voice_consent_state(self, granted: bool) -> None:
        self._browser_voice_consent_version = 1 if granted else 0
        self.browser_voice_consent_label.setText(
            "已同意：本地转写文字只复制到剪贴板，不自动粘贴或发送。"
            if granted
            else "尚未同意：浏览器模式语音按钮不会启动麦克风。"
        )
        self.browser_voice_revoke_button.setEnabled(bool(granted))
        self.browser_voice_revoke_button.setText(
            "撤销浏览器语音复制同意"
            if granted
            else "浏览器语音复制同意已撤销"
        )

    def set_voice_consent_state(self, granted: bool) -> None:
        self._voice_consent_granted = bool(granted)
        self.voice_consent_label.setText(
            "已同意：可手动开始麦克风录音并在本机离线转写。"
            if granted
            else "尚未同意：语音按钮和自动聆听不会启动麦克风。"
        )
        self.voice_revoke_button.setEnabled(granted)
        self.voice_revoke_button.setText(
            "撤销麦克风同意" if granted else "麦克风同意已撤销"
        )

    def set_voice_model_status(
        self,
        installed: bool,
        message: str,
    ) -> None:
        self.voice_model_status_label.setText(
            ("已安装：" if installed else "未安装：") + message
        )

    def refresh_microphone_devices(
        self,
        devices,
        selected_name: str,
    ) -> None:
        self.microphone_combo.blockSignals(True)
        self.microphone_combo.clear()
        self.microphone_combo.addItem("系统默认输入", "")
        for device in devices:
            self.microphone_combo.addItem(device.label, device.name)
        self._set_combo_data(self.microphone_combo, selected_name)
        self.microphone_combo.blockSignals(False)

    def _revoke_voice_consent(self) -> None:
        self.set_voice_consent_state(False)
        self.voice_consent_revoked.emit()

    def _update_voice_controls(self, enabled: bool) -> None:
        for widget in (
            self.voice_auto_listen_checkbox,
            self.voice_auto_send_checkbox,
            self.voice_start_tone_checkbox,
            self.microphone_combo,
            self.voice_language_combo,
            self.voice_silence_spin,
            self.voice_max_record_spin,
        ):
            widget.setEnabled(bool(enabled))

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index < 0 and value:
            combo.addItem(f"{value}（当前不可用）", value)
            index = combo.count() - 1
        combo.setCurrentIndex(max(0, index))

    @property
    def hotkeys_valid(self) -> bool:
        return self._hotkeys_valid

    def _validate_hotkey_editors(self) -> None:
        parsed: dict[tuple[int, int], str] = {}
        duplicate_labels: dict[str, str] = {}
        valid = True
        for definition in HOTKEY_DEFINITIONS:
            editor = self.hotkey_editors[definition.key]
            editor.clear_error()
            try:
                spec = parse_hotkey(editor.value())
            except HotkeyConfigError as exc:
                editor.set_error(str(exc))
                valid = False
                continue
            signature = (spec.modifiers, spec.virtual_key)
            other_label = parsed.get(signature)
            if other_label is not None:
                editor.set_error(f"与{other_label}使用了相同组合键。")
                duplicate_labels[definition.key] = other_label
                valid = False
                continue
            parsed[signature] = definition.label

        for key, other_label in duplicate_labels.items():
            other_key = next(
                definition.key
                for definition in HOTKEY_DEFINITIONS
                if definition.label == other_label
            )
            self.hotkey_editors[other_key].set_error(
                f"与{HOTKEY_BY_KEY[key].label}使用了相同组合键。"
            )
        self._hotkeys_valid = valid
        self.save_button.setEnabled(valid)

    def _handle_hotkey_invalid(self, message: str) -> None:
        self._hotkeys_valid = False
        if hasattr(self, "save_button"):
            self.save_button.setEnabled(False)

    def focus_api_key(
        self,
        reason: Qt.FocusReason = Qt.FocusReason.OtherFocusReason,
    ) -> None:
        self.tabs.setCurrentIndex(PAGE_ACCESS)
        self.scroll_areas[PAGE_ACCESS].verticalScrollBar().setValue(0)
        self.api_key_edit.setFocus(reason)
        self.api_key_edit.deselect()
        self.api_key_edit.setCursorPosition(len(self.api_key_edit.text()))

    def set_status(self, message: str, is_error: bool = False) -> None:
        self.status_label.setProperty("error", is_error)
        self.status_label.setText(message)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.show()

    def clear_status(self) -> None:
        self.status_label.clear()
        self.status_label.hide()

    def _toggle_key_visibility(self) -> None:
        if self.api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.key_toggle_button.setText("隐藏")
        else:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.key_toggle_button.setText("显示")
