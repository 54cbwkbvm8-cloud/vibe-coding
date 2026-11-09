"""应用生命周期、设置持久化和各组件之间的信号连接。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, Slot
from PySide6.QtGui import QCursor, QGuiApplication, QImage
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMessageBox,
)

from .config import (
    AssistantBallPosition,
    AppConfig,
    ConfigError,
    MAX_INTERFACE_NAME_LENGTH,
    MAX_SOFTWARE_NAME_LENGTH,
    PersonalizationConfig,
    get_config_directory,
    get_config_path,
    load_config,
    sanitize_display_name,
    save_config,
    validate_base_url,
)
from .assistant_controller import (
    AssistantController,
    AssistantVisibilitySnapshot,
)
from .credentials import CredentialError, load_api_key, save_api_key
from .hotkeys import HotkeyRegistry, hotkey_values
from .logging_config import log_event
from .platform_support import IS_WINDOWS
from .personalization_runtime import (
    BrandRuntime,
    current_brand_runtime,
    runtime_from_config,
    runtime_from_personalization,
    set_brand_runtime,
)
from .services.chat_provider import ProviderUnavailableError
from .services.browser_clipboard import BrowserClipboardGuard, ClipboardError
from .services.official_web import (
    BROWSER_MODE_RISK_ITEMS,
    BROWSER_MODE_RISK_VERSION,
    BROWSER_MODE_TERMS_READ_DATE,
    OFFICIAL_LOGIN_COMPONENT_APP_VERSION,
    OFFICIAL_LOGIN_COMPONENT_VERSION,
    OFFICIAL_LOGIN_RISK_VERSION,
    OFFICIAL_LOGIN_SESSION_DIRECTORY,
    OFFICIAL_LOGIN_TERMS_READ_DATE,
    consent_is_current,
    consent_timestamp_now,
    browser_consent_is_current,
    browser_mode_ready,
    official_web_ready,
    startup_access_config,
)
from .services.official_web_component import (
    ComponentImportError,
    component_status,
    import_component,
    remove_session_directory,
)
from .services.official_web_process import OfficialWebProcessManager
from .services.provider_registry import create_chat_provider
from .hotkey_definitions import active_context_hotkey_keys
from .services.voice_audio import list_microphone_devices
from .services.voice_models import (
    model_files_present,
    validate_model_directory,
)
from .services.personalization_assets import (
    PersonalizationAssetDraft,
    PersonalizationImageError,
    clear_personalization_assets_after_commit,
    current_asset_ids,
    delete_old_assets_after_commit,
    load_local_image,
)
from .ui.about_dialog import show_about_dialog
from .ui.brand_assets import load_app_icon
from .ui.image_crop_dialog import ImageCropDialog
from .ui.main_window import MainWindow
from .ui.screen_recognition_preview import ScreenRecognitionPreview
from .ui.screenshot_overlay import ScreenshotOverlay
from .ui.tray_controller import TrayController
from .ui.voice_model_dialog import VoiceModelDialog
from .ui.official_web_dialog import OfficialWebRiskDialog
from .win32.hotkey import (
    GlobalHotkeyManager,
    HotkeyConfigError,
)
from .win32.window_style import activate_foreground, foreground_window
from .win32.shortcut import (
    ShortcutError,
    create_desktop_shortcut,
    delete_owned_desktop_shortcut,
    desktop_shortcut_path,
    inspect_shortcut,
    notify_shell_association_changed,
)
from .work_modes import WorkModeUnavailableError, create_work_mode
from .mode_coordinator import ModeCoordinator
from .voice_controller import VoiceController, VoiceSettings


@dataclass(frozen=True)
class ScreenRecognitionSnapshot:
    mode_key: str
    main_visible: bool
    assistant: AssistantVisibilitySnapshot | None
    browser_visible: bool = False
    previous_foreground: int = 0


@dataclass(frozen=True)
class BrowserCaptureSnapshot:
    main_visible: bool
    browser_visible: bool
    previous_foreground: int = 0


class ApplicationController(QObject):
    """持有窗口、托盘和快捷键管理器，保证它们不会被提前回收。"""

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self._app = app
        self._cleaned_up = False
        self._config_problem: str | None = None
        self._credential_problem: str | None = None
        self._screenshot_overlay: ScreenshotOverlay | None = None
        self._capture_screen = None
        self._screen_capture_screen = None
        self._screen_recognition_image: QImage | None = None
        self._screen_recognition_snapshot: ScreenRecognitionSnapshot | None = (
            None
        )
        self._settings_open = False
        self._exit_in_progress = False
        self._voice_model_dialog: VoiceModelDialog | None = None
        self._config_path = get_config_path()
        self._brand_revision = 0
        self._personalization_draft: PersonalizationAssetDraft | None = None
        self._personalization_preview_active = False
        self._clear_personalization_on_save = False
        self._startup_official_gate_pending = False
        self._startup_browser_pending = False
        self._startup_official_fallback_message = ""
        self._official_component_status_value = None
        self._browser_capture_snapshot: BrowserCaptureSnapshot | None = None
        self._browser_voice_active = False
        self._browser_chromium_version = ""

        try:
            self._config = load_config(self._config_path)
        except ConfigError as exc:
            log_event(
                "config_load_error",
                error_type=type(exc).__name__,
            )
            self._config = AppConfig()
            self._config_problem = str(exc)

        official_access_requested = self._config.access_method in {
            "official_login",
            "official_browser",
        }
        startup_component = (
            component_status(
                expected_app_version=OFFICIAL_LOGIN_COMPONENT_APP_VERSION,
                expected_component_version=OFFICIAL_LOGIN_COMPONENT_VERSION,
            )
            if official_access_requested
            else None
        )
        if official_access_requested:
            resolved_config, reason = startup_access_config(
                self._config,
                component_installed=startup_component.installed,
            )
            if resolved_config.access_method != self._config.access_method:
                self._config = resolved_config
                self._startup_official_fallback_message = reason
                self._official_component_status_value = startup_component
                try:
                    save_config(self._config, self._config_path)
                except OSError:
                    log_event(
                        "official_login_runtime_fallback_save_failed",
                        error_type="OSError",
                    )
        if self._config.access_method == "official_login":
            self._startup_official_gate_pending = True
        if self._config.access_method == "official_browser":
            self._startup_browser_pending = True

        self._brand_runtime = runtime_from_config(
            self._config,
            revision=self._brand_revision,
        )
        set_brand_runtime(self._brand_runtime)
        self._app.setApplicationDisplayName(
            self._brand_runtime.software_name
        )
        self._app.setWindowIcon(
            load_app_icon(str(self._brand_runtime.app_icon_path))
        )

        try:
            self._api_key = load_api_key()
        except CredentialError as exc:
            log_event(
                "credential_load_error",
                error_type=type(exc).__name__,
            )
            self._api_key = None
            self._credential_problem = str(exc)

        self.window = MainWindow()
        self.window.apply_brand(self._brand_runtime)
        self.window.restore_saved_geometry(self._config.window_geometry)
        self.window.load_api_settings(self._config, self._api_key)
        self.assistant = AssistantController(self)
        self.assistant.configure(self._config, self._api_key)
        self.assistant.apply_brand(self._brand_runtime)
        self.preview_voice = VoiceController(self)
        self.screen_recognition_preview = ScreenRecognitionPreview()
        self.screen_recognition_preview.apply_brand(self._brand_runtime)
        self.screen_recognition_preview.set_opacity(self._config.opacity)
        self.official_web_process = OfficialWebProcessManager(parent=self)
        self.browser_clipboard = BrowserClipboardGuard(
            auto_clear_enabled=(
                self._config.browser_clipboard_auto_clear_enabled
            ),
            clear_seconds=self._config.browser_clipboard_clear_seconds,
            parent=self,
        )
        self.assistant.settings_requested.connect(self.open_settings)
        self.assistant.exit_requested.connect(self.request_exit)
        self.assistant.auto_listen_requested.connect(
            self.start_assistant_voice
        )
        self.assistant.voice_input_requested.connect(
            self.start_assistant_voice
        )
        self.assistant.position_changed.connect(
            self._assistant_position_changed
        )
        self.mode_coordinator = ModeCoordinator(
            create_work_mode(
                self._config.work_mode,
                window=self.window,
                assistant=self.assistant,
            )
        )
        self.tray = TrayController(self)
        self.hotkeys = GlobalHotkeyManager(self)
        self.hotkey_registry = HotkeyRegistry(
            self.hotkeys,
            lambda: int(self.window.winId()),
        )

        self.hotkeys.activated.connect(self._handle_hotkey)
        self.tray.toggle_requested.connect(self.toggle_window)
        self.tray.show_requested.connect(self.show_window)
        self.tray.ball_visibility_requested.connect(
            self.assistant.toggle_ball_visibility
        )
        self.tray.about_requested.connect(self.show_about)
        self.tray.exit_requested.connect(self.request_exit)
        self.window.shutdown_complete.connect(self.finish_exit)
        self.window.settings_requested.connect(self.open_settings)
        self.window.settings_back_requested.connect(self.close_settings)
        self.window.screenshot_requested.connect(self.start_screenshot_capture)
        self.window.settings_save_requested.connect(self.save_settings)
        self.window.hotkey_recording_started.connect(
            self._suspend_hotkeys_for_recording
        )
        self.window.hotkey_recording_finished.connect(
            self._resume_hotkeys_after_recording
        )
        self.window.assistant_ball_size_preview.connect(
            self._preview_assistant_ball_size
        )
        self.window.screen_consent_revoked.connect(
            self.revoke_screen_recognition_consent
        )
        self.window.voice_consent_revoked.connect(
            self.revoke_voice_consent
        )
        self.window.voice_model_download_requested.connect(
            self.open_voice_model_dialog
        )
        self.window.voice_model_import_requested.connect(
            self.import_voice_model_folder
        )
        self.window.personalization_preview.connect(
            self._preview_personalization
        )
        self.window.background_select_requested.connect(
            self.select_background_image
        )
        self.window.icon_select_requested.connect(
            self.select_icon_image
        )
        self.window.backgrounds_icons_same_requested.connect(
            self.select_all_icon_images
        )
        self.window.reset_personalization_requested.connect(
            self.reset_personalization
        )
        self.window.create_shortcut_requested.connect(
            self.create_personalized_shortcut
        )
        self.window.delete_shortcut_requested.connect(
            self.delete_personalized_shortcut
        )
        self.window.access_method_requested.connect(
            self._official_access_method_requested
        )
        self.window.official_component_import_zip_requested.connect(
            self.import_official_component_zip
        )
        self.window.official_component_import_folder_requested.connect(
            self.import_official_component_folder
        )
        self.window.official_login_requested.connect(
            self.open_official_login_panel
        )
        self.window.official_risk_requested.connect(
            self.show_official_risk_reader
        )
        self.window.official_consent_revoked.connect(
            self.revoke_official_consent
        )
        self.window.browser_mode_requested.connect(
            self.activate_browser_mode
        )
        self.window.browser_risk_requested.connect(
            self.show_browser_risk_reader
        )
        self.window.browser_consent_revoked.connect(
            self.revoke_browser_consent
        )
        self.window.browser_screen_consent_revoked.connect(
            self.revoke_browser_screen_consent
        )
        self.window.browser_voice_consent_revoked.connect(
            self.revoke_browser_voice_consent
        )
        self.official_web_process.state_changed.connect(
            self._official_process_state
        )
        self.official_web_process.login_state_changed.connect(
            self._official_login_state
        )
        self.official_web_process.failed.connect(
            self._official_process_failed
        )
        self.official_web_process.browser_event.connect(
            self._browser_process_event
        )
        self.official_web_process.chromium_version_changed.connect(
            self._browser_chromium_version_changed
        )
        self.window.session_locked.connect(self._session_locked)
        self.screen_recognition_preview.send_requested.connect(
            self._send_screen_recognition_preview
        )
        self.screen_recognition_preview.cancelled.connect(
            self._cancel_screen_recognition_preview
        )
        self.screen_recognition_preview.microphone_requested.connect(
            self.start_preview_voice
        )
        self.screen_recognition_preview.voice_cancel_requested.connect(
            self.cancel_preview_voice
        )
        self.preview_voice.listening_started.connect(
            self._preview_voice_started
        )
        self.preview_voice.listening_finished.connect(
            self._preview_voice_finished
        )
        self.preview_voice.listening_cancelled.connect(
            self._preview_voice_cancelled
        )
        self.preview_voice.listening_failed.connect(
            self._preview_voice_failed
        )
        self.preview_voice.level_changed.connect(
            self.screen_recognition_preview.set_voice_level
        )
        self._app.applicationStateChanged.connect(
            self.window.handle_application_state
        )
        self._app.aboutToQuit.connect(self.cleanup)

    def start(self) -> None:
        """显示窗口和托盘，并在窗口句柄可用后注册快捷键。"""
        self.tray.show()
        if self._is_browser_mode():
            self.window.hide_overlay()
            log_event("official_browser_startup_configured")
        else:
            self.mode_coordinator.activate()
        self._update_tray_mode_actions()
        QTimer.singleShot(100, self._initialize_hotkey)
        QTimer.singleShot(150, self._startup_official_gate)
        QTimer.singleShot(170, self._startup_browser_mode)
        if self._startup_official_fallback_message:
            QTimer.singleShot(
                160,
                lambda: self.window.show_notice(
                    self._startup_official_fallback_message
                ),
            )

    @Slot()
    def toggle_window(self) -> None:
        if self._is_browser_mode():
            self.toggle_browser_window()
        elif self.mode_coordinator.current.definition.key == "global_assistant":
            self.assistant.toggle_input()
        elif self.window.isVisible():
            self.window.hide_overlay()
        else:
            self.window.show_overlay()

    @Slot(str)
    def _handle_hotkey(self, action: str) -> None:
        if action == "assistant":
            self.assistant.toggle_input()
        elif action == "ball_visibility":
            self.assistant.toggle_ball_visibility()
        elif action == "chat":
            self.toggle_window()
        elif action == "screenshot":
            self.start_screenshot_capture()
        elif action == "screen_recognition":
            self.start_screen_recognition()

    @Slot()
    def show_window(self) -> None:
        if self._is_browser_mode():
            self.show_browser_window()
        elif self.mode_coordinator.current.definition.key == "global_assistant":
            self.assistant.show_input()
        else:
            self.window.show_overlay()

    @Slot()
    def show_about(self) -> None:
        show_about_dialog(self.window)

    def _query_official_component_status(self):
        return component_status(
            expected_app_version=OFFICIAL_LOGIN_COMPONENT_APP_VERSION,
            expected_component_version=OFFICIAL_LOGIN_COMPONENT_VERSION,
        )

    def _refresh_official_component_status(
        self,
        *,
        force: bool = False,
    ) -> None:
        status = (
            self._official_component_status_value
            if self._official_component_status_value is not None
            and not force
            else self._query_official_component_status()
        )
        self._official_component_status_value = status
        current = consent_is_current(self._config)
        browser_current = browser_consent_is_current(self._config)
        self.window.settings_panel.set_official_web_state(
            installed=status.installed,
            message=status.message,
            consent_current=current,
            consent_version=self._config.official_login_consent_version,
            terms_read_date=self._config.official_login_terms_read_date,
            consent_at=self._config.official_login_consent_at,
        )
        self.window.settings_panel.set_browser_mode_state(
            installed=status.installed,
            message=(
                f"{status.message} 浏览器模式只显示官网页面，不读取页面内容。"
            ),
            consent_current=browser_current,
            consent_version=self._config.browser_mode_consent_version,
            terms_read_date=self._config.browser_mode_terms_read_date,
            consent_at=self._config.browser_mode_consent_at,
        )
        self.window.settings_panel.set_browser_chromium_version(
            self._browser_chromium_version
        )
        if (
            self._config.access_method == "official_login"
            and status.installed
        ):
            self.window.settings_panel.select_access_method(
                "official_login"
            )
        if (
            self._config.access_method == "official_browser"
            and status.installed
        ):
            self.window.settings_panel.select_access_method(
                "official_browser"
            )
        self.window.set_official_mode_badge(
            (
                self._config.access_method == "official_login"
                and current
            )
            or (
                self._config.access_method == "official_browser"
                and browser_current
            )
        )

    def _startup_official_gate(self) -> None:
        if not self._startup_official_gate_pending:
            return
        self._startup_official_gate_pending = False
        if not self._show_official_consent_gate():
            self._fallback_official_to_api(
                "已取消官网账号接入，已回退到 API 接入。"
            )
            return
        if not self._record_official_consent():
            self._fallback_official_to_api(
                "无法保存官网账号接入同意，已回退到 API 接入。"
            )
            return
        self._refresh_official_component_status()
        if (
            self._official_component_status_value.installed
            and self._config.access_method == "official_login"
        ):
            QTimer.singleShot(0, self.open_official_login_panel)

    def _show_official_consent_gate(self) -> bool:
        dialog = OfficialWebRiskDialog(self.window)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _show_browser_consent_gate(self) -> bool:
        dialog = OfficialWebRiskDialog(
            self.window,
            risk_items=BROWSER_MODE_RISK_ITEMS,
            require_countdown=False,
            require_confirmation=False,
            title="启用 DeepSeek 官网（浏览器模式）前请阅读",
            terms_read_date=BROWSER_MODE_TERMS_READ_DATE,
        )
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _record_official_consent(self) -> bool:
        updated = replace(
            self._config,
            official_login_consent_version=OFFICIAL_LOGIN_RISK_VERSION,
            official_login_terms_read_date=OFFICIAL_LOGIN_TERMS_READ_DATE,
            official_login_consent_at=consent_timestamp_now(),
        )
        try:
            save_config(updated, self._config_path)
        except OSError as exc:
            self.window.set_settings_status(
                f"保存官网账号接入同意失败：{exc}",
                is_error=True,
            )
            return False
        self._config = updated
        self.window.settings_panel.set_official_consent(
            version=updated.official_login_consent_version,
            terms_read_date=updated.official_login_terms_read_date,
            consent_at=updated.official_login_consent_at,
        )
        self.window.set_official_mode_badge(
            updated.access_method == "official_login"
        )
        log_event("official_login_consent_granted")
        return True

    def _record_browser_consent(self) -> bool:
        updated = replace(
            self._config,
            browser_mode_consent_version=BROWSER_MODE_RISK_VERSION,
            browser_mode_terms_read_date=BROWSER_MODE_TERMS_READ_DATE,
            browser_mode_consent_at=consent_timestamp_now(),
        )
        try:
            save_config(updated, self._config_path)
        except OSError as exc:
            self.window.set_settings_status(
                f"保存浏览器模式同意失败：{exc}",
                is_error=True,
            )
            return False
        self._config = updated
        self.window.settings_panel.set_browser_consent(
            version=updated.browser_mode_consent_version,
            terms_read_date=updated.browser_mode_terms_read_date,
            consent_at=updated.browser_mode_consent_at,
        )
        self.window.set_official_mode_badge(
            updated.access_method == "official_browser"
        )
        log_event("official_browser_consent_granted")
        return True

    def _startup_browser_mode(self) -> None:
        if not self._startup_browser_pending:
            log_event("official_browser_startup_not_pending")
            return
        self._startup_browser_pending = False
        log_event("official_browser_startup_begin")
        if not self._is_browser_mode():
            log_event("official_browser_startup_access_changed")
            return
        self._refresh_official_component_status(force=True)
        status = self._official_component_status_value
        ready, message = browser_mode_ready(
            self._config,
            status.installed if status is not None else False,
            status.message if status is not None else "",
        )
        if not ready:
            log_event(
                "official_browser_startup_not_ready",
                status_code=1,
            )
            self._fallback_browser_to_api(message)
            return
        if not self._start_browser_process():
            log_event(
                "official_browser_startup_process_failed",
                status_code=2,
            )
            self._fallback_browser_to_api(
                "浏览器组件启动失败，已回退到 API 接入。"
            )

    def _is_browser_mode(self) -> bool:
        return self._config.access_method == "official_browser"

    def _start_browser_process(self) -> bool:
        log_event("official_browser_process_start_requested")
        self._refresh_official_component_status()
        status = self._official_component_status_value
        ready, message = browser_mode_ready(
            self._config,
            status.installed if status is not None else False,
            status.message if status is not None else "",
        )
        if not ready or status is None:
            log_event(
                "official_browser_process_not_ready",
                status_code=1,
            )
            self.window.set_settings_status(message, is_error=True)
            return False
        session_dir = (
            get_config_directory() / OFFICIAL_LOGIN_SESSION_DIRECTORY
        )
        started = self.official_web_process.start(
            status,
            session_dir=session_dir,
            browser_mode=True,
            interface_name=self._brand_runtime.interface_name,
            logo_path=(
                str(self._brand_runtime.title_logo_path)
                if self._brand_runtime.title_logo_path is not None
                else ""
            ),
            opacity=self._config.opacity,
        )
        if not started:
            log_event(
                "official_browser_process_start_failed",
                status_code=2,
            )
            self.window.set_settings_status(
                "无法创建官网浏览器辅助进程。",
                is_error=True,
            )
        return started

    @Slot()
    def activate_browser_mode(self) -> None:
        if not self._is_browser_mode():
            self.window.settings_panel.select_access_method(
                "official_browser"
            )
            self._official_access_method_requested("official_browser")
            return
        if not browser_consent_is_current(self._config):
            if not self._show_browser_consent_gate():
                self.window.set_settings_status(
                    "已取消，接入方式保持不变。"
                )
                return
            if not self._record_browser_consent():
                return
        if self._is_browser_mode() and not self._start_browser_process():
            self._fallback_browser_to_api(
                "浏览器模式启动失败，已回退到 API 接入。"
            )
            return
        self._browser_process_ready()

    def show_browser_window(self) -> None:
        if not self._is_browser_mode():
            return
        if not self.official_web_process.is_running:
            if not self._start_browser_process():
                self._fallback_browser_to_api(
                    "浏览器组件启动失败，已回退到 API 接入。"
                )
                return
        self.window.hide_overlay()
        self.official_web_process.show()

    def toggle_browser_window(self) -> None:
        if not self._is_browser_mode():
            return
        if not self.official_web_process.is_running:
            if not self._start_browser_process():
                self._fallback_browser_to_api(
                    "浏览器组件启动失败，已回退到 API 接入。"
                )
                return
            self._browser_process_ready()
            return
        self.official_web_process.toggle()

    def _browser_process_ready(self) -> None:
        self.window.hide_overlay()
        self.assistant.input_bar.hide()
        self.assistant.bubble.hide()
        self.assistant.ball.hide()
        self.official_web_process.show()

    def _fallback_browser_to_api(self, message: str) -> None:
        self.official_web_process.stop()
        previous = self._config
        updated = replace(
            previous,
            access_method="api",
            browser_mode_consent_version=0,
            browser_mode_terms_read_date="",
            browser_mode_consent_at="",
        )
        prepared = None
        try:
            prepared = self.hotkey_registry.prepare(
                hotkey_values(updated),
                active_context_hotkey_keys(
                    updated.access_method,
                    updated.work_mode,
                ),
            )
            save_config(updated, self._config_path)
        except (HotkeyConfigError, OSError, RuntimeError) as exc:
            if prepared is not None:
                prepared.rollback()
            self.window.set_settings_status(
                f"{message} 保存回退失败：{exc}",
                is_error=True,
            )
            return
        assert prepared is not None
        prepared.commit()
        self._config = updated
        self.window.settings_panel.select_access_method("api")
        self.window.settings_panel.clear_browser_consent()
        self.window.set_official_mode_badge(False)
        self.window.set_settings_status(message)
        log_event("official_browser_fallback_api")

    def _fallback_official_to_api(self, message: str) -> None:
        self.official_web_process.stop()
        updated = replace(
            self._config,
            access_method="api",
            official_login_consent_version=0,
            official_login_terms_read_date="",
            official_login_consent_at="",
        )
        try:
            save_config(updated, self._config_path)
        except OSError as exc:
            self.window.set_settings_status(
                f"{message} 保存回退失败：{exc}",
                is_error=True,
            )
            return
        self._config = updated
        self.window.settings_panel.select_access_method("api")
        self.window.settings_panel.clear_official_consent()
        self.window.set_official_mode_badge(False)
        self.window.set_settings_status(message)
        log_event("official_login_fallback_api")

    @Slot(str)
    def _official_access_method_requested(self, key: str) -> None:
        previous = self._config.access_method
        if key == previous:
            if key == "official_browser":
                self.activate_browser_mode()
            return
        if (
            previous == "official_browser"
            and self.official_web_process.is_running
            and not self._confirm_browser_close_for_switch()
        ):
            self.window.settings_panel.select_access_method(previous)
            self.window.set_settings_status(
                "已取消切换，官网浏览器窗口和接入方式保持不变。"
            )
            return
        if self._current_mode_busy():
            if not self._confirm_stop_for_context_switch():
                self.window.settings_panel.select_access_method(previous)
                self.window.set_settings_status(
                    "已取消切换，当前回答和接入方式保持不变。"
                )
                return
            self._stop_current_mode_then(
                lambda: self._official_access_method_requested(key)
            )
            self.window.set_settings_status(
                "正在停止当前回答，随后切换接入方式。"
            )
            return
        if key == "api":
            updated = replace(self._config, access_method="api")
            prepared = None
            try:
                prepared = self.hotkey_registry.prepare(
                    hotkey_values(updated),
                    active_context_hotkey_keys(
                        updated.access_method,
                        updated.work_mode,
                    ),
                )
                save_config(updated, self._config_path)
            except (HotkeyConfigError, OSError, RuntimeError) as exc:
                if prepared is not None:
                    prepared.rollback()
                self.window.settings_panel.select_access_method(previous)
                self.window.set_settings_status(
                    f"切换回 API 接入失败：{exc}",
                    is_error=True,
                )
                return
            assert prepared is not None
            prepared.commit()
            self.official_web_process.stop()
            self._config = updated
            self.window.set_official_mode_badge(False)
            self.window.show_overlay()
            self.window.set_settings_status("已切换回 API 接入。")
            return
        if key not in {"official_login", "official_browser"}:
            return
        status = self._query_official_component_status()
        self._official_component_status_value = status
        if not status.installed:
            self.window.settings_panel.select_access_method(previous)
            self.window.set_settings_status(
                status.message,
                is_error=True,
            )
            return
        if key == "official_browser":
            if not self._show_browser_consent_gate():
                self.window.settings_panel.select_access_method(previous)
                self.window.set_settings_status(
                    "已取消切换，接入方式保持不变。"
                )
                return
            if not self._record_browser_consent():
                self.window.settings_panel.select_access_method(previous)
                return
            updated = replace(
                self._config,
                access_method="official_browser",
            )
            prepared = None
            try:
                prepared = self.hotkey_registry.prepare(
                    hotkey_values(updated),
                    active_context_hotkey_keys(
                        updated.access_method,
                        updated.work_mode,
                    ),
                )
                save_config(updated, self._config_path)
            except (HotkeyConfigError, OSError, RuntimeError) as exc:
                if prepared is not None:
                    prepared.rollback()
                self.window.settings_panel.select_access_method(previous)
                self.window.set_settings_status(
                    f"切换浏览器模式失败：{exc}",
                    is_error=True,
                )
                return
            assert prepared is not None
            self.official_web_process.stop()
            prepared.commit()
            self._config = updated
            self.window.settings_panel.set_browser_consent(
                version=updated.browser_mode_consent_version,
                terms_read_date=updated.browser_mode_terms_read_date,
                consent_at=updated.browser_mode_consent_at,
            )
            self._refresh_official_component_status()
            if not self._start_browser_process():
                self._fallback_browser_to_api(
                    "浏览器组件启动失败，已回退到 API 接入。"
                )
                return
            self.window.set_settings_status(
                "浏览器模式已启用。官网页面中的对话仍由你手动操作。"
            )
            log_event("official_browser_mode_enabled")
            return
        if not self._show_official_consent_gate():
            self.window.settings_panel.select_access_method(previous)
            self.window.set_settings_status("已取消切换，接入方式保持不变。")
            return
        if not self._record_official_consent():
            self.window.settings_panel.select_access_method(previous)
            return
        updated = replace(self._config, access_method="official_login")
        try:
            save_config(updated, self._config_path)
        except OSError as exc:
            self.window.settings_panel.select_access_method(previous)
            self.window.set_settings_status(
                f"保存官网账号接入方式失败：{exc}",
                is_error=True,
            )
            return
        self._config = updated
        self.official_web_process.stop()
        self._refresh_official_component_status()
        self.window.set_settings_status(
            "已启用官网账号接入（实验性）。请导入组件后再打开登录面板。"
        )

    @Slot()
    def open_official_login_panel(self) -> None:
        if not consent_is_current(self._config):
            if not self._show_official_consent_gate():
                return
            if not self._record_official_consent():
                return
        self._refresh_official_component_status()
        status = self._official_component_status_value
        ready, message = official_web_ready(
            self._config,
            status.installed,
            status.message,
        )
        if not ready:
            self.window.set_settings_status(
                message,
                is_error=True,
            )
            return
        session_dir = get_config_directory() / OFFICIAL_LOGIN_SESSION_DIRECTORY
        self.official_web_process.start(status, session_dir=session_dir)

    @Slot()
    def show_official_risk_reader(self) -> None:
        dialog = OfficialWebRiskDialog(self.window, reading_only=True)
        dialog.exec()

    @Slot()
    def show_browser_risk_reader(self) -> None:
        dialog = OfficialWebRiskDialog(
            self.window,
            reading_only=True,
            risk_items=BROWSER_MODE_RISK_ITEMS,
            require_countdown=False,
            require_confirmation=False,
            title="DeepSeek 官网（浏览器模式）风险说明",
            terms_read_date=BROWSER_MODE_TERMS_READ_DATE,
        )
        dialog.exec()

    @Slot()
    def revoke_browser_consent(self) -> None:
        self._cancel_pending_screen_recognition(silent=True)
        self._cancel_all_voice()
        session_dir = (
            get_config_directory() / OFFICIAL_LOGIN_SESSION_DIRECTORY
        )
        try:
            remove_session_directory(session_dir)
        except OSError as exc:
            self.window.set_settings_status(
                f"清除官网登录数据失败：{exc}",
                is_error=True,
            )
            return
        self._fallback_browser_to_api(
            "已撤销浏览器模式同意，登录数据已清除，API 配置未改变。"
        )

    @Slot()
    def revoke_browser_screen_consent(self) -> None:
        self._cancel_pending_screen_recognition(silent=True)
        updated = replace(
            self._config,
            browser_screen_capture_consent_version=0,
        )
        try:
            save_config(updated, self._config_path)
        except OSError as exc:
            self.window.set_settings_status(
                f"撤销浏览器截图复制同意失败：{exc}",
                is_error=True,
            )
            return
        self._config = updated
        self.window.settings_panel.set_browser_screen_consent_state(False)
        log_event("official_browser_screen_consent_revoked")

    @Slot()
    def revoke_browser_voice_consent(self) -> None:
        self._cancel_all_voice()
        updated = replace(
            self._config,
            browser_voice_consent_version=0,
        )
        try:
            save_config(updated, self._config_path)
        except OSError as exc:
            self.window.set_settings_status(
                f"撤销浏览器语音复制同意失败：{exc}",
                is_error=True,
            )
            return
        self._config = updated
        self.window.settings_panel.set_browser_voice_consent_state(False)
        log_event("official_browser_voice_consent_revoked")

    @Slot()
    def import_official_component_zip(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.window,
            "选择实验性官网组件 ZIP",
            "",
            "组件压缩包 (*.zip)",
        )
        if path:
            self._import_official_component(Path(path))

    @Slot()
    def import_official_component_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self.window,
            "选择实验性官网组件文件夹",
        )
        if path:
            self._import_official_component(Path(path))

    def _import_official_component(self, source: Path) -> None:
        try:
            imported = import_component(
                source,
                expected_app_version=OFFICIAL_LOGIN_COMPONENT_APP_VERSION,
                expected_component_version=OFFICIAL_LOGIN_COMPONENT_VERSION,
            )
        except ComponentImportError as exc:
            self.window.set_settings_status(
                f"导入组件失败：{exc}",
                is_error=True,
            )
            log_event(
                "official_component_import_failed",
                error_type=type(exc).__name__,
            )
            return
        self._refresh_official_component_status(force=True)
        self.window.set_settings_status(
            f"组件 {imported.version} 已导入并通过自检。"
        )
        log_event("official_component_imported")

    @Slot()
    def revoke_official_consent(self) -> None:
        self.official_web_process.stop()
        session_dir = get_config_directory() / OFFICIAL_LOGIN_SESSION_DIRECTORY
        try:
            remove_session_directory(session_dir)
        except OSError as exc:
            self.window.set_settings_status(
                f"清除官网登录数据失败：{exc}",
                is_error=True,
            )
            return
        self._fallback_official_to_api(
            "已撤销官网账号接入同意，登录数据已清除，API 配置未改变。"
        )

    @Slot(str, str)
    def _official_process_state(self, state: str, message: str) -> None:
        if state == "stopped":
            self.window.set_official_login_state("unknown")
        if message:
            self.window.set_settings_status(message)

    @Slot(str)
    def _official_login_state(self, state: str) -> None:
        self.window.set_official_login_state(state)
        labels = {
            "logged_in": "官网账号已登录。",
            "logged_out": "官网账号尚未登录，请使用登录面板扫码或登录。",
            "expired": "官网登录状态已过期，请重新登录。",
            "unknown": "正在检测官网登录状态…",
        }
        if state in labels:
            self.window.set_settings_status(labels[state])

    @Slot(str)
    def _official_process_failed(self, message: str) -> None:
        self.window.set_settings_status(message, is_error=True)

    @Slot(str)
    def _browser_process_event(self, event: str) -> None:
        if event == "browser_ready":
            self._browser_process_ready()
        elif event == "return_to_main":
            self.official_web_process.hide()
            self.open_settings()
        elif event == "hidden_to_tray":
            self.official_web_process.hide()
            self.window.set_settings_status(
                "官网浏览器已隐藏；可用问答唤出键或托盘重新打开。"
            )
        elif event == "risk_requested":
            self.show_browser_risk_reader()
        elif event == "voice_requested":
            self.start_browser_voice()
        elif event == "external_navigation":
            message = "白名单外链接已交给系统默认浏览器。"
            self.window.set_settings_status(message)
            self.official_web_process.set_message(message)
        elif event == "download_rejected":
            message = "浏览器模式不允许下载，请在系统浏览器里下载。"
            self.window.set_settings_status(message, is_error=True)
            self.official_web_process.set_message(message)
        elif event == "permission_denied":
            log_event("official_browser_permission_denied")

    @Slot(str)
    def _browser_chromium_version_changed(self, version: str) -> None:
        self._browser_chromium_version = version
        self.window.settings_panel.set_browser_chromium_version(version)

    @Slot()
    def request_exit(self) -> None:
        """先停止工作线程，再结束 Qt 应用。"""
        if self._exit_in_progress:
            return
        self._exit_in_progress = True
        if self._voice_is_active():
            self._cancel_all_voice()
        if (
            self.mode_coordinator.current.definition.key
            == "global_assistant"
            and self.assistant.is_busy
        ):
            self.assistant.stop_request_then(self.window.prepare_exit)
            return
        self.window.prepare_exit()

    @Slot()
    def finish_exit(self) -> None:
        self.cleanup()
        self.window.deleteLater()
        self.tray.deleteLater()
        self.hotkeys.deleteLater()
        QTimer.singleShot(0, self._app.quit)

    @Slot()
    def cleanup(self) -> None:
        if self._cleaned_up:
            return
        self._cleaned_up = True
        log_event("app_cleanup_started")
        self._discard_personalization_draft()
        self._save_window_geometry()
        self.hotkey_registry.unregister_all()
        self.hotkeys.unregister()
        self.official_web_process.stop()
        self.preview_voice.shutdown()
        self.assistant.shutdown()
        self.screen_recognition_preview.clear_image()
        self.screen_recognition_preview.close()
        self._screen_capture_screen = None
        self._screen_recognition_image = None
        self._screen_recognition_snapshot = None
        if self._voice_model_dialog is not None:
            self._voice_model_dialog.close()
            self._voice_model_dialog.deleteLater()
            self._voice_model_dialog = None
        if self._screenshot_overlay is not None:
            overlay = self._screenshot_overlay
            self._screenshot_overlay = None
            overlay.cancelled.disconnect(self._on_screenshot_cancelled)
            overlay.close()
        self.tray.hide()
        log_event("app_cleanup_finished")

    @Slot()
    def _initialize_hotkey(self) -> None:
        problems: list[str] = []

        if self._config_problem:
            problems.append(self._config_problem)

        if self._credential_problem:
            problems.append(self._credential_problem)

        if not self.tray.is_available:
            log_event("system_tray_unavailable")
            problems.append("当前系统没有可用的系统托盘区域。")

        if not IS_WINDOWS:
            self.window.show_status("Mac 环境不注册 Win32 快捷键")
            return

        try:
            self.hotkey_registry.register_initial(
                hotkey_values(self._config),
                active_context_hotkey_keys(
                    self._config.access_method,
                    self._config.work_mode,
                ),
            )
        except (
            HotkeyConfigError,
            RuntimeError,
            WorkModeUnavailableError,
        ) as exc:
            log_event(
                "hotkey_registration_error",
                error_type=type(exc).__name__,
            )
            problems.append(str(exc))
            self.window.show_status("快捷键注册失败")
        else:
            self.window.set_hotkey_hint(
                self._config.hotkey,
                self._config.screenshot_hotkey,
            )
            self.window.show_status("快捷键已就绪")

        if problems:
            problems.append(f"配置文件：{self._config_path}")
            message = "\n\n".join(problems)
            self.window.show_overlay()
            self.window.show_notice(message)
        elif self._is_browser_mode():
            self.window.show_status("官网浏览器模式已就绪")
        elif not self._api_key:
            self.window.show_notice("尚未配置 API Key，请在设置中填写并保存。")
            self.window.show_status("等待 API Key")
        else:
            self.window.show_status(
                f"问答 {self._config.hotkey} · "
                f"截图 {self._config.screenshot_hotkey}"
            )

    @Slot()
    def start_screenshot_capture(self) -> None:
        if self._screenshot_overlay is not None:
            return
        if self._is_browser_mode():
            self._cancel_all_voice()
            if not self._confirm_browser_screen_consent():
                return
            screen = QGuiApplication.screenAt(QCursor.pos())
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            if screen is None:
                self.window.show_notice("没有找到可用屏幕。")
                return
            self._browser_capture_snapshot = BrowserCaptureSnapshot(
                main_visible=self.window.isVisible(),
                browser_visible=self.official_web_process.browser_visible,
                previous_foreground=(
                    foreground_window() if IS_WINDOWS else 0
                ),
            )
            self._capture_screen = screen
            self._hide_all_for_browser_capture()
            log_event("browser_screenshot_capture_started")
            QTimer.singleShot(250, self._capture_current_screen)
            return
        if self.window.is_busy:
            self.window.show_overlay()
            self.window.show_status("请先停止当前生成")
            return

        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.window.show_overlay()
            self.window.show_notice("没有找到可用屏幕。")
            return

        self._capture_screen = screen
        log_event("screenshot_capture_started")
        self.window.hide_overlay()
        QTimer.singleShot(180, self._capture_current_screen)

    @Slot()
    def _capture_current_screen(self) -> None:
        screen = self._capture_screen
        self._capture_screen = None
        if screen is None:
            self.window.show_overlay()
            return

        screenshot = screen.grabWindow(0)
        if screenshot.isNull():
            log_event("screenshot_capture_failed", error_type="null_pixmap")
            if self._browser_capture_snapshot is not None:
                self._restore_browser_capture_surfaces()
            else:
                self.window.show_overlay()
            self.window.show_notice("截图失败：无法读取当前屏幕。")
            return

        self._screenshot_overlay = ScreenshotOverlay(screen, screenshot)
        self._screenshot_overlay.selected.connect(self._on_screenshot_selected)
        self._screenshot_overlay.cancelled.connect(self._on_screenshot_cancelled)
        self._screenshot_overlay.show_overlay()

    @Slot(object)
    def _on_screenshot_selected(self, image) -> None:
        log_event("screenshot_selected")
        self._screenshot_overlay = None
        if self._browser_capture_snapshot is not None:
            try:
                self.browser_clipboard.set_image(image)
            except ClipboardError as exc:
                self._restore_browser_capture_surfaces()
                self.window.show_notice(str(exc))
                return
            self._restore_browser_capture_surfaces()
            message = (
                "截图已复制到系统剪贴板，但只会短暂存在。"
                "请切回官网页面按 Ctrl+V，再自行确认并发送。"
            )
            self.window.show_notice(message)
            self.official_web_process.set_message(message)
            log_event("browser_screenshot_copied")
            return
        self.window.set_pending_screenshot(image)
        self.window.show_overlay()
        if self._config.auto_send_screenshot:
            QTimer.singleShot(0, self.window.send_pending_screenshot)

    @Slot()
    def _on_screenshot_cancelled(self) -> None:
        log_event("screenshot_cancelled")
        self._screenshot_overlay = None
        if self._browser_capture_snapshot is not None:
            self._restore_browser_capture_surfaces()
            self.window.show_notice("已取消截图。")
            return
        self.window.show_overlay()
        self.window.show_status("已取消截图")

    def _hide_all_for_browser_capture(self) -> None:
        self.assistant.hide_all_for_screen_capture()
        self.window.hide_overlay()
        self.official_web_process.hide()

    def _restore_browser_capture_surfaces(self) -> None:
        snapshot = self._browser_capture_snapshot
        self._browser_capture_snapshot = None
        if snapshot is None:
            return
        if snapshot.main_visible:
            self.window.show_overlay()
        else:
            self.window.hide_overlay()
        if snapshot.browser_visible:
            self.official_web_process.show()
            if snapshot.previous_foreground and IS_WINDOWS:
                QTimer.singleShot(
                    0,
                    lambda hwnd=snapshot.previous_foreground: (
                        self._activate_previous_foreground(hwnd)
                    ),
                )

    @Slot()
    def open_settings(self) -> None:
        self._cancel_pending_screen_recognition(silent=True)
        self._cancel_all_voice()
        self._discard_personalization_draft()
        self._apply_brand_runtime(self._brand_runtime)
        self._settings_open = True
        self.assistant.input_bar.hide()
        self.assistant.bubble.hide()
        self.assistant.ball.hide()
        self.window.load_api_settings(self._config, self._api_key)
        self._refresh_official_component_status()
        self._refresh_voice_settings_view()
        self.window.show_settings_page()
        self.window.show_overlay()

    @Slot()
    def close_settings(self) -> None:
        self._cancel_all_voice()
        self._discard_personalization_draft()
        self._apply_brand_runtime(self._brand_runtime)
        self._settings_open = False
        if self._is_browser_mode():
            self.window.hide_overlay()
            self.assistant.input_bar.hide()
            self.assistant.bubble.hide()
            self.assistant.ball.hide()
            self.show_browser_window()
            return
        self.assistant.restore_configured_ball_size()
        if self.mode_coordinator.current.definition.key == "global_assistant":
            self.window.hide_overlay()
            if (
                self.assistant.is_busy
                or self.assistant.bubble.markdown_text
            ):
                if self.assistant.should_show_ball():
                    self.assistant.show_ball()
                self.assistant.bubble.show_near(
                    self.assistant.ball.geometry()
                )
            else:
                self.assistant.show_input()
        else:
            self.assistant.ball.hide()
            self.window.show_chat_page()

    @Slot()
    def save_settings(self) -> None:
        self._cancel_all_voice()
        previous_config = self._config
        values = self.window.current_settings_values()
        if not values.api_key and values.access_method != "official_browser":
            self._rollback_personalization_edit(previous_config)
            self.window.set_settings_status("API Key 不能为空。", is_error=True)
            return
        if not self.window.settings_panel.hotkeys_valid:
            self._rollback_personalization_edit(previous_config)
            self.window.set_settings_status(
                "快捷键格式不正确或存在重复，请先修正。",
                is_error=True,
            )
            return

        context_changed = (
            values.access_method != self._config.access_method
            or values.work_mode != self._config.work_mode
        )
        if (
            values.access_method != self._config.access_method
            and self._config.access_method == "official_browser"
            and self.official_web_process.is_running
            and not self._confirm_browser_close_for_switch()
        ):
            self._rollback_personalization_edit(previous_config)
            self.window.settings_panel.select_access_method(
                previous_config.access_method
            )
            self.window.set_settings_status(
                "已取消切换，官网浏览器和所有设置保持不变。"
            )
            return
        if context_changed:
            self._cancel_pending_screen_recognition(silent=True)
            try:
                create_work_mode(values.work_mode)
                if values.access_method == "official_browser":
                    status = self._query_official_component_status()
                    self._official_component_status_value = status
                    if not browser_consent_is_current(previous_config):
                        if not self._show_browser_consent_gate():
                            self._rollback_personalization_edit(
                                previous_config
                            )
                            self.window.settings_panel.select_access_method(
                                previous_config.access_method
                            )
                            self.window.set_settings_status(
                                "已取消切换，所有设置保持不变。"
                            )
                            return
                        if not self._record_browser_consent():
                            self._rollback_personalization_edit(
                                previous_config
                            )
                            self.window.settings_panel.select_access_method(
                                previous_config.access_method
                            )
                            return
                        previous_config = self._config
                    ready, message = browser_mode_ready(
                        self._config,
                        status.installed,
                        status.message,
                    )
                    if not ready:
                        raise ProviderUnavailableError(message)
                else:
                    create_chat_provider(values.access_method)
            except (
                WorkModeUnavailableError,
                ProviderUnavailableError,
                RuntimeError,
            ) as exc:
                self._rollback_personalization_edit(previous_config)
                self.window.set_settings_status(str(exc), is_error=True)
                return
            if self._current_mode_busy():
                if not self._confirm_stop_for_context_switch():
                    self.window.set_settings_status(
                        "已取消切换，当前回答和所有设置保持不变。"
                    )
                    return
                self._stop_current_mode_then(self.save_settings)
                self.window.set_settings_status(
                    "正在停止当前回答，随后切换接入方式或模式。"
                )
                return
        if self.hotkey_registry.suspended:
            try:
                self.hotkey_registry.resume()
            except (HotkeyConfigError, RuntimeError) as exc:
                self._rollback_personalization_edit(previous_config)
                self.window.set_settings_status(
                    f"恢复原快捷键失败：{exc}",
                    is_error=True,
                )
                return

        prepared = None
        new_asset_ids: set[str] = set()
        try:
            personalization = self._normalize_personalization(
                values.personalization
            )
            if self._personalization_draft is not None:
                new_asset_ids = self._personalization_draft.commit()
                self._personalization_draft = None
            assistant_position = (
                self.assistant.current_ball_position()
                if self.mode_coordinator.current.definition.key
                == "global_assistant"
                or self.assistant.ball.isVisible()
                else self._config.assistant_ball_position
            )
            updated_config = AppConfig(
                access_method=values.access_method,
                work_mode=values.work_mode,
                hotkeys=dict(values.hotkeys),
                auto_send_screenshot=values.auto_send_screenshot,
                image_max_edge=values.image_max_edge,
                no_focus_mode=values.no_focus_mode,
                opacity=values.opacity,
                acrylic_enabled=values.acrylic_enabled,
                compact_mode=self.window.is_compact,
                base_url=validate_base_url(values.base_url),
                model=values.model.strip(),
                timeout_seconds=values.timeout_seconds,
                window_geometry=self.window.current_window_geometry(),
                assistant_ball_persistent=(
                    values.assistant_ball_persistent
                ),
                assistant_auto_hide_seconds=(
                    values.assistant_auto_hide_seconds
                ),
                assistant_ball_size=values.assistant_ball_size,
                assistant_ball_position=assistant_position,
                screen_recognition_auto_send=(
                    values.screen_recognition_auto_send
                ),
                screen_recognition_prompt=(
                    values.screen_recognition_prompt
                ),
                screen_recognition_image_max_edge=(
                    values.screen_recognition_image_max_edge
                ),
                screen_recognition_consent_version=(
                    values.screen_recognition_consent_version
                ),
                voice_enabled=values.voice_enabled,
                voice_auto_listen=values.voice_auto_listen,
                voice_auto_send=values.voice_auto_send,
                voice_language=values.voice_language,
                voice_microphone_device=values.voice_microphone_device,
                voice_silence_seconds=values.voice_silence_seconds,
                voice_max_record_seconds=(
                    values.voice_max_record_seconds
                ),
                voice_start_tone_enabled=values.voice_start_tone_enabled,
                voice_consent_version=values.voice_consent_version,
                official_login_consent_version=(
                    values.official_login_consent_version
                ),
                official_login_terms_read_date=(
                    values.official_login_terms_read_date
                ),
                official_login_consent_at=values.official_login_consent_at,
                browser_mode_consent_version=(
                    values.browser_mode_consent_version
                ),
                browser_mode_terms_read_date=(
                    values.browser_mode_terms_read_date
                ),
                browser_mode_consent_at=values.browser_mode_consent_at,
                browser_clipboard_auto_clear_enabled=(
                    values.browser_clipboard_auto_clear_enabled
                ),
                browser_clipboard_clear_seconds=(
                    values.browser_clipboard_clear_seconds
                ),
                browser_screen_capture_consent_version=(
                    values.browser_screen_capture_consent_version
                ),
                browser_voice_consent_version=(
                    values.browser_voice_consent_version
                ),
                personalization=personalization,
            )
            if not updated_config.model:
                raise ConfigError("模型名不能为空。")

            prepared = self.hotkey_registry.prepare(
                hotkey_values(updated_config),
                active_context_hotkey_keys(
                    updated_config.access_method,
                    updated_config.work_mode,
                ),
            )
            key_to_save = values.api_key or self._api_key
            if key_to_save:
                save_api_key(key_to_save)
            save_config(updated_config, self._config_path)
        except (
            ConfigError,
            CredentialError,
            HotkeyConfigError,
            OSError,
            PersonalizationImageError,
        ) as exc:
            if prepared is not None:
                prepared.rollback()
            if new_asset_ids:
                delete_old_assets_after_commit(new_asset_ids)
            self._rollback_personalization_edit(previous_config)
            log_event(
                "settings_save_failed",
                error_type=type(exc).__name__,
            )
            self.window.set_settings_status(str(exc), is_error=True)
            return

        prepared.commit()
        hotkeys_changed = bool(prepared.changed_keys)
        previous_access_method = self._config.access_method
        self._config = updated_config
        self._api_key = values.api_key or self._api_key
        self._config_problem = None
        self._credential_problem = None
        self.assistant.configure(updated_config, values.api_key)
        self.screen_recognition_preview.set_opacity(updated_config.opacity)
        clipboard = getattr(self, "browser_clipboard", None)
        if clipboard is not None:
            clipboard.configure(
                auto_clear_enabled=(
                    updated_config.browser_clipboard_auto_clear_enabled
                ),
                clear_seconds=updated_config.browser_clipboard_clear_seconds,
            )
        browser_process = getattr(self, "official_web_process", None)
        if browser_process is not None:
            browser_process.set_window_opacity(updated_config.opacity)
        self._refresh_voice_settings_view()
        if context_changed:
            self.mode_coordinator.transition_to(
                create_work_mode(
                    updated_config.work_mode,
                    window=self.window,
                    assistant=self.assistant,
                ),
                cancel_request=False,
            )
            if updated_config.access_method == "official_browser":
                if not self._start_browser_process():
                    self._fallback_browser_to_api(
                        "浏览器组件启动失败，已回退到 API 接入。"
                    )
                    return
                self._browser_process_ready()
            else:
                if previous_access_method == "official_browser":
                    self.official_web_process.stop()
                if updated_config.work_mode == "global_assistant":
                    self.assistant.show_input()
                else:
                    self.window.show_overlay()
        self._update_tray_mode_actions()
        if self._settings_open:
            self.assistant.input_bar.hide()
            self.assistant.bubble.hide()
            self.assistant.ball.hide()
        self.window.update_api_settings(updated_config, values.api_key)
        self.window.settings_panel.set_personalization_values(
            updated_config.personalization
        )
        self._brand_revision += 1
        self._brand_runtime = runtime_from_config(
            updated_config,
            revision=self._brand_revision,
        )
        set_brand_runtime(self._brand_runtime)
        self._apply_brand_runtime(self._brand_runtime)
        notify_shell_association_changed()
        old_asset_ids = current_asset_ids(
            previous_config.personalization
        )
        if self._clear_personalization_on_save:
            clear_personalization_assets_after_commit()
        else:
            keep_ids = current_asset_ids(
                updated_config.personalization
            )
            delete_old_assets_after_commit(
                (old_asset_ids | new_asset_ids) - keep_ids
            )
        self._clear_personalization_on_save = False
        log_event("settings_saved")
        message = (
            "接入方式或模式已切换，快捷键与设置已立即生效。"
            if context_changed
            else "设置已保存，快捷键已立即生效。"
            if hotkeys_changed
            else "设置已保存并立即生效。"
        )
        self.window.set_settings_status(message)

    def _rollback_personalization_edit(
        self,
        previous_config: AppConfig,
    ) -> None:
        self._discard_personalization_draft()
        panel = getattr(
            getattr(self, "window", None),
            "settings_panel",
            None,
        )
        if panel is not None and hasattr(
            panel,
            "set_personalization_values",
        ):
            panel.set_personalization_values(
                previous_config.personalization
            )
        self._apply_brand_runtime(
            getattr(self, "_brand_runtime", current_brand_runtime())
        )

    def _current_mode_busy(self) -> bool:
        return self.mode_coordinator.current.is_busy()

    def _normalize_personalization(
        self,
        personalization: PersonalizationConfig,
    ) -> PersonalizationConfig:
        return PersonalizationConfig(
            interface_name=sanitize_display_name(
                personalization.interface_name,
                MAX_INTERFACE_NAME_LENGTH,
            ),
            software_name=sanitize_display_name(
                personalization.software_name,
                MAX_SOFTWARE_NAME_LENGTH,
            ),
            background_asset=personalization.background_asset,
            background_mode=personalization.background_mode,
            background_blur=personalization.background_blur,
            background_dim=personalization.background_dim,
            app_icon_asset=personalization.app_icon_asset,
            title_logo_asset=personalization.title_logo_asset,
            ball_image_asset=personalization.ball_image_asset,
        )

    def _ensure_personalization_draft(self) -> PersonalizationAssetDraft:
        if self._personalization_draft is None:
            self._personalization_draft = PersonalizationAssetDraft()
        return self._personalization_draft

    def _discard_personalization_draft(self) -> None:
        draft = getattr(self, "_personalization_draft", None)
        if draft is not None:
            draft.discard()
            self._personalization_draft = None
        self._personalization_preview_active = False
        self._clear_personalization_on_save = False

    def _preview_personalization(
        self,
        personalization: PersonalizationConfig,
    ) -> None:
        normalized = self._normalize_personalization(personalization)
        has_selection = any(
            (
                normalized.interface_name,
                normalized.software_name,
                normalized.background_asset,
                normalized.app_icon_asset,
                normalized.title_logo_asset,
                normalized.ball_image_asset,
            )
        )
        if has_selection:
            self._clear_personalization_on_save = False
        runtime = runtime_from_personalization(
            normalized,
            asset_directory=(
                self._personalization_draft.directory
                if self._personalization_draft is not None
                else None
            ),
            revision=self._brand_revision + 1,
        )
        self._personalization_preview_active = True
        self._apply_brand_runtime(runtime)

    def _apply_brand_runtime(self, runtime: BrandRuntime) -> None:
        set_brand_runtime(runtime)
        app = getattr(self, "_app", None)
        if app is not None:
            app.setApplicationDisplayName(runtime.software_name)
            app.setWindowIcon(
                load_app_icon(str(runtime.app_icon_path))
            )
        window = getattr(self, "window", None)
        if window is not None and hasattr(window, "apply_brand"):
            window.apply_brand(runtime)
        assistant = getattr(self, "assistant", None)
        if assistant is not None and hasattr(assistant, "apply_brand"):
            assistant.apply_brand(runtime)
        tray = getattr(self, "tray", None)
        if tray is not None and hasattr(tray, "apply_brand"):
            tray.apply_brand(runtime)
        preview = getattr(self, "screen_recognition_preview", None)
        if preview is not None and hasattr(preview, "apply_brand"):
            preview.apply_brand(runtime)
        browser_process = getattr(self, "official_web_process", None)
        if (
            browser_process is not None
            and browser_process.is_running
            and browser_process.browser_mode
        ):
            browser_process.set_brand(
                runtime.interface_name,
                (
                    str(runtime.title_logo_path)
                    if runtime.title_logo_path is not None
                    else ""
                ),
            )
        if (
            self._voice_model_dialog is not None
            and hasattr(self._voice_model_dialog, "apply_brand")
        ):
            self._voice_model_dialog.apply_brand(runtime)

    def _load_personalization_image(self, path: Path):
        loaded = load_local_image(path)
        if loaded.animated:
            dialog = QMessageBox(self.window)
            dialog.setIcon(QMessageBox.Icon.Information)
            dialog.setTextFormat(Qt.TextFormat.PlainText)
            dialog.setWindowTitle(
                self._brand_runtime.dialog_title("动图提示")
            )
            dialog.setText(
                "所选图片是动图，程序只使用第一帧继续处理。"
            )
            dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
            dialog.exec()
        return loaded.image

    def _show_personalization_error(self, message: str) -> None:
        dialog = QMessageBox(self.window)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowTitle(
            self._brand_runtime.dialog_title("个性化图片")
        )
        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.exec()

    @Slot()
    def select_background_image(self) -> None:
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self.window,
            self._brand_runtime.dialog_title("选择软件背景图"),
            "",
            (
                "图片 (*.png *.jpg *.jpeg *.webp *.bmp *.gif "
                "*.heic *.heif *.avif)"
            ),
        )
        if not filename:
            return
        try:
            image = self._load_personalization_image(Path(filename))
            draft = self._ensure_personalization_draft()
            asset_id = draft.stage_background(image)
        except (PersonalizationImageError, OSError) as exc:
            self._show_personalization_error(str(exc))
            return
        self.window.settings_panel.set_asset_selected(
            "background",
            asset_id,
        )

    @Slot(str)
    def select_icon_image(self, kind: str) -> None:
        if kind not in {"app", "title_logo", "ball"}:
            return
        square = self._ask_for_icon_crop()
        if square is None:
            return
        try:
            draft = self._ensure_personalization_draft()
            generated = draft.stage_icons(square)
        except (PersonalizationImageError, OSError) as exc:
            self._show_personalization_error(str(exc))
            return
        asset_id = {
            "app": generated.app_icon_id,
            "title_logo": generated.title_logo_id,
            "ball": generated.ball_image_id,
        }[kind]
        self.window.settings_panel.set_asset_selected(kind, asset_id)

    @Slot()
    def select_all_icon_images(self) -> None:
        square = self._ask_for_icon_crop()
        if square is None:
            return
        try:
            draft = self._ensure_personalization_draft()
            generated = draft.stage_icons(square)
        except (PersonalizationImageError, OSError) as exc:
            self._show_personalization_error(str(exc))
            return
        panel = self.window.settings_panel
        panel.set_asset_selected("app", generated.app_icon_id)
        panel.set_asset_selected(
            "title_logo",
            generated.title_logo_id,
        )
        panel.set_asset_selected("ball", generated.ball_image_id)

    def _ask_for_icon_crop(self):
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self.window,
            self._brand_runtime.dialog_title("选择图标源图片"),
            "",
            (
                "图片 (*.png *.jpg *.jpeg *.webp *.bmp *.gif "
                "*.heic *.heif *.avif)"
            ),
        )
        if not filename:
            return None
        try:
            image = self._load_personalization_image(Path(filename))
        except (PersonalizationImageError, OSError) as exc:
            self._show_personalization_error(str(exc))
            return None
        crop = ImageCropDialog(image, self.window)
        if crop.exec() != QDialog.DialogCode.Accepted:
            return None
        return crop.square_image()

    @Slot(str)
    def reset_personalization(self, target: str) -> None:
        panel = self.window.settings_panel
        if target == "background":
            panel.clear_asset("background")
            return
        if target.startswith("icon:"):
            panel.clear_asset(target.split(":", 1)[1])
            return
        if target != "all":
            return
        dialog = QMessageBox(self.window)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowTitle(
            self._brand_runtime.dialog_title("恢复全部个性化")
        )
        dialog.setText(
            "这会恢复默认名称、背景和三个图标，并在保存后清空"
            "个性化资产文件夹。是否继续？"
        )
        continue_button = dialog.addButton(
            "全部恢复默认",
            QMessageBox.ButtonRole.AcceptRole,
        )
        dialog.addButton(
            "取消",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(continue_button)
        dialog.exec()
        if dialog.clickedButton() is not continue_button:
            return
        self._clear_personalization_on_save = True
        panel.set_personalization_values(PersonalizationConfig())
        self._preview_personalization(PersonalizationConfig())

    @Slot()
    def create_personalized_shortcut(self) -> None:
        if not getattr(sys, "frozen", False):
            self.window.settings_panel.set_shortcut_status(
                "只有打包后的应用可以创建桌面快捷方式。",
                is_error=True,
            )
            return
        software_name = sanitize_display_name(
            self.window.settings_panel.software_name_edit.text(),
            MAX_SOFTWARE_NAME_LENGTH,
        ) or self._brand_runtime.software_name
        overwrite_foreign = False
        try:
            shortcut_path = desktop_shortcut_path(software_name)
            inspection = inspect_shortcut(shortcut_path)
            if inspection.exists and not inspection.owned:
                dialog = QMessageBox(self.window)
                dialog.setIcon(QMessageBox.Icon.Warning)
                dialog.setTextFormat(Qt.TextFormat.PlainText)
                dialog.setWindowTitle(
                    self._brand_runtime.dialog_title("快捷方式同名冲突")
                )
                dialog.setText(
                    "桌面上已有同名但并非本软件创建的快捷方式。"
                    "是否覆盖它？"
                )
                overwrite_button = dialog.addButton(
                    "覆盖",
                    QMessageBox.ButtonRole.AcceptRole,
                )
                dialog.addButton(
                    "取消",
                    QMessageBox.ButtonRole.RejectRole,
                )
                dialog.setDefaultButton(overwrite_button)
                dialog.exec()
                if dialog.clickedButton() is not overwrite_button:
                    return
                overwrite_foreign = True
            shortcut = create_desktop_shortcut(
                software_name,
                target=Path(sys.executable),
                icon_path=self._brand_runtime.app_icon_path,
                overwrite_foreign=overwrite_foreign,
            )
        except (ShortcutError, OSError) as exc:
            self.window.settings_panel.set_shortcut_status(
                str(exc),
                is_error=True,
            )
            return
        self.window.settings_panel.set_shortcut_status(
            f"快捷方式已创建：{shortcut.name}"
        )
        notify_shell_association_changed()
        log_event("personalized_shortcut_created")

    @Slot()
    def delete_personalized_shortcut(self) -> None:
        software_name = sanitize_display_name(
            self.window.settings_panel.software_name_edit.text(),
            MAX_SOFTWARE_NAME_LENGTH,
        ) or self._brand_runtime.software_name
        try:
            deleted = delete_owned_desktop_shortcut(software_name)
        except (ShortcutError, OSError) as exc:
            self.window.settings_panel.set_shortcut_status(
                str(exc),
                is_error=True,
            )
            return
        self.window.settings_panel.set_shortcut_status(
            "已删除本软件创建的快捷方式。"
            if deleted
            else "没有找到本软件创建的快捷方式。"
        )

    def _stop_current_mode_then(self, callback) -> None:
        if self.mode_coordinator.current.definition.key == "global_assistant":
            self.assistant.stop_request_then(callback)
        else:
            self.window.stop_request_then(callback)

    @Slot(QPoint)
    def _assistant_position_changed(self, point: QPoint) -> None:
        self._config = replace(
            self._config,
            assistant_ball_position=AssistantBallPosition(
                point.x(),
                point.y(),
            ),
        )
        try:
            save_config(self._config, self._config_path)
        except OSError:
            log_event(
                "assistant_position_save_failed",
                error_type="OSError",
            )

    @Slot(int)
    def _preview_assistant_ball_size(self, size: int) -> None:
        self.assistant.preview_ball_size(size)

    def _update_tray_mode_actions(self) -> None:
        self.tray.set_ball_visibility_enabled(
            self.mode_coordinator.current.definition.key
            == "global_assistant"
            and not self._is_browser_mode()
        )

    @Slot()
    def revoke_screen_recognition_consent(self) -> None:
        self._cancel_pending_screen_recognition(silent=True)
        updated = replace(
            self._config,
            screen_recognition_consent_version=0,
        )
        try:
            save_config(updated, self._config_path)
        except OSError as exc:
            self.window.set_settings_status(
                f"撤销同意失败：{exc}",
                is_error=True,
            )
            return
        self._config = updated
        self.window.settings_panel.set_screen_consent_state(False)
        log_event("screen_recognition_consent_revoked")

    @Slot()
    def revoke_voice_consent(self) -> None:
        self._cancel_all_voice()
        updated = replace(self._config, voice_consent_version=0)
        try:
            save_config(updated, self._config_path)
        except OSError as exc:
            self.window.set_settings_status(
                f"撤销麦克风同意失败：{exc}",
                is_error=True,
            )
            return
        self._config = updated
        self.window.settings_panel.set_voice_consent_state(False)
        assistant = getattr(self, "assistant", None)
        if assistant is not None:
            assistant.configure(updated, getattr(self, "_api_key", ""))
        log_event("voice_consent_revoked")

    @Slot()
    def start_assistant_voice(self) -> None:
        if self.mode_coordinator.current.definition.key != "global_assistant":
            return
        if not self._confirm_voice_consent():
            return
        valid, message = model_files_present()
        if not valid:
            self._show_mode_message(
                f"{message}。请先安装本地 SenseVoice 模型。"
            )
            self.open_voice_model_dialog()
            return
        self.assistant.start_voice_listening("input")

    @Slot()
    def start_preview_voice(self) -> None:
        if not self.screen_recognition_preview.isVisible():
            return
        if (
            self.assistant.is_listening
            or self.preview_voice.listening
        ):
            return
        if not self._confirm_voice_consent():
            return
        valid, message = model_files_present()
        if not valid:
            self.screen_recognition_preview.set_listening(False)
            self._show_mode_message(
                f"{message}。请先安装本地 SenseVoice 模型。"
            )
            self.open_voice_model_dialog()
            return
        self.preview_voice.start(self._voice_settings())

    @Slot()
    def start_browser_voice(self) -> None:
        if not self._is_browser_mode():
            return
        if self.preview_voice.listening:
            self.preview_voice.stop()
            return
        if not self._config.voice_enabled:
            self.window.show_notice(
                "语音当前未启用，请在设置中启用并安装本地模型。"
            )
            self.official_web_process.set_message(
                "语音未启用，请先在设置中启用。"
            )
            return
        if not self._confirm_browser_voice_consent():
            return
        valid, message = model_files_present()
        if not valid:
            self.window.show_notice(
                f"{message}。请先安装本地 SenseVoice 模型。"
            )
            self.open_voice_model_dialog()
            return
        self._browser_voice_active = True
        self.official_web_process.set_voice_state("listening")
        if not self.preview_voice.start(self._voice_settings()):
            self._browser_voice_active = False
            self.official_web_process.set_voice_state("idle")

    @Slot()
    def cancel_preview_voice(self) -> None:
        self.preview_voice.cancel()
        self.screen_recognition_preview.set_listening(False)

    @Slot()
    def _preview_voice_started(self) -> None:
        if self._browser_voice_active:
            self.official_web_process.set_voice_state("listening")
        else:
            self.screen_recognition_preview.set_listening(True)

    @Slot(str)
    def _preview_voice_finished(self, transcript: str) -> None:
        if self._browser_voice_active:
            self._browser_voice_active = False
            self.official_web_process.set_voice_state("idle")
            try:
                self.browser_clipboard.set_text(transcript)
            except ClipboardError as exc:
                self.window.show_notice(str(exc))
                return
            message = (
                "语音文字已复制到系统剪贴板，只在剪贴板中短暂存在。"
                "请在官网页面按 Ctrl+V，并自行确认和发送。"
            )
            self.window.show_notice(message)
            self.official_web_process.set_message(
                "语音文字已复制。请在官网页面按 Ctrl+V。"
            )
            log_event("official_browser_voice_copied")
            return
        self.screen_recognition_preview.set_listening(False)
        if self.screen_recognition_preview.isVisible():
            self.screen_recognition_preview.append_transcript(transcript)
            self.screen_recognition_preview.prompt.setFocus()

    @Slot()
    def _preview_voice_cancelled(self) -> None:
        if self._browser_voice_active:
            self._browser_voice_active = False
            self.official_web_process.set_voice_state("idle")
            return
        self.screen_recognition_preview.set_listening(False)
        if self.screen_recognition_preview.isVisible():
            self.screen_recognition_preview.prompt.setFocus()

    @Slot(str)
    def _preview_voice_failed(self, message: str) -> None:
        if self._browser_voice_active:
            self._browser_voice_active = False
            self.official_web_process.set_voice_state("idle")
            self.window.show_notice(message)
            return
        self.screen_recognition_preview.set_listening(False)
        self._show_mode_message(message)
        if self.screen_recognition_preview.isVisible():
            self.screen_recognition_preview.prompt.setFocus()

    def _voice_settings(self) -> VoiceSettings:
        return VoiceSettings(
            microphone_device=self._config.voice_microphone_device,
            language=self._config.voice_language,
            silence_seconds=self._config.voice_silence_seconds,
            max_record_seconds=self._config.voice_max_record_seconds,
            start_tone_enabled=self._config.voice_start_tone_enabled,
        )

    def _confirm_voice_consent(self) -> bool:
        if self._config.voice_consent_version >= 1:
            return True
        dialog = QMessageBox(self.window)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowTitle(
            getattr(
                self,
                "_brand_runtime",
                current_brand_runtime(),
            ).dialog_title("麦克风隐私说明")
        )
        dialog.setText("语音提问会短暂使用麦克风录音。")
        dialog.setInformativeText(
            "音频只在本机内存中交给离线 SenseVoice 模型转写，不写盘，"
            "不会发送到云端；日志不记录音频或识别文字。"
            "只有在您按快捷键或点击麦克风后才会录音。"
        )
        accept = dialog.addButton(
            "同意并启用",
            QMessageBox.ButtonRole.AcceptRole,
        )
        dialog.addButton(
            "取消",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(accept)
        dialog.exec()
        if dialog.clickedButton() is not accept:
            return False
        updated = replace(self._config, voice_consent_version=1)
        try:
            save_config(updated, self._config_path)
        except OSError as exc:
            self._show_mode_message(f"保存麦克风同意失败：{exc}")
            return False
        self._config = updated
        assistant = getattr(self, "assistant", None)
        if assistant is not None:
            assistant.configure(updated, getattr(self, "_api_key", ""))
        self.window.settings_panel.set_voice_consent_state(True)
        log_event("voice_consent_granted")
        return True

    @Slot()
    def open_voice_model_dialog(self) -> None:
        if self._voice_model_dialog is None:
            self._voice_model_dialog = VoiceModelDialog()
            self._voice_model_dialog.apply_brand(
                self._brand_runtime
            )
            self._voice_model_dialog.model_installed.connect(
                self._voice_model_installed
            )
        self._voice_model_dialog.show_for(self.window)

    @Slot()
    def import_voice_model_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self.window,
            self._brand_runtime.dialog_title(
                "选择包含 model.int8.onnx 和 tokens.txt 的文件夹"
            ),
        )
        if not folder:
            return
        self.open_voice_model_dialog()
        if self._voice_model_dialog is not None:
            self._voice_model_dialog.import_folder(Path(folder))

    @Slot()
    def _voice_model_installed(self) -> None:
        self._refresh_voice_settings_view()

    def _refresh_voice_settings_view(self) -> None:
        valid, message = validate_model_directory()
        panel = self.window.settings_panel
        panel.set_voice_model_status(valid, message)
        try:
            devices = list_microphone_devices()
        except Exception:
            devices = []
        panel.refresh_microphone_devices(
            devices,
            self._config.voice_microphone_device,
        )
        panel.set_voice_consent_state(
            self._config.voice_consent_version >= 1
        )
        panel.set_browser_screen_consent_state(
            self._config.browser_screen_capture_consent_version >= 1
        )
        panel.set_browser_voice_consent_state(
            self._config.browser_voice_consent_version >= 1
        )

    def _cancel_all_voice(self) -> None:
        assistant = getattr(self, "assistant", None)
        if assistant is not None and hasattr(
            assistant,
            "cancel_voice_listening",
        ):
            assistant.cancel_voice_listening()
        preview_voice = getattr(self, "preview_voice", None)
        if preview_voice is not None:
            preview_voice.cancel()
        self._browser_voice_active = False
        process = getattr(self, "official_web_process", None)
        if process is not None:
            process.set_voice_state("idle")
        preview = getattr(self, "screen_recognition_preview", None)
        if preview is not None and hasattr(preview, "set_listening"):
            preview.set_listening(False)

    def _voice_is_active(self) -> bool:
        assistant = getattr(self, "assistant", None)
        preview_voice = getattr(self, "preview_voice", None)
        return bool(
            getattr(assistant, "is_listening", False)
            or getattr(preview_voice, "listening", False)
        )

    @Slot()
    def _session_locked(self) -> None:
        self._cancel_all_voice()
        log_event("voice_stopped_for_session_lock")

    @Slot()
    def start_screen_recognition(self) -> None:
        if (
            self._screen_capture_screen is not None
            or self._screen_recognition_image is not None
            or self.screen_recognition_preview.isVisible()
        ):
            return
        if self._is_browser_mode():
            self._cancel_all_voice()
            if not self._confirm_browser_screen_consent():
                return
            screen = QGuiApplication.screenAt(QCursor.pos())
            screen = screen or QGuiApplication.primaryScreen()
            if screen is None:
                self.window.show_notice("没有找到可用屏幕。")
                return
            self._screen_recognition_snapshot = ScreenRecognitionSnapshot(
                mode_key="official_browser",
                main_visible=self.window.isVisible(),
                assistant=None,
                browser_visible=(
                    self.official_web_process.browser_visible
                ),
                previous_foreground=(
                    foreground_window() if IS_WINDOWS else 0
                ),
            )
            self._screen_capture_screen = screen
            self._hide_all_for_browser_capture()
            log_event("browser_screen_recognition_capture_started")
            QTimer.singleShot(
                250,
                self._capture_screen_recognition_once,
            )
            return
        if self._voice_is_active():
            self._show_mode_message(
                "正在聆听语音，请先结束、取消或等待识别完成。"
            )
            return
        if self._current_mode_busy():
            self._show_mode_message(
                "请先停止当前回答，再开始屏幕识别。"
            )
            return
        if not self._confirm_screen_recognition_consent():
            return
        preflight_error = self._screen_recognition_preflight_error()
        if preflight_error:
            self._show_mode_message(preflight_error)
            return
        screen = QGuiApplication.screenAt(QCursor.pos())
        screen = screen or QGuiApplication.primaryScreen()
        if screen is None:
            self._show_mode_message("没有找到可用屏幕。")
            return

        mode_key = self.mode_coordinator.current.definition.key
        assistant_snapshot = (
            self.assistant.capture_visibility_snapshot()
            if mode_key == "global_assistant"
            else None
        )
        self._screen_recognition_snapshot = ScreenRecognitionSnapshot(
            mode_key=mode_key,
            main_visible=self.window.isVisible(),
            assistant=assistant_snapshot,
            browser_visible=False,
            previous_foreground=(
                foreground_window() if IS_WINDOWS else 0
            ),
        )
        self._screen_capture_screen = screen
        self.window.hide_overlay()
        self.assistant.hide_all_for_screen_capture()
        log_event("screen_recognition_capture_started")
        QTimer.singleShot(
            250,
            self._capture_screen_recognition_once,
        )

    def _confirm_screen_recognition_consent(self) -> bool:
        if self._config.screen_recognition_consent_version >= 1:
            return True
        dialog = QMessageBox(self.window)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowTitle(
            getattr(
                self,
                "_brand_runtime",
                current_brand_runtime(),
            ).dialog_title("屏幕识别隐私说明")
        )
        dialog.setText(
            "一键屏幕识别会把当前屏幕截图发送给 DeepSeek。"
        )
        dialog.setInformativeText(
            "屏幕上如果有密码、验证码、聊天记录、账号信息或其他隐私内容，"
            "请不要使用。截图只在本次识别期间保存在内存中。"
        )
        accept = dialog.addButton(
            "同意并启用",
            QMessageBox.ButtonRole.AcceptRole,
        )
        dialog.addButton(
            "取消",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(accept)
        dialog.exec()
        if dialog.clickedButton() is not accept:
            return False
        updated = replace(
            self._config,
            screen_recognition_consent_version=1,
        )
        try:
            save_config(updated, self._config_path)
        except OSError as exc:
            self._show_mode_message(f"保存隐私同意失败：{exc}")
            return False
        self._config = updated
        self.window.settings_panel.set_screen_consent_state(True)
        log_event("screen_recognition_consent_granted")
        return True

    def _confirm_browser_screen_consent(self) -> bool:
        if self._config.browser_screen_capture_consent_version >= 1:
            return True
        dialog = QMessageBox(self.window)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowTitle(
            getattr(
                self,
                "_brand_runtime",
                current_brand_runtime(),
            ).dialog_title("浏览器截图复制说明")
        )
        dialog.setText(
            "浏览器模式下，截图只复制到系统剪贴板，不经本软件发送。"
        )
        dialog.setInformativeText(
            "你之后自行把图片粘贴并发送到 DeepSeek 官网时，内容会到 "
            "DeepSeek。屏幕上有密码、验证码、聊天记录、账号信息或其他"
            "隐私内容时不要使用。截图只在内存和系统剪贴板中短暂存在；"
            "本软件不会自动粘贴或发送。"
        )
        accept = dialog.addButton(
            "同意并启用",
            QMessageBox.ButtonRole.AcceptRole,
        )
        dialog.addButton(
            "取消",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(accept)
        dialog.exec()
        if dialog.clickedButton() is not accept:
            return False
        updated = replace(
            self._config,
            browser_screen_capture_consent_version=1,
        )
        try:
            save_config(updated, self._config_path)
        except OSError as exc:
            self.window.show_notice(f"保存浏览器截图同意失败：{exc}")
            return False
        self._config = updated
        self.window.settings_panel.set_browser_screen_consent_state(True)
        log_event("official_browser_screen_consent_granted")
        return True

    def _confirm_browser_voice_consent(self) -> bool:
        if self._config.browser_voice_consent_version >= 1:
            return True
        dialog = QMessageBox(self.window)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowTitle(
            getattr(
                self,
                "_brand_runtime",
                current_brand_runtime(),
            ).dialog_title("浏览器语音复制说明")
        )
        dialog.setText(
            "浏览器模式下，语音只在本机离线转写为文字并复制到系统剪贴板。"
        )
        dialog.setInformativeText(
            "本软件不会自动粘贴或发送。你之后自行粘贴并发送到 DeepSeek "
            "官网时，文字会到 DeepSeek。音频只在内存中处理，不写盘，"
            "日志不记录音频或识别文字。"
        )
        accept = dialog.addButton(
            "同意并启用",
            QMessageBox.ButtonRole.AcceptRole,
        )
        dialog.addButton(
            "取消",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(accept)
        dialog.exec()
        if dialog.clickedButton() is not accept:
            return False
        updated = replace(
            self._config,
            browser_voice_consent_version=1,
        )
        try:
            save_config(updated, self._config_path)
        except OSError as exc:
            self.window.show_notice(f"保存浏览器语音同意失败：{exc}")
            return False
        self._config = updated
        self.window.settings_panel.set_browser_voice_consent_state(True)
        log_event("official_browser_voice_consent_granted")
        return True

    def _screen_recognition_preflight_error(self) -> str | None:
        if not self._api_key:
            return "尚未配置 API Key，请先在设置中填写并保存。"
        try:
            provider = create_chat_provider(
                self._config.access_method
            )
        except ProviderUnavailableError as exc:
            return str(exc)
        return provider.image_support_error(self._config.model)

    @Slot()
    def _capture_screen_recognition_once(self) -> None:
        screen = self._screen_capture_screen
        self._screen_capture_screen = None
        snapshot = self._screen_recognition_snapshot
        if screen is None or snapshot is None:
            return
        screenshot = screen.grabWindow(0)
        if screenshot.isNull():
            self._restore_screen_recognition_surfaces(snapshot)
            self._show_mode_message("屏幕识别失败：无法读取当前屏幕。")
            self._clear_screen_recognition_state()
            return
        image = screenshot.toImage()
        if snapshot.mode_key == "official_browser":
            try:
                self.browser_clipboard.set_image(image)
            except ClipboardError as exc:
                self._restore_screen_recognition_surfaces(snapshot)
                self._clear_screen_recognition_state()
                self.window.show_notice(str(exc))
                return
            self._restore_screen_recognition_surfaces(
                snapshot,
                restore_focus=True,
            )
            self._clear_screen_recognition_state()
            message = (
                "整屏截图已复制到系统剪贴板，只在剪贴板中短暂存在。"
                "本软件没有发送图片；请切回官网页面按 Ctrl+V。"
            )
            self.window.show_notice(message)
            self.official_web_process.set_message(
                "整屏截图已复制。请在官网页面按 Ctrl+V。"
            )
            log_event("browser_screen_recognition_copied")
            return
        prompt = self._config.screen_recognition_prompt
        if self._config.screen_recognition_auto_send:
            self._dispatch_screen_recognition(image, prompt)
            return

        self._screen_recognition_image = image
        self._restore_screen_recognition_surfaces(snapshot)
        self.screen_recognition_preview.set_opacity(
            self._config.opacity
        )
        anchor = (
            snapshot.assistant.anchor
            if snapshot.assistant is not None
            else self._screen_preview_anchor(screen)
        )
        if not self.screen_recognition_preview.show_for(
            image,
            prompt,
            anchor,
        ):
            self._cancel_pending_screen_recognition(silent=False)
            self._show_mode_message("屏幕识别预览创建失败。")
            return
        log_event("screen_recognition_preview_ready")

    def _screen_preview_anchor(self, screen) -> QRect:
        area = screen.availableGeometry()
        return QRect(
            area.center().x() - 32,
            area.center().y() - 32,
            64,
            64,
        )

    @Slot(str)
    def _send_screen_recognition_preview(self, prompt: str) -> None:
        image = self._screen_recognition_image
        if image is None:
            return
        self._dispatch_screen_recognition(image, prompt)

    @Slot()
    def _cancel_screen_recognition_preview(self) -> None:
        preview_voice = getattr(self, "preview_voice", None)
        if preview_voice is not None:
            preview_voice.cancel()
        preview = getattr(self, "screen_recognition_preview", None)
        if preview is not None and hasattr(preview, "set_listening"):
            preview.set_listening(False)
        snapshot = self._screen_recognition_snapshot
        self._screen_recognition_image = None
        self._screen_recognition_snapshot = None
        log_event("screen_recognition_cancelled")
        if snapshot is not None:
            self._restore_screen_recognition_surfaces(
                snapshot,
                restore_focus=True,
            )

    def _dispatch_screen_recognition(
        self,
        image: QImage,
        prompt: str,
    ) -> None:
        snapshot = self._screen_recognition_snapshot
        if snapshot is None:
            return
        self._screen_recognition_image = None
        if snapshot.mode_key == "global_assistant":
            if snapshot.assistant is not None:
                self.assistant.prepare_screen_recognition_result(
                    snapshot.assistant
                )
            started = self.assistant.send_screen_recognition(
                image,
                prompt,
            )
        else:
            self.window.show_overlay()
            started = self.window.send_screen_recognition(image, prompt)
        self._screen_recognition_snapshot = None
        log_event(
            "screen_recognition_request_started"
            if started
            else "screen_recognition_request_rejected"
        )

    def _restore_screen_recognition_surfaces(
        self,
        snapshot: ScreenRecognitionSnapshot,
        restore_focus: bool = False,
    ) -> None:
        own_focus_restored = False
        if snapshot.mode_key == "official_browser":
            if snapshot.main_visible:
                self.window.show_overlay()
                own_focus_restored = True
            else:
                self.window.hide_overlay()
            if snapshot.browser_visible:
                self.official_web_process.show()
                own_focus_restored = False
            else:
                self.official_web_process.hide()
        elif snapshot.mode_key == "global_assistant":
            if snapshot.assistant is not None:
                self.assistant.restore_visibility_snapshot(
                    snapshot.assistant
                )
                own_focus_restored = snapshot.assistant.input_visible
                if restore_focus:
                    self.assistant.restore_primary_input_focus()
        else:
            if snapshot.main_visible:
                self.window.show_overlay()
                own_focus_restored = True
            else:
                self.window.hide_overlay()
        if (
            restore_focus
            and not own_focus_restored
            and snapshot.previous_foreground
            and IS_WINDOWS
        ):
            QTimer.singleShot(
                0,
                lambda hwnd=snapshot.previous_foreground: (
                    self._activate_previous_foreground(hwnd)
                ),
            )

    def _activate_previous_foreground(self, hwnd: int) -> None:
        try:
            activate_foreground(hwnd)
        except OSError:
            pass

    def _cancel_pending_screen_recognition(
        self,
        *,
        silent: bool,
    ) -> None:
        preview_voice = getattr(self, "preview_voice", None)
        if preview_voice is not None:
            preview_voice.cancel()
        preview = getattr(self, "screen_recognition_preview", None)
        if preview is not None and hasattr(preview, "set_listening"):
            preview.set_listening(False)
        if (
            getattr(self, "_screen_recognition_snapshot", None) is None
            and (preview is None or not preview.isVisible())
            and getattr(self, "_screen_recognition_image", None) is None
        ):
            return
        if preview is not None:
            preview.clear_image()
            preview.hide()
        self._screen_capture_screen = None
        snapshot = self._screen_recognition_snapshot
        self._screen_recognition_snapshot = None
        self._screen_recognition_image = None
        if snapshot is not None:
            self._restore_screen_recognition_surfaces(
                snapshot,
                restore_focus=not silent,
            )
        if not silent:
            log_event("screen_recognition_cancelled")

    def _clear_screen_recognition_state(self) -> None:
        self.screen_recognition_preview.clear_image()
        self.screen_recognition_preview.hide()
        self._screen_capture_screen = None
        self._screen_recognition_image = None
        self._screen_recognition_snapshot = None

    def _show_mode_message(self, message: str) -> None:
        if self.mode_coordinator.current.definition.key == "global_assistant":
            self.assistant.show_notice(message)
        else:
            self.window.show_overlay()
            self.window.show_notice(message)

    def _confirm_stop_for_context_switch(self) -> bool:
        dialog = QMessageBox(self.window)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowTitle(
            getattr(
                self,
                "_brand_runtime",
                current_brand_runtime(),
            ).dialog_title("切换会停止当前回答")
        )
        dialog.setText(
            "切换接入方式或工作模式会停止当前回答，"
            "并放弃这一轮尚未完成的回答。"
        )
        dialog.setInformativeText("是否继续切换？")
        continue_button = dialog.addButton(
            "继续切换",
            QMessageBox.ButtonRole.AcceptRole,
        )
        dialog.addButton(
            "取消切换",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(continue_button)
        dialog.exec()
        return dialog.clickedButton() is continue_button

    def _confirm_browser_close_for_switch(self) -> bool:
        dialog = QMessageBox(self.window)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowTitle(
            getattr(
                self,
                "_brand_runtime",
                current_brand_runtime(),
            ).dialog_title("切换会关闭官网浏览器")
        )
        dialog.setText(
            "切换接入方式会关闭当前官网浏览器窗口。"
            "官网页面中的登录状态会保留在本机专用目录中。"
            "页面里正在进行的回答可能继续在官网服务器生成；"
            "本软件不声称能可靠停止官网生成。"
        )
        dialog.setInformativeText("是否继续切换？")
        continue_button = dialog.addButton(
            "继续切换",
            QMessageBox.ButtonRole.AcceptRole,
        )
        dialog.addButton(
            "取消切换",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(continue_button)
        dialog.exec()
        return dialog.clickedButton() is continue_button

    @Slot()
    def _suspend_hotkeys_for_recording(self) -> None:
        if not IS_WINDOWS:
            return
        self.hotkey_registry.suspend()
        self.window.set_settings_status(
            "正在录制快捷键，全局快捷键暂时暂停。"
        )

    @Slot()
    def _resume_hotkeys_after_recording(self) -> None:
        if not IS_WINDOWS or not self.hotkey_registry.suspended:
            return
        try:
            self.hotkey_registry.resume()
        except (HotkeyConfigError, RuntimeError) as exc:
            log_event(
                "hotkey_resume_error",
                error_type=type(exc).__name__,
            )
            self.window.set_settings_status(
                f"恢复原快捷键失败：{exc}",
                is_error=True,
            )
        else:
            self.window.set_settings_status("已恢复原快捷键。")

    def _save_window_geometry(self) -> None:
        try:
            assistant_position = (
                self.assistant.current_ball_position()
                if self.mode_coordinator.current.definition.key
                == "global_assistant"
                or self.assistant.ball.isVisible()
                else self._config.assistant_ball_position
            )
            updated = replace(
                self._config,
                window_geometry=self.window.current_window_geometry(),
                compact_mode=self.window.is_compact,
                assistant_ball_position=assistant_position,
            )
            save_config(updated, self._config_path)
            self._config = updated
        except OSError:
            log_event(
                "window_geometry_save_failed",
                error_type="OSError",
            )
            return
