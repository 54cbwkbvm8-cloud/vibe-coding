"""配置文件读写的纯逻辑测试。"""

from pathlib import Path
import json
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.config import (  # noqa: E402
    AppConfig,
    ConfigError,
    PersonalizationConfig,
    WindowGeometry,
    load_config,
    sanitize_display_name,
    save_config,
)


class ConfigTests(unittest.TestCase):
    def test_missing_file_creates_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = load_config(path)
            self.assertEqual(config, AppConfig())
            self.assertTrue(path.exists())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["schema_version"], 2)
            self.assertEqual(data["access_method"], "api")
            self.assertEqual(data["work_mode"], "quiz")
            self.assertEqual(
                data["hotkeys"],
                {
                    "chat": "Ctrl+Alt+Q",
                    "screenshot": "Ctrl+Alt+A",
                    "assistant": "Ctrl+Alt+Space",
                    "ball_visibility": "Ctrl+Alt+B",
                    "screen_recognition": "Ctrl+Alt+S",
                },
            )
            self.assertEqual(data["hotkey"], "Ctrl+Alt+Q")
            self.assertEqual(data["screenshot_hotkey"], "Ctrl+Alt+A")
            self.assertFalse(data["auto_send_screenshot"])
            self.assertEqual(data["image_max_edge"], 1600)
            self.assertFalse(data["no_focus_mode"])
            self.assertEqual(data["opacity"], 1.0)
            self.assertTrue(data["acrylic_enabled"])
            self.assertFalse(data["compact_mode"])
            self.assertEqual(data["base_url"], "https://api.deepseek.com")
            self.assertEqual(data["model"], "deepseek-flash")
            self.assertEqual(data["timeout_seconds"], 60)
            self.assertIsNone(data["window_geometry"])
            self.assertTrue(data["assistant_ball_persistent"])
            self.assertEqual(data["assistant_auto_hide_seconds"], 60)
            self.assertIsNone(data["assistant_ball_position"])
            self.assertEqual(data["assistant_ball_size"], 64)
            self.assertFalse(data["screen_recognition_auto_send"])
            self.assertEqual(
                data["screen_recognition_prompt"],
                "请概括当前画面在做什么，提取关键文字，并指出需要注意的地方。",
            )
            self.assertEqual(
                data["screen_recognition_image_max_edge"],
                2048,
            )
            self.assertEqual(
                data["screen_recognition_consent_version"],
                0,
            )
            self.assertFalse(data["voice_enabled"])
            self.assertFalse(data["voice_auto_listen"])
            self.assertFalse(data["voice_auto_send"])
            self.assertEqual(data["voice_language"], "zh")
            self.assertEqual(data["voice_microphone_device"], "")
            self.assertEqual(data["voice_silence_seconds"], 1.2)
            self.assertEqual(data["voice_max_record_seconds"], 30)
            self.assertTrue(data["voice_start_tone_enabled"])
            self.assertEqual(data["voice_consent_version"], 0)
            self.assertEqual(
                data["personalization"],
                {
                    "interface_name": "",
                    "software_name": "",
                    "background": {
                        "asset": "",
                        "mode": "cover",
                        "blur": 8,
                        "dim": 55,
                    },
                    "icons": {
                        "app": "",
                        "title_logo": "",
                        "ball": "",
                    },
                },
            )

    def test_custom_hotkey_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"schema_version": 1, "hotkey": "Ctrl+Shift+Q"}),
                encoding="utf-8",
            )
            self.assertEqual(load_config(path).hotkey, "Ctrl+Shift+Q")
            migrated = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(migrated["schema_version"], 2)
            self.assertEqual(
                migrated["hotkeys"]["chat"],
                "Ctrl+Shift+Q",
            )

    def test_utf8_bom_config_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"schema_version": 1, "hotkey": "Ctrl+Shift+Q"}),
                encoding="utf-8-sig",
            )
            self.assertEqual(load_config(path).hotkey, "Ctrl+Shift+Q")

    def test_invalid_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_empty_hotkey_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"hotkey": "  "}), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_saved_config_never_contains_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            save_config(AppConfig(), path)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("api_key", text)
            self.assertNotIn("sk-", text)

    def test_invalid_base_url_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"base_url": "api.deepseek.com"}),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_base_url_is_locked_to_official_https_origin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for value in (
                "http://api.deepseek.com",
                "https://example.com",
                "https://api.deepseek.com/proxy",
                "https://api.deepseek.com:443",
                "https://user@" + "api.deepseek.com",
            ):
                path.write_text(
                    json.dumps({"base_url": value}),
                    encoding="utf-8",
                )
                with self.subTest(value=value):
                    with self.assertRaises(ConfigError):
                        load_config(path)

    def test_invalid_timeout_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"timeout_seconds": 0}),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_duplicate_hotkeys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "hotkey": "Ctrl+Alt+Q",
                        "screenshot_hotkey": "Ctrl+Alt+Q",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_v1_migration_preserves_settings_and_creates_backup_once(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            original = {
                "schema_version": 1,
                "hotkey": "Ctrl+Shift+F11",
                "screenshot_hotkey": "Ctrl+Shift+F12",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-flash",
                "timeout_seconds": 42,
                "image_max_edge": 1200,
                "auto_send_screenshot": True,
                "no_focus_mode": True,
                "opacity": 0.4,
                "acrylic_enabled": False,
                "compact_mode": True,
                "window_geometry": {
                    "x": 120,
                    "y": 80,
                    "width": 500,
                    "height": 620,
                },
            }
            original_text = json.dumps(original, ensure_ascii=False, indent=2)
            path.write_text(original_text, encoding="utf-8")

            loaded = load_config(path)
            backup = Path(directory) / "config.json.v1.bak"
            self.assertTrue(backup.exists())
            self.assertEqual(backup.read_text(encoding="utf-8"), original_text)
            self.assertEqual(loaded.access_method, "api")
            self.assertEqual(loaded.work_mode, "quiz")
            self.assertEqual(loaded.hotkeys["chat"], "Ctrl+Shift+F11")
            self.assertEqual(
                loaded.hotkeys["screenshot"],
                "Ctrl+Shift+F12",
            )
            self.assertEqual(loaded.timeout_seconds, 42)
            self.assertEqual(loaded.image_max_edge, 1200)
            self.assertTrue(loaded.auto_send_screenshot)
            self.assertTrue(loaded.no_focus_mode)
            self.assertEqual(loaded.opacity, 0.4)
            self.assertFalse(loaded.acrylic_enabled)
            self.assertTrue(loaded.compact_mode)

            backup.write_text("do-not-overwrite", encoding="utf-8")
            load_config(path)
            self.assertEqual(
                backup.read_text(encoding="utf-8"),
                "do-not-overwrite",
            )

    def test_v2_keeps_legacy_hotkey_fields_for_downgrade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = AppConfig(
                hotkeys={
                    "chat": "Ctrl+Shift+F11",
                    "screenshot": "Ctrl+Shift+F12",
                    "assistant": "Ctrl+Alt+Space",
                    "ball_visibility": "Ctrl+Alt+B",
                    "screen_recognition": "Ctrl+Alt+S",
                }
            )
            save_config(config, path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["hotkey"], "Ctrl+Shift+F11")
            self.assertEqual(
                data["screenshot_hotkey"],
                "Ctrl+Shift+F12",
            )

    def test_access_method_and_work_mode_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "access_method": "api",
                        "work_mode": "quiz",
                    }
                ),
                encoding="utf-8",
            )
            loaded = load_config(path)
            self.assertEqual(loaded.access_method, "api")
            self.assertEqual(loaded.work_mode, "quiz")
            save_config(loaded, path)
            reloaded = load_config(path)
            self.assertEqual(reloaded.access_method, "api")
            self.assertEqual(reloaded.work_mode, "quiz")

    def test_assistant_window_settings_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "work_mode": "global_assistant",
                        "assistant_ball_persistent": False,
                        "assistant_auto_hide_seconds": 25,
                        "assistant_ball_size": 160,
                        "assistant_ball_position": {"x": 120, "y": 340},
                        "screen_recognition_auto_send": True,
                        "screen_recognition_prompt": "自定义屏幕提示",
                        "screen_recognition_image_max_edge": 2560,
                        "screen_recognition_consent_version": 1,
                    }
                ),
                encoding="utf-8",
            )
            loaded = load_config(path)
            self.assertEqual(loaded.work_mode, "global_assistant")
            self.assertFalse(loaded.assistant_ball_persistent)
            self.assertEqual(loaded.assistant_auto_hide_seconds, 25)
            self.assertEqual(loaded.assistant_ball_size, 160)
            self.assertEqual(loaded.assistant_ball_position.x, 120)
            self.assertEqual(loaded.assistant_ball_position.y, 340)
            self.assertTrue(loaded.screen_recognition_auto_send)
            self.assertEqual(
                loaded.screen_recognition_prompt,
                "自定义屏幕提示",
            )
            self.assertEqual(
                loaded.screen_recognition_image_max_edge,
                2560,
            )
            self.assertEqual(
                loaded.screen_recognition_consent_version,
                1,
            )

    def test_assistant_ball_size_validation_and_default_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"schema_version": 2}),
                encoding="utf-8",
            )
            self.assertEqual(load_config(path).assistant_ball_size, 64)

            for invalid in (39, 161, True, "64"):
                path.write_text(
                    json.dumps(
                        {
                            "schema_version": 2,
                            "assistant_ball_size": invalid,
                        }
                    ),
                    encoding="utf-8",
                )
                with self.assertRaises(ConfigError):
                    load_config(path)

    def test_screen_recognition_config_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            invalid_values = (
                {"screen_recognition_auto_send": "yes"},
                {"screen_recognition_prompt": ""},
                {"screen_recognition_image_max_edge": 511},
                {"screen_recognition_image_max_edge": 4097},
                {"screen_recognition_consent_version": 2},
                {"screen_recognition_consent_version": True},
            )
            for invalid in invalid_values:
                path.write_text(
                    json.dumps(
                        {"schema_version": 2, **invalid}
                    ),
                    encoding="utf-8",
                )
                with self.assertRaises(ConfigError):
                    load_config(path)

    def test_voice_defaults_are_added_to_existing_schema_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "hotkey": "Ctrl+Shift+F11",
                        "screenshot_hotkey": "Ctrl+Shift+F12",
                        "timeout_seconds": 42,
                    }
                ),
                encoding="utf-8",
            )
            loaded = load_config(path)
            self.assertFalse(loaded.voice_enabled)
            self.assertFalse(loaded.voice_auto_listen)
            self.assertFalse(loaded.voice_auto_send)
            self.assertEqual(loaded.voice_language, "zh")
            self.assertEqual(loaded.voice_silence_seconds, 1.2)
            self.assertEqual(loaded.voice_max_record_seconds, 30)
            self.assertTrue(loaded.voice_start_tone_enabled)
            self.assertEqual(loaded.voice_consent_version, 0)

    def test_voice_settings_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = AppConfig(
                voice_enabled=True,
                voice_auto_listen=True,
                voice_auto_send=True,
                voice_language="en",
                voice_microphone_device="Parallels Microphone",
                voice_silence_seconds=1.8,
                voice_max_record_seconds=45,
                voice_start_tone_enabled=False,
                voice_consent_version=1,
            )
            save_config(config, path)
            loaded = load_config(path)
            self.assertTrue(loaded.voice_enabled)
            self.assertTrue(loaded.voice_auto_listen)
            self.assertTrue(loaded.voice_auto_send)
            self.assertEqual(loaded.voice_language, "en")
            self.assertEqual(
                loaded.voice_microphone_device,
                "Parallels Microphone",
            )
            self.assertEqual(loaded.voice_silence_seconds, 1.8)
            self.assertEqual(loaded.voice_max_record_seconds, 45)
            self.assertFalse(loaded.voice_start_tone_enabled)
            self.assertEqual(loaded.voice_consent_version, 1)

    def test_voice_config_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            invalid_values = (
                {"voice_enabled": "yes"},
                {"voice_auto_listen": 1},
                {"voice_auto_send": "no"},
                {"voice_language": "fr"},
                {"voice_microphone_device": 2},
                {"voice_silence_seconds": 0.2},
                {"voice_silence_seconds": 5.1},
                {"voice_max_record_seconds": 4},
                {"voice_max_record_seconds": 121},
                {"voice_start_tone_enabled": "yes"},
                {"voice_consent_version": 2},
            )
            for invalid in invalid_values:
                path.write_text(
                    json.dumps({"schema_version": 2, **invalid}),
                    encoding="utf-8",
                )
                with self.assertRaises(ConfigError):
                    load_config(path)

    def test_personalization_round_trip_and_sanitization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = AppConfig(
                personalization=PersonalizationConfig(
                    interface_name=sanitize_display_name(
                        "  <b>自定义</b>\u0000  ",
                        32,
                    ),
                    software_name="奶蛙 & 朋友",
                    background_asset="background-abc.png",
                    background_mode="contain",
                    background_blur=12,
                    background_dim=20,
                    app_icon_asset="app-icon-abc.ico",
                    title_logo_asset="title-logo-abc.png",
                    ball_image_asset="ball-abc.png",
                )
            )
            save_config(config, path)
            loaded = load_config(path)
            self.assertEqual(
                loaded.personalization.interface_name,
                "<b>自定义</b>",
            )
            self.assertEqual(
                loaded.personalization.software_name,
                "奶蛙 & 朋友",
            )
            self.assertEqual(
                loaded.personalization.background_mode,
                "contain",
            )
            self.assertEqual(loaded.personalization.background_dim, 20)

    def test_personalization_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            invalid_values = (
                {"personalization": []},
                {
                    "personalization": {
                        "background": {"mode": "stretch"}
                    }
                },
                {
                    "personalization": {
                        "background": {"blur": 21}
                    }
                },
                {
                    "personalization": {
                        "background": {"dim": 19}
                    }
                },
                {
                    "personalization": {
                        "icons": {"app": "../escape.ico"}
                    }
                },
            )
            for invalid in invalid_values:
                path.write_text(
                    json.dumps({"schema_version": 2, **invalid}),
                    encoding="utf-8",
                )
                with self.assertRaises(ConfigError):
                    load_config(path)

    def test_unknown_config_fields_survive_save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "future_top_level": {"keep": True},
                        "personalization": {
                            "interface_name": "旧名称",
                            "future_personalization": [1, 2, 3],
                        },
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(path)
            config = AppConfig(
                personalization=PersonalizationConfig(
                    interface_name="新名称"
                )
            )
            save_config(config, path)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["future_top_level"],
                {"keep": True},
            )
            self.assertEqual(
                saved["personalization"]["future_personalization"],
                [1, 2, 3],
            )
            self.assertEqual(
                saved["personalization"]["interface_name"],
                "新名称",
            )

    def test_invalid_auto_send_value_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"auto_send_screenshot": "yes"}),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_window_geometry_is_saved_and_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = AppConfig(
                window_geometry=WindowGeometry(120, 80, 500, 620),
            )
            save_config(config, path)
            self.assertEqual(load_config(path).window_geometry, config.window_geometry)

    def test_invalid_opacity_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"opacity": -0.1}), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_existing_opacity_is_preserved_above_new_floor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"opacity": 0.4}), encoding="utf-8")
            self.assertEqual(load_config(path).opacity, 0.4)

    def test_opacity_below_20_percent_is_clamped_to_new_floor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"opacity": 0.1}), encoding="utf-8")
            self.assertEqual(load_config(path).opacity, 0.2)

    def test_theme_and_compact_state_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = AppConfig(
                acrylic_enabled=False,
                compact_mode=True,
            )
            save_config(config, path)
            loaded = load_config(path)
            self.assertFalse(loaded.acrylic_enabled)
            self.assertTrue(loaded.compact_mode)

    def test_invalid_image_max_edge_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"image_max_edge": 9999}), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_invalid_no_focus_value_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps({"no_focus_mode": 1}),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
