"""Qt signal tests for offline voice capture."""

from pathlib import Path
import sys
import threading
import unittest
from unittest import mock

from PySide6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.services.voice_audio import VoiceCaptureResult  # noqa: E402
from ai_quiz_overlay.voice_controller import (  # noqa: E402
    VoiceSettings,
    VoiceWorker,
)


class VoiceControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_worker_emits_transcript_and_release(self) -> None:
        finished: list[str] = []
        released: list[bool] = []
        completed: list[bool] = []
        worker = VoiceWorker(
            VoiceSettings(
                microphone_device="",
                language="zh",
                silence_seconds=1.2,
                max_record_seconds=30,
                start_tone_enabled=False,
            ),
            threading.Event(),
            threading.Event(),
        )
        worker.finished.connect(finished.append)
        worker.microphone_released.connect(
            lambda: released.append(True)
        )
        worker.completed.connect(lambda: completed.append(True))
        with (
            mock.patch(
                "ai_quiz_overlay.voice_controller.validate_model_directory",
                return_value=(True, "ok"),
            ),
            mock.patch(
                "ai_quiz_overlay.voice_controller.record_once",
                return_value=VoiceCaptureResult(
                    pcm=b"\x00\x00",
                    duration_seconds=0.03,
                    speech_detected=True,
                    stopped_by_silence=False,
                ),
            ),
            mock.patch(
                "ai_quiz_overlay.voice_controller.transcribe_pcm",
                return_value="测试转写",
            ),
        ):
            worker.run()
        self.assertEqual(finished, ["测试转写"])
        self.assertEqual(released, [True])
        self.assertEqual(completed, [True])
        worker.deleteLater()


if __name__ == "__main__":
    unittest.main()
