"""Controller-level personalization commit and rollback ordering tests."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.config import (  # noqa: E402
    AppConfig,
    AssistantBallPosition,
    PersonalizationConfig,
    WindowGeometry,
)
from ai_quiz_overlay.controller import ApplicationController  # noqa: E402
from ai_quiz_overlay.personalization_runtime import (  # noqa: E402
    runtime_from_config,
    set_brand_runtime,
)
from ai_quiz_overlay.services import personalization_assets  # noqa: E402
from ai_quiz_overlay.services.personalization_assets import (  # noqa: E402
    PersonalizationAssetDraft,
)
from ai_quiz_overlay.ui.settings_panel import SettingsValues  # noqa: E402


def values_with_personalization(
    personalization: PersonalizationConfig,
) -> SettingsValues:
    return SettingsValues(
        api_key="fake-unit-key",
        access_method="api",
        work_mode="quiz",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        timeout_seconds=60,
        hotkeys={
            "chat": "Ctrl+Alt+Q",
            "screenshot": "Ctrl+Alt+A",
            "assistant": "Ctrl+Alt+Space",
            "ball_visibility": "Ctrl+Alt+B",
            "screen_recognition": "Ctrl+Alt+S",
        },
        image_max_edge=1600,
        auto_send_screenshot=False,
        no_focus_mode=False,
        opacity=1.0,
        acrylic_enabled=False,
        assistant_ball_persistent=True,
        assistant_auto_hide_seconds=60,
        assistant_ball_size=64,
        screen_recognition_auto_send=False,
        screen_recognition_prompt="请描述屏幕。",
        screen_recognition_image_max_edge=2048,
        screen_recognition_consent_version=1,
        personalization=personalization,
    )


class PersonalizationControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _controller(self, root: Path, old_asset: Path, values):
        controller = ApplicationController.__new__(ApplicationController)
        controller._app = MagicMock()
        controller._settings_open = False
        controller._config_path = root / "config.json"
        controller._config = AppConfig(
            assistant_ball_position=AssistantBallPosition(1, 2),
            personalization=PersonalizationConfig(
                background_asset=old_asset.name
            ),
        )
        controller._api_key = "old-fake-key"
        controller._config_problem = None
        controller._credential_problem = None
        controller._brand_revision = 0
        controller._brand_runtime = runtime_from_config(controller._config)
        controller._personalization_draft = None
        controller._personalization_preview_active = False
        controller._clear_personalization_on_save = False
        controller.window = MagicMock()
        controller.window.current_settings_values.return_value = values
        controller.window.current_window_geometry.return_value = (
            WindowGeometry(0, 0, 500, 600)
        )
        controller.window.is_compact = False
        controller.window.settings_panel.hotkeys_valid = True
        controller.mode_coordinator = MagicMock()
        controller.mode_coordinator.current.definition.key = "quiz"
        controller.assistant = MagicMock()
        controller.assistant.ball.isVisible.return_value = False
        controller.tray = MagicMock()
        controller.screen_recognition_preview = MagicMock()
        controller._voice_model_dialog = None
        controller.hotkey_registry = MagicMock()
        controller.hotkey_registry.suspended = False
        prepared = MagicMock()
        prepared.changed_keys = []
        controller.hotkey_registry.prepare.return_value = prepared
        controller._refresh_voice_settings_view = MagicMock()
        controller._update_tray_mode_actions = MagicMock()
        return controller

    def test_config_save_failure_preserves_old_asset_and_restores_runtime(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_asset = root / "old-background.png"
            old_asset.write_bytes(b"old")
            image = QImage(64, 64, QImage.Format.Format_RGB32)
            image.fill(QColor("#ffffff"))
            with patch.object(
                personalization_assets,
                "personalization_directory",
                return_value=root,
            ):
                draft = PersonalizationAssetDraft()
                new_id = draft.stage_background(image)
                values = values_with_personalization(
                    PersonalizationConfig(background_asset=new_id)
                )
                controller = self._controller(root, old_asset, values)
                controller._personalization_draft = draft
                with (
                    patch(
                        "ai_quiz_overlay.controller.save_api_key"
                    ),
                    patch(
                        "ai_quiz_overlay.controller.save_config",
                        side_effect=OSError("disk full"),
                    ),
                ):
                    controller.save_settings()
            self.assertEqual(old_asset.read_bytes(), b"old")
            self.assertFalse((root / new_id).exists())
            self.assertEqual(
                controller._config.personalization.background_asset,
                old_asset.name,
            )
            self.assertIn("disk full", controller.window.set_settings_status.call_args.args[0])
            set_brand_runtime(runtime_from_config(AppConfig()))

    def test_old_asset_is_deleted_only_after_successful_config_save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_asset = root / "old-background.png"
            old_asset.write_bytes(b"old")
            image = QImage(64, 64, QImage.Format.Format_RGB32)
            image.fill(QColor("#d9a93f"))
            with patch.object(
                personalization_assets,
                "personalization_directory",
                return_value=root,
            ):
                draft = PersonalizationAssetDraft()
                new_id = draft.stage_background(image)
                values = values_with_personalization(
                    PersonalizationConfig(background_asset=new_id)
                )
                controller = self._controller(root, old_asset, values)
                controller._personalization_draft = draft
                with (
                    patch(
                        "ai_quiz_overlay.controller.save_api_key"
                    ),
                    patch(
                        "ai_quiz_overlay.controller.save_config"
                    ) as save,
                ):
                    controller.save_settings()
            self.assertTrue(save.called)
            self.assertTrue((root / new_id).is_file())
            self.assertFalse(old_asset.exists())
            set_brand_runtime(runtime_from_config(AppConfig()))

    def test_full_reset_clears_assets_only_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_asset = root / "old-background.png"
            old_asset.write_bytes(b"old")
            values = values_with_personalization(PersonalizationConfig())
            controller = self._controller(root, old_asset, values)
            controller._clear_personalization_on_save = True
            with patch.object(
                personalization_assets,
                "personalization_directory",
                return_value=root,
            ):
                with (
                    patch(
                        "ai_quiz_overlay.controller.save_api_key"
                    ),
                    patch(
                        "ai_quiz_overlay.controller.save_config"
                    ) as save,
                ):
                    controller.save_settings()
            self.assertTrue(save.called)
            self.assertFalse(old_asset.exists())
            set_brand_runtime(runtime_from_config(AppConfig()))

    def test_full_reset_keeps_assets_when_config_save_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_asset = root / "old-background.png"
            old_asset.write_bytes(b"old")
            values = values_with_personalization(PersonalizationConfig())
            controller = self._controller(root, old_asset, values)
            controller._clear_personalization_on_save = True
            with patch.object(
                personalization_assets,
                "personalization_directory",
                return_value=root,
            ):
                with (
                    patch(
                        "ai_quiz_overlay.controller.save_api_key"
                    ),
                    patch(
                        "ai_quiz_overlay.controller.save_config",
                        side_effect=OSError("disk full"),
                    ),
                ):
                    controller.save_settings()
            self.assertEqual(old_asset.read_bytes(), b"old")
            set_brand_runtime(runtime_from_config(AppConfig()))


if __name__ == "__main__":
    unittest.main()
