"""Liquid-glass window behavior tests that do not capture the desktop."""

from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.config import (  # noqa: E402
    AppConfig,
    PersonalizationConfig,
    WindowGeometry,
)
from ai_quiz_overlay.personalization_runtime import (  # noqa: E402
    runtime_from_config,
    runtime_from_personalization,
    set_brand_runtime,
)
from ai_quiz_overlay.ui.main_window import (  # noqa: E402
    HTBOTTOM,
    HTBOTTOMLEFT,
    HTBOTTOMRIGHT,
    HTLEFT,
    HTRIGHT,
    HTTOP,
    HTTOPLEFT,
    HTTOPRIGHT,
    MainWindow,
)
from ai_quiz_overlay.ui.settings_panel import (  # noqa: E402
    PAGE_ACCESS,
    PAGE_APPEARANCE,
    PAGE_HOTKEYS,
    PAGE_PERSONALIZATION,
    PAGE_RECOGNITION,
    SettingsPanel,
)
from ai_quiz_overlay.theme import (  # noqa: E402
    GLASS_OPACITY_MIN,
    GLASS_PANEL_MIN_ALPHA,
    THEME,
    glass_alpha,
    readability_scrim_alpha,
)
from ai_quiz_overlay.services.window_geometry import (  # noqa: E402
    restore_window_rect,
)
from ai_quiz_overlay.ui.title_bar import TitleBar  # noqa: E402
from ai_quiz_overlay.ui.glass_checkbox import GlassCheckBox  # noqa: E402
from ai_quiz_overlay.ui.hotkey_editor import HotkeyEditor  # noqa: E402
from ai_quiz_overlay.ui.large_spinbox import LargeSpinBox  # noqa: E402
from ai_quiz_overlay.win32.acrylic import ACRYLIC_FALLBACK_ENV  # noqa: E402
from ai_quiz_overlay.ui.voice_model_dialog import VoiceModelDialog  # noqa: E402
from ai_quiz_overlay.ui.image_crop_dialog import ImageCropDialog  # noqa: E402
from ai_quiz_overlay.ui.personalized_background import (  # noqa: E402
    GlassSurfaceRenderer,
)


class GlassUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_opacity_floor_keeps_background_dark_enough(self) -> None:
        self.assertEqual(GLASS_OPACITY_MIN, 0.20)
        self.assertGreaterEqual(
            glass_alpha(GLASS_OPACITY_MIN),
            GLASS_PANEL_MIN_ALPHA,
        )
        self.assertEqual(glass_alpha(0.1), glass_alpha(GLASS_OPACITY_MIN))
        self.assertGreater(glass_alpha(1.0), glass_alpha(0.2))

    def test_label_scrim_fades_with_opacity(self) -> None:
        self.assertEqual(readability_scrim_alpha(0.82), 0)
        self.assertGreater(readability_scrim_alpha(0.50), 0)
        self.assertGreater(
            readability_scrim_alpha(0.20),
            readability_scrim_alpha(0.50),
        )

    def test_traffic_lights_emit_real_actions(self) -> None:
        title_bar = TitleBar()
        emitted: list[str] = []
        title_bar.close_requested.connect(lambda: emitted.append("hide"))
        title_bar.minimize_requested.connect(lambda: emitted.append("minimize"))
        title_bar.compact_toggle_requested.connect(
            lambda: emitted.append("compact")
        )
        title_bar.close_button.click()
        title_bar.minimize_button.click()
        title_bar.compact_button.click()
        self.assertEqual(emitted, ["hide", "minimize", "compact"])

    def test_compact_mode_restores_last_expanded_geometry(self) -> None:
        window = MainWindow()
        expanded = WindowGeometry(100, 120, 520, 640)
        window.restore_saved_geometry(expanded)
        window.set_compact_mode(True)
        self.assertTrue(window.is_compact)
        self.assertLess(window.height(), 200)
        self.assertTrue(window._body.isHidden())
        self.assertFalse(window._compact_bar.isHidden())
        self.assertEqual(window.current_window_geometry(), expanded)

        window.set_compact_mode(False)
        self.assertFalse(window.is_compact)
        self.assertEqual(window.width(), 520)
        self.assertEqual(window.height(), 640)
        window.deleteLater()

    def test_opacity_changes_glass_only_not_window_text(self) -> None:
        window = MainWindow()
        window.set_window_opacity(0.62)
        self.assertAlmostEqual(window.glass_opacity, 0.62)
        self.assertAlmostEqual(window.windowOpacity(), 1.0)
        window.deleteLater()

    def test_window_renders_antialiased_transparent_corners(self) -> None:
        window = MainWindow()
        window.show()
        self.app.processEvents()
        image = window.grab().toImage()
        self.assertFalse(image.isNull())
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        window.hide()
        window.deleteLater()

    def test_compact_send_auto_expands_before_request(self) -> None:
        window = MainWindow()
        window.set_compact_mode(True)
        observed: list[bool] = []
        window._start_request = lambda: observed.append(window.is_compact)
        window._compact_bar.set_text("自动展开测试")
        window._handle_compact_send()
        self.assertEqual(observed, [False])
        self.assertIn("自动展开测试", window._question_input.toPlainText())
        window.deleteLater()

    def test_environment_override_reaches_runtime_fallback(self) -> None:
        window = MainWindow()
        with patch.dict(
            os.environ,
            {ACRYLIC_FALLBACK_ENV: "1"},
            clear=False,
        ):
            window.set_acrylic_enabled(True)
            window.show()
            loop = QEventLoop()
            QTimer.singleShot(120, loop.quit)
            loop.exec()
            self.assertFalse(window.acrylic_active)
            self.assertFalse(
                window.settings_panel.acrylic_checkbox.isEnabled()
            )
            self.assertIn("强制", window.acrylic_reason)
        window.hide()
        window.deleteLater()

    def test_saved_compact_mode_restores_on_startup(self) -> None:
        window = MainWindow()
        expanded = WindowGeometry(140, 160, 540, 680)
        window.restore_saved_geometry(expanded)
        window.load_api_settings(
            AppConfig(compact_mode=True, acrylic_enabled=False),
            "",
        )
        self.assertTrue(window.is_compact)
        expected = restore_window_rect(
            expanded,
            [
                screen.availableGeometry()
                for screen in QGuiApplication.screens()
            ],
            QSize(420, 560),
        )
        self.assertEqual(
            window.current_window_geometry(),
            WindowGeometry(
                expected.x(),
                expected.y(),
                expected.width(),
                expected.height(),
            ),
        )
        window.deleteLater()

    def test_window_has_no_reserved_transparent_shadow_margin(self) -> None:
        window = MainWindow()
        margins = window.layout().contentsMargins()
        self.assertEqual(THEME.shadow_margin, 0)
        self.assertEqual(
            (margins.left(), margins.top(), margins.right(), margins.bottom()),
            (0, 0, 0, 0),
        )
        self.assertTrue(
            window.windowFlags()
            & Qt.WindowType.NoDropShadowWindowHint
        )
        window.deleteLater()

    def test_native_resize_hit_zones_cover_edges_and_corners(self) -> None:
        window = MainWindow()
        window.resize(520, 640)
        width = window.width()
        height = window.height()

        def hit(x: int, y: int) -> int:
            return window._resize_hit_test_local(QPoint(x, y))

        self.assertEqual(hit(0, height // 2), HTLEFT)
        self.assertEqual(hit(width - 1, height // 2), HTRIGHT)
        self.assertEqual(hit(width // 2, 0), HTTOP)
        self.assertEqual(hit(width // 2, height - 1), HTBOTTOM)
        self.assertEqual(hit(0, 0), HTTOPLEFT)
        self.assertEqual(hit(width - 1, 0), HTTOPRIGHT)
        self.assertEqual(hit(0, height - 1), HTBOTTOMLEFT)
        self.assertEqual(hit(width - 1, height - 1), HTBOTTOMRIGHT)
        self.assertEqual(hit(17, 17), HTTOPLEFT)
        self.assertEqual(hit(width // 2, height // 2), 0)

        window.set_compact_mode(True)
        self.assertEqual(
            window._resize_hit_test_local(QPoint(0, 20)),
            HTLEFT,
        )
        self.assertEqual(
            window._resize_hit_test_local(QPoint(window.width() - 1, 20)),
            HTRIGHT,
        )
        self.assertEqual(
            window._resize_hit_test_local(QPoint(window.width() // 2, 0)),
            0,
        )
        window.deleteLater()

    def test_expanded_minimum_height_covers_chat_size_hint(self) -> None:
        window = MainWindow()
        content_height = window._chat_page.sizeHint().height()
        self.assertGreaterEqual(
            window.minimumHeight(),
            THEME.title_height + content_height,
        )
        window.deleteLater()

    def test_settings_exposes_acrylic_switch_and_opacity_floor(self) -> None:
        panel = SettingsPanel()
        panel.set_values(AppConfig(acrylic_enabled=False, opacity=0.20), "")
        self.assertFalse(panel.acrylic_checkbox.isChecked())
        self.assertEqual(panel.opacity_slider.minimum(), 20)
        self.assertEqual(panel.opacity_slider.value(), 20)
        self.assertEqual(panel.opacity_value_label.text(), "20%")
        self.assertAlmostEqual(panel.values().opacity, 0.20)
        self.assertEqual(panel.values().access_method, "api")
        self.assertEqual(panel.values().work_mode, "quiz")
        self.assertFalse(panel.values().acrylic_enabled)
        panel.set_acrylic_availability(False, "测试不可用")
        self.assertFalse(panel.acrylic_checkbox.isEnabled())
        self.assertFalse(panel.acrylic_checkbox.isChecked())
        panel.deleteLater()

    def test_unavailable_acrylic_is_unchecked_but_preference_is_kept(
        self,
    ) -> None:
        panel = SettingsPanel()
        panel.set_values(AppConfig(acrylic_enabled=True), "")
        panel.set_acrylic_availability(False, "测试不可用")
        self.assertFalse(panel.acrylic_checkbox.isChecked())
        self.assertFalse(panel.acrylic_checkbox.isEnabled())
        self.assertTrue(panel.values().acrylic_enabled)
        panel.deleteLater()

    def test_global_assistant_display_settings_are_preserved(self) -> None:
        panel = SettingsPanel()
        panel.set_values(
            AppConfig(
                work_mode="global_assistant",
                assistant_ball_persistent=False,
                assistant_auto_hide_seconds=25,
                assistant_ball_size=120,
            ),
            "",
        )
        self.assertTrue(panel.assistant_ball_persistent_checkbox.isEnabled())
        self.assertFalse(
            panel.assistant_ball_persistent_checkbox.isChecked()
        )
        self.assertEqual(panel.assistant_auto_hide_spin.value(), 25)
        self.assertEqual(panel.assistant_ball_size_slider.value(), 120)
        self.assertEqual(
            panel.assistant_ball_size_value_label.text(),
            "120 px",
        )
        values = panel.values()
        self.assertEqual(values.work_mode, "global_assistant")
        self.assertFalse(values.assistant_ball_persistent)
        self.assertEqual(values.assistant_auto_hide_seconds, 25)
        self.assertEqual(values.assistant_ball_size, 120)
        panel.deleteLater()

    def test_settings_tabs_keep_all_existing_controls(self) -> None:
        panel = SettingsPanel()
        panel.set_values(AppConfig(), "")
        self.assertEqual(panel.tabs.count(), 5)
        self.assertEqual(panel.page_stack.count(), 5)
        self.assertEqual(panel.tabs.tabText(PAGE_ACCESS), "接入")
        self.assertEqual(panel.tabs.tabText(PAGE_HOTKEYS), "快捷键")
        self.assertEqual(panel.tabs.tabText(PAGE_APPEARANCE), "外观")
        self.assertEqual(
            panel.tabs.tabText(PAGE_RECOGNITION),
            "识别与语音",
        )
        self.assertEqual(
            panel.tabs.tabText(PAGE_PERSONALIZATION),
            "个性化",
        )
        for attribute in (
            "api_key_edit",
            "base_url_edit",
            "model_edit",
            "timeout_spin",
            "hotkey_editors",
            "image_max_edge_spin",
            "auto_send_checkbox",
            "no_focus_checkbox",
            "acrylic_checkbox",
            "opacity_slider",
            "assistant_ball_size_slider",
            "screen_auto_send_checkbox",
            "screen_prompt_edit",
            "screen_image_max_edge_spin",
            "screen_consent_label",
            "screen_revoke_button",
            "voice_enabled_checkbox",
            "voice_auto_listen_checkbox",
            "voice_auto_send_checkbox",
            "voice_start_tone_checkbox",
            "microphone_combo",
            "voice_language_combo",
            "voice_silence_spin",
            "voice_max_record_spin",
            "voice_model_status_label",
            "voice_model_download_button",
            "voice_model_import_button",
            "voice_consent_label",
            "voice_revoke_button",
            "interface_name_edit",
            "software_name_edit",
            "background_select_button",
            "background_reset_button",
            "background_mode_combo",
            "background_blur_slider",
            "background_dim_slider",
            "background_dim_warning",
            "all_icons_button",
            "create_shortcut_button",
            "delete_shortcut_button",
            "reset_all_personalization_button",
            "shortcut_hint_label",
        ):
            self.assertTrue(hasattr(panel, attribute))
        self.assertIn(
            "Parallels 共享到 Mac",
            panel.shortcut_hint_label.text(),
        )
        panel.deleteLater()

    def test_voice_settings_round_trip_and_controls(self) -> None:
        panel = SettingsPanel()
        config = AppConfig(
            voice_enabled=True,
            voice_auto_listen=True,
            voice_auto_send=True,
            voice_language="en",
            voice_microphone_device="Synthetic Microphone",
            voice_silence_seconds=1.8,
            voice_max_record_seconds=45,
            voice_start_tone_enabled=False,
            voice_consent_version=1,
        )
        panel.set_values(config, "")
        values = panel.values()
        self.assertTrue(values.voice_enabled)
        self.assertTrue(values.voice_auto_listen)
        self.assertTrue(values.voice_auto_send)
        self.assertEqual(values.voice_language, "en")
        self.assertEqual(
            values.voice_microphone_device,
            "Synthetic Microphone",
        )
        self.assertEqual(values.voice_silence_seconds, 1.8)
        self.assertEqual(values.voice_max_record_seconds, 45)
        self.assertFalse(values.voice_start_tone_enabled)
        self.assertEqual(values.voice_consent_version, 1)
        self.assertTrue(panel.microphone_combo.isEnabled())
        panel.voice_enabled_checkbox.setChecked(False)
        self.assertFalse(panel.microphone_combo.isEnabled())
        panel.deleteLater()

    def test_personalization_settings_round_trip_and_dim_warning(self) -> None:
        panel = SettingsPanel()
        panel.set_values(
            AppConfig(
                personalization=PersonalizationConfig(
                    interface_name="<b>界面</b>",
                    software_name="奶蛙 & 朋友",
                    background_asset="background-test.png",
                    background_mode="contain",
                    background_blur=12,
                    background_dim=20,
                    app_icon_asset="app-icon-test.ico",
                    title_logo_asset="title-logo-test.png",
                    ball_image_asset="ball-test.png",
                )
            ),
            "",
        )
        values = panel.values().personalization
        self.assertEqual(values.interface_name, "<b>界面</b>")
        self.assertEqual(values.software_name, "奶蛙 & 朋友")
        self.assertEqual(values.background_mode, "contain")
        self.assertEqual(values.background_blur, 12)
        self.assertEqual(values.background_dim, 20)
        self.assertFalse(panel.background_dim_warning.isHidden())
        panel.background_dim_slider.setValue(35)
        self.assertTrue(panel.background_dim_warning.isHidden())
        panel.deleteLater()

    def test_five_tabs_fit_minimum_width_and_support_keyboard(self) -> None:
        panel = SettingsPanel()
        panel.resize(420, 640)
        panel.show()
        self.app.processEvents()
        for index in range(panel.tabs.count()):
            text = panel.tabs.tabText(index)
            available = panel.tabs.tabRect(index).width() - 8
            self.assertLessEqual(
                panel.tabs.fontMetrics().horizontalAdvance(text),
                available,
            )
        panel.tabs.setCurrentIndex(0)
        panel.tabs.setFocus()
        QTest.keyClick(
            panel.tabs,
            Qt.Key.Key_Tab,
            Qt.KeyboardModifier.ControlModifier,
        )
        self.assertEqual(panel.tabs.currentIndex(), 1)
        QTest.keyClick(
            panel.tabs,
            Qt.Key.Key_Tab,
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.ShiftModifier,
        )
        self.assertEqual(panel.tabs.currentIndex(), 0)
        panel.hide()
        panel.deleteLater()

    def test_custom_names_are_plain_text_and_long_title_elides(self) -> None:
        runtime = runtime_from_config(
            AppConfig(
                personalization=PersonalizationConfig(
                    interface_name="<b>" + ("W" * 28) + "</b>",
                    software_name="奶蛙 & <b>朋友</b>",
                )
            ),
            revision=99,
        )
        set_brand_runtime(runtime)
        try:
            window = MainWindow()
            window.resize(420, 560)
            window.show()
            self.app.processEvents()
            self.assertEqual(
                window.title_bar.title_label.textFormat(),
                Qt.TextFormat.PlainText,
            )
            self.assertEqual(
                window.title_bar.title_label.toolTip(),
                runtime.interface_name,
            )
            self.assertIn("…", window.title_bar.title_label.text())
            self.assertEqual(window.windowTitle(), runtime.software_name)
            self.assertGreater(
                window.title_bar.settings_button.width(),
                0,
            )
            window.hide()
            window.deleteLater()
        finally:
            set_brand_runtime(runtime_from_config(AppConfig()))

    def test_custom_background_is_cached_high_dpi_and_clipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset_directory = Path(directory)
            background = QImage(320, 180, QImage.Format.Format_RGB32)
            background.fill(QColor("#fffef2"))
            self.assertTrue(
                background.save(
                    str(asset_directory / "bright.png"),
                    "PNG",
                )
            )
            runtime = runtime_from_personalization(
                PersonalizationConfig(
                    background_asset="bright.png",
                    background_dim=20,
                ),
                asset_directory=asset_directory,
                revision=12,
            )
            set_brand_runtime(runtime)
            try:
                window = MainWindow()
                window.resize(420, 560)
                window.apply_brand(runtime)
                window.set_window_opacity(0.20)
                window.show()
                self.app.processEvents()
                image = window.grab().toImage()
                self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
                self.assertGreater(
                    image.pixelColor(
                        image.width() // 2,
                        image.height() // 2,
                    ).alpha(),
                    0,
                )
                self.assertFalse(window._glass_cache.isNull())
                window.hide()
                window.deleteLater()
            finally:
                set_brand_runtime(runtime_from_config(AppConfig()))

    def test_background_releases_source_and_debounces_resize(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset_directory = Path(directory)
            background = QImage(640, 360, QImage.Format.Format_RGB32)
            background.fill(QColor("#ffffff"))
            self.assertTrue(
                background.save(
                    str(asset_directory / "bright.png"),
                    "PNG",
                )
            )
            runtime = runtime_from_personalization(
                PersonalizationConfig(
                    background_asset="bright.png",
                    background_dim=20,
                ),
                asset_directory=asset_directory,
                revision=50,
            )
            parent = QWidget()
            renderer = GlassSurfaceRenderer(parent)
            renderer.configure(runtime)
            first = renderer.pixmap_for(
                520,
                760,
                2.0,
                opacity=0.20,
                active=True,
            )
            self.assertFalse(first.isNull())
            self.assertIsNone(renderer.retained_source)
            old_physical_size = first.size()
            renderer.pixmap_for(
                600,
                800,
                2.0,
                opacity=0.20,
                active=True,
            )
            self.assertTrue(renderer._timer.isActive())
            self.assertEqual(renderer.cached_pixmap.size(), old_physical_size)
            deadline = 0
            while (
                (
                    renderer.cached_pixmap.size() != QSize(1200, 1600)
                    or renderer._load_thread is not None
                )
                and deadline < 3000
            ):
                QTest.qWait(50)
                deadline += 50
            self.assertEqual(
                renderer.cached_pixmap.size(),
                QSize(1200, 1600),
            )
            self.assertGreater(renderer.last_render_ms, 0)
            self.assertGreater(renderer.last_decode_ms, 0)
            rendered_mode = renderer._key[7]
            changed_runtime = runtime_from_personalization(
                PersonalizationConfig(
                    background_asset="bright.png",
                    background_mode="contain",
                    background_blur=14,
                    background_dim=60,
                ),
                asset_directory=asset_directory,
                revision=51,
            )
            renderer.configure(changed_runtime)
            changed = renderer.pixmap_for(
                600,
                800,
                2.0,
                opacity=0.20,
                active=True,
            )
            self.assertFalse(changed.isNull())
            self.assertNotEqual(rendered_mode, renderer._key[7])
            renderer.pixmap_for(
                600,
                800,
                1.5,
                opacity=0.20,
                active=True,
            )
            self.assertTrue(renderer._timer.isActive())
            deadline = 0
            while (
                (
                    renderer._key is None
                    or renderer._key[2] != 1.5
                    or renderer._load_thread is not None
                )
                and deadline < 3000
            ):
                QTest.qWait(50)
                deadline += 50
            self.assertEqual(renderer.cached_pixmap.size(), QSize(900, 1200))
            self.assertIsNone(renderer._load_thread)
            renderer.shutdown()
            self.assertTrue(renderer._shutting_down)
            self.assertIsNone(renderer._load_thread)
            parent.deleteLater()

    def test_background_shutdown_joins_pending_decoder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            asset_directory = Path(directory)
            background = QImage(1920, 1080, QImage.Format.Format_RGB32)
            background.fill(QColor("#fef6da"))
            self.assertTrue(
                background.save(
                    str(asset_directory / "large.png"),
                    "PNG",
                )
            )
            runtime = runtime_from_personalization(
                PersonalizationConfig(
                    background_asset="large.png",
                    background_blur=8,
                ),
                asset_directory=asset_directory,
                revision=52,
            )
            parent = QWidget()
            renderer = GlassSurfaceRenderer(parent)
            renderer.configure(runtime)
            renderer.pixmap_for(
                520,
                760,
                2.0,
                opacity=0.20,
                active=True,
            )
            renderer.pixmap_for(
                640,
                820,
                2.0,
                opacity=0.20,
                active=True,
            )
            QTest.qWait(130)
            renderer.shutdown()
            self.assertTrue(renderer._shutting_down)
            self.assertIsNone(renderer._load_thread)
            self.assertTrue(
                renderer.pixmap_for(
                    640,
                    820,
                    2.0,
                    opacity=0.20,
                    active=True,
                ).isNull()
            )
            parent.deleteLater()

    def test_crop_dialog_warns_when_source_is_below_high_dpi_size(
        self,
    ) -> None:
        image = QImage(200, 150, QImage.Format.Format_RGB32)
        image.fill(QColor("#ffffff"))
        dialog = ImageCropDialog(image)
        dialog.show()
        self.app.processEvents()
        self.assertIn(
            "320×320",
            dialog.warning_label.text(),
        )
        self.assertFalse(dialog.square_image().isNull())
        dialog.reject()
        dialog.deleteLater()

    def test_opening_voice_ui_does_not_start_network_request(self) -> None:
        with patch(
            "ai_quiz_overlay.services.voice_models.urllib.request.build_opener"
        ) as build_opener:
            panel = SettingsPanel()
            panel.set_values(AppConfig(voice_enabled=True), "")
            dialog = VoiceModelDialog()
            dialog.show_for()
            self.app.processEvents()
            dialog.close()
            panel.deleteLater()
        build_opener.assert_not_called()

    def test_tabs_align_with_content_and_hide_settings_button(self) -> None:
        window = MainWindow()
        window.show_settings_page()
        window.show()
        self.app.processEvents()
        panel = window.settings_panel
        first_tab_left = panel.tabs.mapTo(
            panel,
            panel.tabs.tabRect(0).topLeft(),
        ).x()
        content_left = (
            panel.scroll_areas[PAGE_ACCESS].mapTo(panel, QPoint(0, 0)).x()
            + 16
        )
        self.assertLessEqual(abs(first_tab_left - content_left), 1)
        gap_one = panel.tabs.tabRect(1).left() - panel.tabs.tabRect(0).right()
        gap_two = panel.tabs.tabRect(2).left() - panel.tabs.tabRect(1).right()
        self.assertLessEqual(abs(gap_one - gap_two), 1)
        self.assertTrue(window.title_bar.settings_button.isHidden())
        window.show_chat_page()
        self.assertFalse(window.title_bar.settings_button.isHidden())
        window.hide()
        window.deleteLater()

    def test_low_opacity_adds_label_scrim_and_group_divider_exists(self) -> None:
        window = MainWindow()
        window.set_window_opacity(0.20)
        self.assertIn(
            str(readability_scrim_alpha(0.20)),
            window.title_bar.title_label.styleSheet(),
        )
        window.set_window_opacity(0.82)
        self.assertIn(
            "transparent",
            window.settings_panel._scrim_labels[0].styleSheet(),
        )
        self.assertTrue(
            window.settings_panel.findChildren(
                QWidget,
                "settingsDivider",
            )
        )
        window.deleteLater()

    def test_experimental_access_remains_selectable(self) -> None:
        panel = SettingsPanel()
        panel.set_official_web_state(
            installed=True,
            message="组件已安装",
            consent_current=True,
            consent_version=1,
            terms_read_date="2026-11-08",
            consent_at="2026-11-08T10:00:00+08:00",
        )
        panel.set_values(AppConfig(), "")
        official_login = panel.access_selection.button_for("official_login")
        global_assistant = panel.work_mode_selection.button_for(
            "global_assistant"
        )
        self.assertTrue(official_login.isEnabled())
        self.assertIn("实验性", official_login.text())
        self.assertIn("非官方", official_login.text())
        self.assertTrue(global_assistant.isEnabled())
        QTest.mouseClick(official_login, Qt.MouseButton.LeftButton)
        QTest.mouseClick(global_assistant, Qt.MouseButton.LeftButton)
        self.assertEqual(
            panel.access_selection.selected_key(),
            "official_login",
        )
        self.assertEqual(
            panel.work_mode_selection.selected_key(),
            "global_assistant",
        )
        self.assertTrue(panel.assistant_auto_hide_spin.isEnabled())
        self.assertTrue(panel.assistant_ball_size_slider.isEnabled())
        panel.deleteLater()

    def test_official_component_controls_and_title_badge(self) -> None:
        panel = SettingsPanel()
        requests: list[str] = []
        panel.access_method_requested.connect(requests.append)
        panel.set_official_web_state(
            installed=True,
            message="组件已安装",
            consent_current=True,
            consent_version=1,
            terms_read_date="2026-11-08",
            consent_at="2026-11-08T10:00:00+08:00",
        )
        self.assertTrue(panel.official_login_button.isEnabled())
        self.assertTrue(panel.official_revoke_button.isEnabled())
        panel.access_selection.button_for("official_login").click()
        self.assertEqual(requests[-1], "official_login")
        window = MainWindow()
        window.set_official_mode_badge(True)
        self.assertFalse(window.title_bar.official_badge.isHidden())
        window.set_official_mode_badge(False)
        self.assertTrue(window.title_bar.official_badge.isHidden())
        window.deleteLater()
        panel.deleteLater()

    def test_browser_mode_settings_state_and_clipboard_controls(self) -> None:
        panel = SettingsPanel()
        panel.set_official_web_state(
            installed=True,
            message="组件已安装",
            consent_current=False,
        )
        panel.set_browser_mode_state(
            installed=True,
            message="浏览器组件已安装",
            consent_current=True,
            consent_version=1,
            terms_read_date="2026-11-08",
            consent_at="2026-11-08T10:00:00+08:00",
        )
        panel.set_values(
            AppConfig(
                access_method="official_browser",
                browser_mode_consent_version=1,
                browser_mode_terms_read_date="2026-11-08",
                browser_mode_consent_at="2026-11-08T10:00:00+08:00",
                browser_clipboard_auto_clear_enabled=False,
                browser_clipboard_clear_seconds=75,
                browser_screen_capture_consent_version=1,
                browser_voice_consent_version=1,
            ),
            "",
        )
        browser = panel.access_selection.button_for("official_browser")
        self.assertTrue(browser.isEnabled())
        self.assertIn("独立浏览器", browser.text())
        self.assertTrue(panel.browser_open_button.isEnabled())
        self.assertFalse(
            panel.browser_clipboard_seconds_spin.isEnabled()
        )
        values = panel.values()
        self.assertEqual(values.access_method, "official_browser")
        self.assertFalse(values.browser_clipboard_auto_clear_enabled)
        self.assertEqual(values.browser_clipboard_clear_seconds, 75)
        self.assertEqual(values.browser_screen_capture_consent_version, 1)
        self.assertEqual(values.browser_voice_consent_version, 1)
        panel.set_browser_chromium_version("130.0.0.0")
        self.assertIn("130.0.0.0", panel.browser_chromium_label.text())
        panel.deleteLater()

    def test_screen_recognition_hotkey_is_editable_and_validated(self) -> None:
        panel = SettingsPanel()
        panel.set_values(AppConfig(), "")
        assistant = panel.hotkey_editors["assistant"]
        self.assertTrue(assistant.recorder.isEnabled())
        ball_visibility = panel.hotkey_editors["ball_visibility"]
        self.assertTrue(ball_visibility.recorder.isEnabled())
        self.assertEqual(ball_visibility.value(), "Ctrl+Alt+B")
        self.assertIn(
            "仅全局助手模式下生效",
            ball_visibility.availability_label.text(),
        )
        screen = panel.hotkey_editors["screen_recognition"]
        self.assertTrue(screen.recorder.isEnabled())
        self.assertTrue(screen.reset_button.isEnabled())
        self.assertEqual(screen.value(), "Ctrl+Alt+S")
        screen.set_value("Ctrl+Alt+Q")
        panel._validate_hotkey_editors()
        self.assertFalse(panel.hotkeys_valid)
        self.assertFalse(panel.save_button.isEnabled())
        panel.deleteLater()

    def test_screen_recognition_settings_and_consent_revoke(self) -> None:
        panel = SettingsPanel()
        panel.set_values(
            AppConfig(
                screen_recognition_auto_send=True,
                screen_recognition_prompt="自定义提示词",
                screen_recognition_image_max_edge=2560,
                screen_recognition_consent_version=1,
            ),
            "",
        )
        self.assertTrue(panel.screen_auto_send_checkbox.isChecked())
        self.assertEqual(
            panel.screen_prompt_edit.toPlainText(),
            "自定义提示词",
        )
        self.assertEqual(
            panel.screen_image_max_edge_spin.value(),
            2560,
        )
        self.assertTrue(panel.screen_revoke_button.isEnabled())
        revoked: list[bool] = []
        panel.screen_consent_revoked.connect(
            lambda: revoked.append(True)
        )
        panel.screen_revoke_button.click()
        self.assertEqual(revoked, [True])
        self.assertFalse(panel.screen_revoke_button.isEnabled())
        self.assertEqual(
            panel.values().screen_recognition_consent_version,
            0,
        )
        panel.screen_prompt_reset_button.click()
        self.assertIn(
            "概括当前画面",
            panel.screen_prompt_edit.toPlainText(),
        )
        panel.deleteLater()

    def test_screen_recognition_page_scrolls_above_footer(self) -> None:
        panel = SettingsPanel()
        panel.resize(430, 480)
        panel.show()
        panel.tabs.setCurrentIndex(PAGE_RECOGNITION)
        self.app.processEvents()
        scroll = panel.scroll_areas[PAGE_RECOGNITION].verticalScrollBar()
        scroll.setValue(scroll.maximum())
        self.app.processEvents()
        viewport = panel.scroll_areas[PAGE_RECOGNITION].viewport()
        bottom_control = panel.browser_clipboard_seconds_spin
        button_pos = bottom_control.mapTo(
            viewport,
            QPoint(0, 0),
        )
        button_rect = QRect(button_pos, bottom_control.size())
        self.assertTrue(viewport.rect().contains(button_rect))
        footer = panel.findChild(QWidget, "settingsFooter")
        self.assertGreater(
            footer.geometry().top(),
            panel.scroll_areas[PAGE_RECOGNITION].geometry().bottom(),
        )
        panel.hide()
        panel.deleteLater()

    def test_ball_size_slider_previews_and_restores_default(self) -> None:
        panel = SettingsPanel()
        panel.set_values(
            AppConfig(work_mode="global_assistant"),
            "",
        )
        previews: list[int] = []
        panel.assistant_ball_size_preview.connect(previews.append)
        panel.assistant_ball_size_slider.setValue(160)
        self.assertEqual(previews[-1], 160)
        self.assertEqual(
            panel.assistant_ball_size_value_label.text(),
            "160 px",
        )
        panel.assistant_ball_size_reset_button.click()
        self.assertEqual(panel.assistant_ball_size_slider.value(), 64)
        self.assertEqual(previews[-1], 64)
        panel.deleteLater()

    def test_api_key_load_does_not_leave_programmatic_selection(self) -> None:
        panel = SettingsPanel()
        panel.set_values(AppConfig(), "unit-test-placeholder")
        self.assertFalse(panel.api_key_edit.hasSelectedText())
        self.assertEqual(
            panel.api_key_edit.cursorPosition(),
            len("unit-test-placeholder"),
        )
        panel.focus_api_key()
        self.assertFalse(panel.api_key_edit.hasSelectedText())
        panel.deleteLater()

    def test_large_spin_buttons_have_stable_28_by_24_targets(self) -> None:
        spin = LargeSpinBox()
        spin.resize(260, 42)
        spin.show()
        self.app.processEvents()
        up_rect, down_rect = spin.step_button_rects()
        self.assertEqual((up_rect.width(), up_rect.height()), (28, 24))
        self.assertEqual((down_rect.width(), down_rect.height()), (28, 24))
        self.assertGreaterEqual(down_rect.left(), up_rect.right())
        spin.setValue(10)
        spin.stepUp()
        self.assertEqual(spin.value(), 11)
        spin.stepDown()
        self.assertEqual(spin.value(), 10)
        spin.hide()
        spin.deleteLater()

    def test_checked_checkbox_paints_a_dark_check_mark(self) -> None:
        checkbox = GlassCheckBox("测试")
        checkbox.resize(180, 30)
        checkbox.setChecked(True)
        checkbox.show()
        self.app.processEvents()
        image = checkbox.grab().toImage()
        dark_pixels = 0
        for x in range(2, 20):
            for y in range(5, 25):
                color = image.pixelColor(x, y)
                if max(color.red(), color.green(), color.blue()) < 100:
                    dark_pixels += 1
        self.assertGreater(dark_pixels, 8)
        checkbox.hide()
        checkbox.deleteLater()

    def test_hotkey_hint_is_a_wrapping_full_width_label(self) -> None:
        window = MainWindow()
        window.set_hotkey_hint(
            "Ctrl+Alt+Shift+F11",
            "Ctrl+Alt+Shift+F12",
        )
        self.assertTrue(window._hotkey_hint_label.wordWrap())
        self.assertIn("Ctrl+Alt+Shift+F11", window._hotkey_hint_label.text())
        self.assertIn("Ctrl+Alt+Shift+F12", window._hotkey_hint_label.text())
        window.deleteLater()

    def test_settings_button_remains_available_during_generation(self) -> None:
        window = MainWindow()
        window._set_busy(True)
        self.assertTrue(window.title_bar.settings_button.isEnabled())
        window._set_busy(False)
        window.deleteLater()

    def test_hotkey_recorder_requires_modifier_and_records_combination(
        self,
    ) -> None:
        editor = HotkeyEditor("Ctrl+Alt+Q")
        editor.resize(360, 80)
        editor.show()
        editor.raise_()
        editor.activateWindow()
        editor.recorder.setFocus()
        QTest.qWait(30)
        self.assertTrue(editor.recorder.recording)

        QTest.keyClick(editor.recorder, Qt.Key.Key_Q)
        self.app.processEvents()
        self.assertTrue(editor.recorder.recording)
        self.assertIn("修饰键", editor.error_label.text())

        QTest.keyClick(
            editor.recorder,
            Qt.Key.Key_F11,
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.ShiftModifier,
        )
        self.app.processEvents()
        self.assertFalse(editor.recorder.recording)
        self.assertEqual(editor.value(), "Ctrl+Shift+F11")
        editor.reset_button.click()
        self.assertEqual(editor.value(), "Ctrl+Alt+Q")
        editor.hide()
        editor.deleteLater()

    def test_duplicate_hotkeys_disable_save_until_corrected(self) -> None:
        panel = SettingsPanel()
        panel.set_values(AppConfig(), "")
        screenshot_editor = panel.hotkey_editors["screenshot"]
        screenshot_editor.set_value("Alt+Ctrl+Q")
        panel._validate_hotkey_editors()
        self.assertFalse(panel.hotkeys_valid)
        self.assertFalse(panel.save_button.isEnabled())
        self.assertFalse(panel.hotkey_editor.error_label.isHidden())
        self.assertFalse(screenshot_editor.error_label.isHidden())

        screenshot_editor.restore_default()
        panel._validate_hotkey_editors()
        self.assertTrue(panel.hotkeys_valid)
        self.assertTrue(panel.save_button.isEnabled())
        panel.deleteLater()

    def test_invalid_recording_disables_save_until_reset(self) -> None:
        panel = SettingsPanel()
        panel.resize(430, 560)
        panel.set_values(AppConfig(), "")
        panel.show()
        self.app.processEvents()
        editor = panel.hotkey_editor
        editor.recorder.setFocus()
        self.app.processEvents()
        self.assertTrue(editor.recorder.recording)
        QTest.keyClick(editor.recorder, Qt.Key.Key_Q)
        self.app.processEvents()
        self.assertFalse(panel.hotkeys_valid)
        self.assertFalse(panel.save_button.isEnabled())
        editor.reset_button.click()
        self.assertTrue(panel.hotkeys_valid)
        self.assertTrue(panel.save_button.isEnabled())
        panel.hide()
        panel.deleteLater()

    def test_settings_footer_is_separate_and_bottom_content_is_scrollable(
        self,
    ) -> None:
        panel = SettingsPanel()
        panel.resize(430, 480)
        panel.show()
        panel.tabs.setCurrentIndex(PAGE_APPEARANCE)
        self.app.processEvents()
        scroll = panel.scroll_area.verticalScrollBar()
        scroll.setValue(scroll.maximum())
        self.app.processEvents()

        viewport = panel.scroll_area.viewport()
        checkbox_position = panel.no_focus_checkbox.mapTo(viewport, QPoint(0, 0))
        checkbox_rect = QRect(
            checkbox_position,
            panel.no_focus_checkbox.size(),
        )
        self.assertTrue(viewport.rect().contains(checkbox_rect))
        footer = panel.findChild(QWidget, "settingsFooter")
        self.assertIsNotNone(footer)
        self.assertGreater(
            footer.geometry().top(),
            panel.scroll_area.geometry().bottom(),
        )
        panel.hide()
        panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
