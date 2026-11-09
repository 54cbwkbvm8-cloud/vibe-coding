"""Qt thread lifecycle for microphone capture and offline transcription."""

from __future__ import annotations

from dataclasses import dataclass
import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot

from .services.voice_audio import (
    VoiceAudioError,
    VoiceCaptureResult,
    VoiceRecordingCancelled,
    play_start_tone,
    record_once,
    transcribe_pcm,
)
from .services.voice_models import validate_model_directory


@dataclass(frozen=True)
class VoiceSettings:
    microphone_device: str
    language: str
    silence_seconds: float
    max_record_seconds: int
    start_tone_enabled: bool


class VoiceWorker(QObject):
    level_changed = Signal(int)
    finished = Signal(str)
    cancelled = Signal()
    failed = Signal(str)
    microphone_released = Signal()
    completed = Signal()

    def __init__(
        self,
        settings: VoiceSettings,
        stop_event: threading.Event,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._stop_event = stop_event
        self._cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        released = False
        try:
            valid, message = validate_model_directory()
            if not valid:
                raise VoiceAudioError(
                    f"{message}。请先在“识别与语音”中安装模型。"
                )
            result = record_once(
                device_name=self._settings.microphone_device,
                silence_seconds=self._settings.silence_seconds,
                max_seconds=self._settings.max_record_seconds,
                stop_event=self._stop_event,
                cancel_event=self._cancel_event,
                level_callback=self.level_changed.emit,
            )
            self.microphone_released.emit()
            released = True
            self._transcribe(result)
        except VoiceRecordingCancelled:
            if not released:
                self.microphone_released.emit()
            self.cancelled.emit()
        except VoiceAudioError as exc:
            if not released:
                self.microphone_released.emit()
            self.failed.emit(str(exc))
        except Exception as exc:
            if not released:
                self.microphone_released.emit()
            self.failed.emit(f"语音处理失败：{exc}")
        finally:
            self.completed.emit()

    def _transcribe(self, result: VoiceCaptureResult) -> None:
        if self._cancel_event.is_set():
            self.cancelled.emit()
            return
        if not result.speech_detected:
            self.failed.emit("没有检测到说话声，请靠近麦克风后重试。")
            return
        text = transcribe_pcm(result.pcm, self._settings.language)
        if self._cancel_event.is_set():
            self.cancelled.emit()
            return
        self.finished.emit(text)


class VoiceController(QObject):
    listening_started = Signal()
    listening_finished = Signal(str)
    listening_cancelled = Signal()
    listening_failed = Signal(str)
    level_changed = Signal(int)
    microphone_released = Signal()
    idle = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: VoiceWorker | None = None
        self._stop_event = threading.Event()
        self._cancel_event = threading.Event()

    @property
    def listening(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, settings: VoiceSettings) -> bool:
        if self.listening:
            return False
        self._stop_event = threading.Event()
        self._cancel_event = threading.Event()
        self._thread = QThread(self)
        self._worker = VoiceWorker(
            settings,
            self._stop_event,
            self._cancel_event,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.level_changed.connect(self.level_changed.emit)
        self._worker.finished.connect(self.listening_finished.emit)
        self._worker.cancelled.connect(self.listening_cancelled.emit)
        self._worker.failed.connect(self.listening_failed.emit)
        self._worker.microphone_released.connect(
            self.microphone_released.emit
        )
        self._worker.completed.connect(self._thread.quit)
        self._worker.completed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        if settings.start_tone_enabled:
            play_start_tone()
        self._thread.start()
        self.listening_started.emit()
        return True

    def stop(self) -> None:
        if self.listening:
            self._stop_event.set()

    def cancel(self) -> None:
        if self.listening:
            self._cancel_event.set()
            self._stop_event.set()

    def shutdown(self) -> None:
        if not self.listening:
            return
        self.cancel()
        thread = self._thread
        if thread is not None:
            thread.quit()
            thread.wait(2500)
        self._thread = None
        self._worker = None

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self.idle.emit()
