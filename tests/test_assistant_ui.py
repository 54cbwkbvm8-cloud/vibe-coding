"""Global-assistant ball, input bar, and bubble tests."""

from pathlib import Path
import sys
import unittest
from unittest.mock import PropertyMock, patch

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.assistant_controller import (  # noqa: E402
    AssistantController,
    _clamp_ball_position,
)
from ai_quiz_overlay.config import (  # noqa: E402
    AppConfig,
    AssistantBallPosition,
)
from ai_quiz_overlay.branding import asset_path  # noqa: E402
from ai_quiz_overlay.mode_coordinator import ModeCoordinator  # noqa: E402
from ai_quiz_overlay.ui.assistant_ball import (  # noqa: E402
    DEFAULT_FADE_MS,
    AssistantBall,
    _frog_pixmap,
)
from ai_quiz_overlay.ui.assistant_surfaces import (  # noqa: E402
    AssistantBubble,
    AssistantInputBar,
    _clamp_rect,
)
from ai_quiz_overlay.ui.tray_controller import TrayController  # noqa: E402
from ai_quiz_overlay.ui.screen_recognition_preview import (  # noqa: E402
    ScreenRecognitionPreview,
)
from ai_quiz_overlay.work_modes import create_work_mode  # noqa: E402
from ai_quiz_overlay.voice_controller import VoiceController  # noqa: E402


class AssistantUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_ball_states_animation_and_transparent_corners(self) -> None:
        ball = AssistantBall()
        ball.show_without_activation()
        self.app.processEvents()
        for state in ("idle", "thinking", "responding", "listening"):
            ball.set_state(state)
            self.assertEqual(ball.state, state)
        self.assertTrue(ball._timer.isActive())
        image = ball.grab().toImage()
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        ball.hide()
        self.assertFalse(ball._timer.isActive())
        ball.deleteLater()

    def test_listening_ball_has_clean_edges_at_all_sizes(self) -> None:
        ball = AssistantBall()
        ball.show_without_activation()
        for size in (40, 64, 160):
            ball.set_ball_size(size)
            ball.set_state("listening")
            ball.set_voice_level(80)
            self.app.processEvents()
            image = ball.grab().toImage()
            self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
            self.assertEqual(
                image.pixelColor(image.width() - 1, 0).alpha(),
                0,
            )
            self.assertTrue(ball._timer.isActive())
        ball.hide()
        self.assertFalse(ball._timer.isActive())
        ball.deleteLater()

    def test_ball_high_resolution_asset_supports_max_size(self) -> None:
        source = QImage(
            str(asset_path("brand", "assistant_ball_1024.png"))
        )
        self.assertFalse(source.isNull())
        self.assertGreaterEqual(source.width(), 1024)
        pixmap = _frog_pixmap(160, 2.0)
        self.assertFalse(pixmap.isNull())
        self.assertEqual(pixmap.width(), 320)
        self.assertEqual(pixmap.height(), 320)

    def test_ball_size_preserves_center_and_clamps_near_edge(self) -> None:
        ball = AssistantBall()
        ball.move(400, 300)
        old_center = ball.frameGeometry().center()
        ball.set_ball_size(40)
        self.assertEqual(ball.ball_size, 40)
        self.assertEqual(ball.width(), 60)
        ball.set_ball_size(160)
        self.assertEqual(ball.ball_size, 160)
        self.assertEqual(ball.width(), 240)
        self.assertLessEqual(
            abs(ball.frameGeometry().center().x() - old_center.x()),
            1,
        )
        self.assertLessEqual(
            abs(ball.frameGeometry().center().y() - old_center.y()),
            1,
        )

        screen = self.app.primaryScreen()
        area = screen.availableGeometry()
        ball.move(area.right() - 20, area.bottom() - 20)
        ball.set_ball_size(120)
        self.assertLessEqual(ball.frameGeometry().right(), area.right())
        self.assertLessEqual(ball.frameGeometry().bottom(), area.bottom())
        ball.deleteLater()

    def test_ball_fade_hides_within_two_hundred_milliseconds(self) -> None:
        self.assertLessEqual(DEFAULT_FADE_MS, 200)
        ball = AssistantBall()
        ball.show_without_activation()
        self.app.processEvents()
        ball.set_visible_animated(False, DEFAULT_FADE_MS)
        QTest.qWait(DEFAULT_FADE_MS + 80)
        self.assertFalse(ball.isVisible())
        self.assertFalse(ball._timer.isActive())
        ball.set_visible_animated(True, DEFAULT_FADE_MS)
        QTest.qWait(DEFAULT_FADE_MS + 80)
        self.assertTrue(ball.isVisible())
        self.assertAlmostEqual(ball.windowOpacity(), 1.0, places=2)
        ball.hide()
        ball.deleteLater()

    def test_ball_snap_stays_inside_available_screen(self) -> None:
        ball = AssistantBall()
        ball.move(-500, -500)
        ball.snap_to_edge()
        screen = ball.screen() or QApplication.primaryScreen()
        self.assertIsNotNone(screen)
        area = screen.availableGeometry()
        self.assertGreaterEqual(ball.x(), area.left())
        self.assertGreaterEqual(ball.y(), area.top())
        self.assertLessEqual(ball.frameGeometry().right(), area.right())
        self.assertLessEqual(ball.frameGeometry().bottom(), area.bottom())
        ball.deleteLater()

    def test_input_enter_escape_and_stop_button(self) -> None:
        bar = AssistantInputBar()
        sent: list[str] = []
        dismissed: list[bool] = []
        stopped: list[bool] = []
        bar.send_requested.connect(sent.append)
        bar.dismissed.connect(lambda: dismissed.append(True))
        bar.stop_requested.connect(lambda: stopped.append(True))
        bar.show_focused(QRect(100, 100, 96, 96))
        self.app.processEvents()
        bar.input.setText("你好")
        QTest.keyClick(bar.input, Qt.Key.Key_Return)
        self.assertEqual(sent, ["你好"])
        QTest.keyClick(bar.input, Qt.Key.Key_Escape)
        self.assertEqual(dismissed, [True])
        bar.set_busy(True)
        bar.send_button.click()
        self.assertEqual(stopped, [True])
        bar.deleteLater()

    def test_input_listening_indicator_and_transcript_append(self) -> None:
        bar = AssistantInputBar()
        bar.input.setText("保留已有文字")
        bar.append_transcript("这是语音补充")
        self.assertEqual(
            bar.input.text(),
            "保留已有文字 这是语音补充",
        )
        bar.set_listening(True)
        self.assertTrue(bar.listening_label.isVisibleTo(bar))
        self.assertTrue(bar.voice_level.isVisibleTo(bar))
        self.assertFalse(bar.send_button.isEnabled())
        bar.set_voice_level(75)
        self.assertEqual(bar.voice_level._level, 75)
        bar.set_listening(False)
        self.assertFalse(bar.listening_label.isVisibleTo(bar))
        self.assertTrue(bar.send_button.isEnabled())
        bar.deleteLater()

    def test_bubble_markdown_copy_and_auto_hide_timer(self) -> None:
        bubble = AssistantBubble()
        bubble.set_auto_hide_seconds(5)
        bubble.begin_stream()
        bubble.append_markdown("## 标题\n\n正文")
        bubble.show_near(QRect(100, 100, 96, 96))
        bubble.show_result()
        self.assertIn("标题", bubble.markdown_text)
        self.assertTrue(bubble._auto_hide_timer.isActive())
        bubble.copy_answer()
        clipboard = QApplication.clipboard()
        self.assertIn("正文", clipboard.text())
        bubble.close_bubble()
        self.assertFalse(bubble._auto_hide_timer.isActive())
        bubble.deleteLater()

    def test_bubble_viewport_activity_restarts_auto_hide(self) -> None:
        bubble = AssistantBubble()
        bubble.set_auto_hide_seconds(5)
        bubble.begin_stream()
        bubble.append_markdown("正文")
        bubble.show_near(QRect(100, 100, 96, 96))
        bubble.show_result()
        bubble._auto_hide_timer.stop()

        bubble.answer.activity.emit()
        self.assertTrue(bubble._auto_hide_timer.isActive())
        bubble._auto_hide_timer.stop()
        bubble.answer.selectAll()
        self.assertTrue(bubble._auto_hide_timer.isActive())
        bubble.close_bubble()
        bubble.deleteLater()

    def test_position_clamping_works_for_primary_and_secondary_rects(
        self,
    ) -> None:
        primary = QRect(0, 0, 1920, 1080)
        secondary = QRect(1920, 0, 2560, 1440)
        for screen_rect in (primary, secondary):
            clamped = _clamp_rect(
                QRect(screen_rect.x() - 800, screen_rect.y() + 300, 520, 380),
                screen_rect,
            )
            self.assertTrue(screen_rect.contains(clamped))

    def test_input_bar_temporarily_replaces_persistent_ball(self) -> None:
        controller = AssistantController()
        controller.configure(
            AppConfig(assistant_ball_persistent=True),
            "",
        )
        controller.activate()
        controller.show_input()
        self.app.processEvents()
        self.assertTrue(controller.input_bar.isVisible())
        self.assertFalse(controller.ball.isVisible())
        controller.input_bar.dismiss()
        self.app.processEvents()
        self.assertTrue(controller.ball.isVisible())
        controller.shutdown()
        controller.deleteLater()

    def test_summon_emits_auto_listen_only_after_consent(self) -> None:
        controller = AssistantController()
        requests: list[bool] = []
        controller.auto_listen_requested.connect(
            lambda: requests.append(True)
        )
        controller.configure(
            AppConfig(
                voice_enabled=True,
                voice_auto_listen=True,
                voice_consent_version=0,
            ),
            "",
        )
        controller.activate()
        controller.show_input()
        self.assertEqual(requests, [])
        controller.input_bar.dismiss()
        controller.configure(
            AppConfig(
                voice_enabled=True,
                voice_auto_listen=True,
                voice_consent_version=1,
            ),
            "",
        )
        controller.show_input()
        self.assertEqual(requests, [True])
        controller.input_bar.dismiss()
        controller.shutdown()
        controller.deleteLater()

    def test_hotkey_only_mode_hides_ball_after_input_dismissal(self) -> None:
        controller = AssistantController()
        controller.configure(
            AppConfig(assistant_ball_persistent=False),
            "",
        )
        controller.activate()
        self.assertFalse(controller.ball.isVisible())
        controller.show_input()
        self.app.processEvents()
        self.assertTrue(controller.input_bar.isVisible())
        self.assertFalse(controller.ball.isVisible())
        controller.input_bar.dismiss()
        self.app.processEvents()
        self.assertFalse(controller.ball.isVisible())
        controller.shutdown()
        controller.deleteLater()

    def test_manual_hidden_ball_still_accepts_input_and_resets_on_mode_restart(
        self,
    ) -> None:
        controller = AssistantController()
        controller.configure(
            AppConfig(assistant_ball_persistent=True),
            "",
        )
        controller.activate()
        controller.set_ball_visible(False)
        QTest.qWait(DEFAULT_FADE_MS + 80)
        self.assertFalse(controller.ball.isVisible())
        controller.show_input()
        self.app.processEvents()
        self.assertTrue(controller.input_bar.isVisible())
        self.assertFalse(controller.ball.isVisible())
        controller.input_bar.dismiss()
        self.app.processEvents()
        self.assertFalse(controller.ball.isVisible())

        controller.deactivate()
        controller.activate()
        self.app.processEvents()
        self.assertIsNone(controller.manual_ball_visible)
        self.assertTrue(controller.ball.isVisible())
        controller.shutdown()
        controller.deleteLater()

    def test_returning_to_assistant_mode_resets_manual_visibility(self) -> None:
        assistant = AssistantController()
        assistant.configure(
            AppConfig(assistant_ball_persistent=True),
            "",
        )
        assistant_mode = create_work_mode(
            "global_assistant",
            assistant=assistant,
        )
        quiz_mode = create_work_mode("quiz")
        coordinator = ModeCoordinator(assistant_mode)
        coordinator.activate()
        assistant.set_ball_visible(False)
        QTest.qWait(DEFAULT_FADE_MS + 80)
        self.assertFalse(assistant.ball.isVisible())

        coordinator.transition_to(quiz_mode, cancel_request=False)
        coordinator.transition_to(assistant_mode, cancel_request=False)
        self.app.processEvents()
        self.assertIsNone(assistant.manual_ball_visible)
        self.assertTrue(assistant.ball.isVisible())
        assistant.shutdown()
        assistant.deleteLater()

    def test_mode_deactivation_cancels_active_voice_capture(self) -> None:
        assistant = AssistantController()
        assistant.configure(AppConfig(voice_enabled=True), "")
        with patch.object(
            VoiceController,
            "listening",
            new_callable=PropertyMock,
            return_value=True,
        ), patch.object(
            assistant.voice,
            "cancel",
        ) as cancel:
            assistant.deactivate(cancel_request=False)
        cancel.assert_called_once_with()
        assistant.shutdown()
        assistant.deleteLater()

    def test_input_and_bubble_scale_reasonably_with_large_ball(self) -> None:
        ball = AssistantBall()
        ball.set_ball_size(160)
        anchor = QRect(200, 200, ball.width(), ball.height())
        screen = self.app.primaryScreen().availableGeometry()

        bar = AssistantInputBar()
        bar.show_focused(anchor)
        QTest.qWait(220)
        self.assertEqual(bar.width(), 600)
        self.assertTrue(screen.contains(bar.geometry()))

        bubble = AssistantBubble()
        bubble.show_near(anchor)
        self.assertEqual(bubble.width(), 600)
        self.assertEqual(bubble.height(), 440)
        self.assertTrue(screen.contains(bubble.geometry()))
        bar.close()
        bubble.close()
        ball.deleteLater()

    def test_tray_ball_action_is_mode_controlled(self) -> None:
        tray = TrayController()
        emitted: list[bool] = []
        tray.ball_visibility_requested.connect(
            lambda: emitted.append(True)
        )
        tray.set_ball_visibility_enabled(False)
        tray.ball_visibility_action.trigger()
        self.assertEqual(emitted, [])
        tray.set_ball_visibility_enabled(True)
        tray.ball_visibility_action.trigger()
        self.assertEqual(emitted, [True])
        tray.deleteLater()

    def test_capture_restore_preserves_visible_ball(self) -> None:
        controller = AssistantController()
        controller.configure(
            AppConfig(assistant_ball_persistent=True),
            "",
        )
        controller.activate()
        snapshot = controller.capture_visibility_snapshot()
        self.assertTrue(snapshot.ball_visible)
        controller.hide_all_for_screen_capture()
        self.assertFalse(controller.ball.isVisible())
        controller.restore_visibility_snapshot(snapshot)
        self.app.processEvents()
        self.assertTrue(controller.ball.isVisible())
        controller.shutdown()
        controller.deleteLater()

    def test_capture_restore_preserves_manually_hidden_ball(self) -> None:
        controller = AssistantController()
        controller.configure(
            AppConfig(assistant_ball_persistent=True),
            "",
        )
        controller.activate()
        controller.set_ball_visible(False)
        QTest.qWait(DEFAULT_FADE_MS + 80)
        snapshot = controller.capture_visibility_snapshot()
        self.assertFalse(snapshot.ball_visible)
        self.assertFalse(snapshot.ball_should_show)
        controller.hide_all_for_screen_capture()
        controller.restore_visibility_snapshot(snapshot)
        self.assertFalse(controller.ball.isVisible())
        controller.shutdown()
        controller.deleteLater()

    def test_capture_restore_preserves_input_open_ball_state(self) -> None:
        controller = AssistantController()
        controller.configure(
            AppConfig(assistant_ball_persistent=True),
            "",
        )
        controller.activate()
        controller.show_input()
        self.app.processEvents()
        snapshot = controller.capture_visibility_snapshot()
        self.assertTrue(snapshot.input_visible)
        self.assertFalse(snapshot.ball_visible)
        self.assertTrue(snapshot.ball_should_show)
        controller.hide_all_for_screen_capture()
        self.assertFalse(controller.input_bar.isVisible())
        controller.restore_visibility_snapshot(snapshot)
        self.app.processEvents()
        self.assertTrue(controller.input_bar.isVisible())
        self.assertFalse(controller.ball.isVisible())
        controller.shutdown()
        controller.deleteLater()

    def test_preview_at_160_fits_screen_and_restores_input_focus(self) -> None:
        controller = AssistantController()
        controller.configure(
            AppConfig(
                work_mode="global_assistant",
                assistant_ball_size=160,
                assistant_ball_persistent=True,
            ),
            "",
        )
        controller.activate()
        controller.show_input()
        self.app.processEvents()
        snapshot = controller.capture_visibility_snapshot()
        controller.hide_all_for_screen_capture()
        controller.restore_visibility_snapshot(snapshot)

        image = QImage(1024, 768, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.darkCyan)
        preview = ScreenRecognitionPreview()
        preview.show_for(
            image,
            "请描述当前画面。",
            snapshot.anchor,
        )
        QTest.qWait(120)
        screen = self.app.primaryScreen().availableGeometry()
        self.assertTrue(screen.contains(preview.geometry()))
        self.assertTrue(preview.prompt.hasFocus())
        preview.cancel()
        controller.restore_primary_input_focus()
        QTest.qWait(80)
        self.assertTrue(controller.input_bar.input.hasFocus())
        controller.shutdown()
        controller.deleteLater()
        preview.deleteLater()

    def test_preview_voice_listening_and_prompt_append(self) -> None:
        preview = ScreenRecognitionPreview()
        image = QImage(640, 360, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.darkBlue)
        preview.show_for(image, "已有提示", QRect(300, 260, 96, 96))
        preview.set_listening(True)
        self.assertTrue(preview.listening_label.isVisibleTo(preview))
        self.assertFalse(preview.send_button.isEnabled())
        preview.append_transcript("用语音补充条件")
        self.assertIn("已有提示", preview.prompt.toPlainText())
        self.assertIn("用语音补充条件", preview.prompt.toPlainText())
        preview.voice_cancel_requested.emit()
        preview.set_listening(False)
        self.assertTrue(preview.send_button.isEnabled())
        preview.cancel()
        preview.deleteLater()

    def test_ball_position_clamps_on_primary_and_secondary_screens(
        self,
    ) -> None:
        primary = QRect(0, 0, 1920, 1080)
        secondary = QRect(1920, 0, 2560, 1440)
        for screen_rect in (primary, secondary):
            clamped = _clamp_ball_position(
                AssistantBallPosition(
                    screen_rect.right() + 500,
                    screen_rect.bottom() + 500,
                ),
                96,
                96,
                screen_rect,
            )
            self.assertTrue(screen_rect.contains(clamped))
            self.assertLessEqual(
                clamped.x() + 96,
                screen_rect.right() + 1,
            )
            self.assertLessEqual(
                clamped.y() + 96,
                screen_rect.bottom() + 1,
            )


if __name__ == "__main__":
    unittest.main()
