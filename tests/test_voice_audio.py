"""Synthetic-audio tests for capture boundaries and offline transcription."""

from array import array
from pathlib import Path
import socket
import sys
import threading
import unittest
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.services.voice_audio import (  # noqa: E402
    FRAME_BYTES,
    FRAME_SAMPLES,
    VoiceAudioError,
    VoiceRecordingCancelled,
    friendly_audio_error,
    pcm_level,
    record_once,
    transcribe_pcm,
)
from ai_quiz_overlay.ui.assistant_surfaces import AssistantInputBar  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def speech_frame(value: int = 1000) -> bytes:
    samples = array("h", [value] * FRAME_SAMPLES)
    return samples.tobytes()


def silence_frame() -> bytes:
    return bytes(FRAME_BYTES)


class FakeVad:
    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        return any(frame)


class FakeStream:
    def __init__(self, frames: list[bytes]) -> None:
        self._frames = iter(frames)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self, _frames: int) -> bytes:
        try:
            return next(self._frames)
        except StopIteration:
            return silence_frame()


class FakeResult:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeRecognitionStream:
    def __init__(self) -> None:
        self.result = FakeResult(
            "<|zh|><|NEUTRAL|><|Speech|><|woitn|>请解释这段代码"
        )
        self.samples = None

    def accept_waveform(self, sample_rate: int, samples) -> None:
        self.sample_rate = sample_rate
        self.samples = samples

    def decode(self) -> None:
        return None


class FakeRecognizer:
    def __init__(self) -> None:
        self.stream = FakeRecognitionStream()

    def create_stream(self):
        return self.stream

    def decode_stream(self, stream) -> None:
        if stream is not self.stream:
            raise AssertionError("Unexpected stream")


class VoiceAudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_level_uses_short_pcm_without_extra_dependencies(self) -> None:
        self.assertEqual(pcm_level(b""), 0)
        self.assertGreater(pcm_level(speech_frame()), 0)

    def test_silence_stops_after_speech(self) -> None:
        silence_count = 40
        frames = [speech_frame()] + [silence_frame()] * silence_count
        levels: list[int] = []
        result = record_once(
            device_name="",
            silence_seconds=1.2,
            max_seconds=30,
            stop_event=threading.Event(),
            cancel_event=threading.Event(),
            level_callback=levels.append,
            stream_factory=lambda: FakeStream(frames),
            vad_factory=FakeVad,
        )
        self.assertTrue(result.speech_detected)
        self.assertTrue(result.stopped_by_silence)
        self.assertEqual(result.duration_seconds, 1.23)
        self.assertEqual(len(levels), len(frames))

    def test_manual_stop_finishes_without_waiting_for_silence(self) -> None:
        stop = threading.Event()
        stream = FakeStream([speech_frame()] * 20)

        class StoppingStream(FakeStream):
            def read(self, frames: int) -> bytes:
                value = super().read(frames)
                stop.set()
                return value

        result = record_once(
            device_name="",
            silence_seconds=1.2,
            max_seconds=30,
            stop_event=stop,
            cancel_event=threading.Event(),
            stream_factory=lambda: StoppingStream([speech_frame()] * 20),
            vad_factory=FakeVad,
        )
        self.assertEqual(result.duration_seconds, 0.03)

    def test_cancel_discards_recording(self) -> None:
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(VoiceRecordingCancelled):
            record_once(
                device_name="",
                silence_seconds=1.2,
                max_seconds=30,
                stop_event=threading.Event(),
                cancel_event=cancel,
                stream_factory=lambda: FakeStream([speech_frame()]),
                vad_factory=FakeVad,
            )

    def test_max_duration_caps_capture(self) -> None:
        result = record_once(
            device_name="",
            silence_seconds=5.0,
            max_seconds=5,
            stop_event=threading.Event(),
            cancel_event=threading.Event(),
            stream_factory=lambda: FakeStream(
                [speech_frame()] * 200
            ),
            vad_factory=FakeVad,
        )
        self.assertLessEqual(result.duration_seconds, 5.0)
        self.assertGreaterEqual(result.duration_seconds, 4.95)

    def test_offline_transcription_never_opens_network(self) -> None:
        recognizer = FakeRecognizer()
        original_connect = socket.socket.connect

        def forbidden_connect(*args, **kwargs):
            raise AssertionError("Network access is forbidden")

        with mock.patch.object(
            socket.socket,
            "connect",
            forbidden_connect,
        ):
            text = transcribe_pcm(
                speech_frame(),
                "offline-test",
                recognizer_loader=lambda _language: recognizer,
            )
        self.assertEqual(text, "请解释这段代码")
        self.assertEqual(recognizer.stream.sample_rate, 16000)
        socket.socket.connect = original_connect

    def test_empty_audio_is_rejected(self) -> None:
        with self.assertRaises(VoiceAudioError):
            transcribe_pcm(b"", "zh")

    def test_audio_errors_have_actionable_chinese_messages(self) -> None:
        self.assertIn(
            "Windows",
            friendly_audio_error(RuntimeError("permission denied")),
        )
        self.assertIn(
            "占用",
            friendly_audio_error(RuntimeError("device busy")),
        )
        self.assertIn(
            "未检测到",
            friendly_audio_error(
                RuntimeError("No default input device available")
            ),
        )

    def test_offline_record_transcribe_and_append_pipeline(self) -> None:
        capture = record_once(
            device_name="",
            silence_seconds=0.3,
            max_seconds=5,
            stop_event=threading.Event(),
            cancel_event=threading.Event(),
            stream_factory=lambda: FakeStream(
                [speech_frame()] + [silence_frame()] * 10
            ),
            vad_factory=FakeVad,
        )
        recognizer = FakeRecognizer()
        with mock.patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("Network access is forbidden"),
        ):
            transcript = transcribe_pcm(
                capture.pcm,
                "offline-pipeline",
                recognizer_loader=lambda _language: recognizer,
            )
        bar = AssistantInputBar()
        bar.input.setText("用户已输入")
        bar.append_transcript(transcript)
        self.assertEqual(
            bar.input.text(),
            "用户已输入 请解释这段代码",
        )
        bar.deleteLater()


if __name__ == "__main__":
    unittest.main()
