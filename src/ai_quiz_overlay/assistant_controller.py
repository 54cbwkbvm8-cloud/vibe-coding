"""Runtime controller for the text-only global assistant mode."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import (
    QObject,
    QPoint,
    QRect,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QCursor, QGuiApplication, QImage

from .config import AppConfig, AssistantBallPosition
from .services.chat_provider import ChatRequest, ProviderUnavailableError
from .services.chat_session import ASSISTANT_SYSTEM_PROMPT, ChatSession
from .services.image_payload import ImagePayloadError, image_to_data_url
from .services.provider_registry import create_chat_provider
from .services.provider_worker import ProviderChatWorker
from .ui.assistant_ball import AssistantBall
from .ui.assistant_surfaces import AssistantBubble, AssistantInputBar
from .voice_controller import VoiceController, VoiceSettings
from .personalization_runtime import BrandRuntime


@dataclass(frozen=True)
class AssistantVisibilitySnapshot:
    input_visible: bool
    bubble_visible: bool
    ball_visible: bool
    ball_should_show: bool
    anchor: QRect


def _clamp_ball_position(
    position: AssistantBallPosition,
    width: int,
    height: int,
    screen_rect: QRect,
) -> QPoint:
    x = max(
        screen_rect.left(),
        min(screen_rect.right() - width + 1, position.x),
    )
    y = max(
        screen_rect.top(),
        min(screen_rect.bottom() - height + 1, position.y),
    )
    return QPoint(x, y)


class AssistantController(QObject):
    position_changed = Signal(QPoint)
    settings_requested = Signal()
    exit_requested = Signal()
    auto_listen_requested = Signal()
    voice_input_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.ball = AssistantBall()
        self.input_bar = AssistantInputBar()
        self.bubble = AssistantBubble()
        self.voice = VoiceController(self)
        self._session = ChatSession(ASSISTANT_SYSTEM_PROMPT)
        self._config = AppConfig()
        self._api_key = ""
        self._thread: QThread | None = None
        self._worker: ProviderChatWorker | None = None
        self._stream_kind = ""
        self._stream_message = ""
        self._after_stop_callback = None
        self._mode_active = False
        self._manual_ball_visible: bool | None = None
        self._voice_context = ""
        self._suppress_auto_listen = False
        self._pending_voice_auto_send = False

        self.ball.activated.connect(self.show_input)
        self.ball.new_conversation_requested.connect(
            self.start_new_conversation
        )
        self.ball.settings_requested.connect(self.settings_requested.emit)
        self.ball.hide_requested.connect(self.hide_ball)
        self.ball.position_changed.connect(self._position_updated)
        self.input_bar.send_requested.connect(self.send)
        self.input_bar.stop_requested.connect(self.stop_generation)
        self.input_bar.dismissed.connect(self._input_dismissed)
        self.input_bar.microphone_requested.connect(
            self.voice_input_requested.emit
        )
        self.bubble.closed.connect(self._bubble_closed)
        self.bubble.new_conversation_requested.connect(
            self.start_new_conversation
        )
        self.bubble.stop_requested.connect(self.stop_generation)
        self.voice.listening_started.connect(self._voice_started)
        self.voice.listening_finished.connect(self._voice_finished)
        self.voice.listening_cancelled.connect(self._voice_cancelled)
        self.voice.listening_failed.connect(self._voice_failed)
        self.voice.level_changed.connect(self._voice_level_changed)
        self.voice.idle.connect(self._voice_idle)

    @property
    def is_busy(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    @property
    def is_listening(self) -> bool:
        return self.voice.listening

    @property
    def mode_active(self) -> bool:
        return self._mode_active

    @property
    def manual_ball_visible(self) -> bool | None:
        return self._manual_ball_visible

    def should_show_ball(self) -> bool:
        if self._manual_ball_visible is not None:
            return self._manual_ball_visible
        return self._config.assistant_ball_persistent

    def apply_brand(self, runtime: BrandRuntime) -> None:
        self.ball.apply_brand(runtime)
        self.input_bar.apply_brand(runtime)
        self.bubble.apply_brand(runtime)

    def configure(self, config: AppConfig, api_key: str | None) -> None:
        persistent_changed = (
            config.assistant_ball_persistent
            != self._config.assistant_ball_persistent
        )
        self._config = config
        self._api_key = api_key or ""
        self.ball.set_ball_size(config.assistant_ball_size)
        self.input_bar.set_opacity(config.opacity)
        self.bubble.set_opacity(config.opacity)
        self.bubble.set_auto_hide_seconds(config.assistant_auto_hide_seconds)
        if persistent_changed:
            self._manual_ball_visible = None
        if config.assistant_ball_position is not None:
            self.restore_ball_position(config.assistant_ball_position)
        if self._mode_active:
            self._apply_ball_visibility(animated=False)

    def activate(self) -> None:
        self._mode_active = True
        self._manual_ball_visible = None
        self._apply_ball_visibility(animated=False)

    def deactivate(self, cancel_request: bool = True) -> None:
        self._pending_voice_auto_send = False
        self.cancel_voice_listening()
        if cancel_request and self.is_busy and self._worker is not None:
            self._worker.request_stop()
        self._mode_active = False
        self._manual_ball_visible = None
        self.input_bar.hide()
        self.bubble.clear_conversation()
        self.ball.hide()

    def shutdown(self) -> None:
        self.voice.shutdown()
        if self._worker is not None:
            self._worker.request_stop()
        self._mode_active = False
        self.input_bar.close()
        self.bubble.close()
        self.ball.close()

    @Slot()
    def show_ball(self) -> None:
        if not self.ball.isVisible():
            self._position_default_if_needed()
        self.ball.show_without_activation()

    def hide_ball(self) -> None:
        self.set_ball_visible(False)

    def toggle_ball_visibility(self) -> None:
        if not self._mode_active:
            return
        self.set_ball_visible(not self.should_show_ball())

    def set_ball_visible(self, visible: bool) -> None:
        self._manual_ball_visible = bool(visible)
        self._apply_ball_visibility(animated=True)

    def preview_ball_size(self, size: int) -> None:
        self.ball.set_ball_size(size)
        if not self.ball.isVisible():
            self._position_default_if_needed()
        self.ball.show_without_activation()

    def restore_configured_ball_size(self) -> None:
        self.ball.set_ball_size(self._config.assistant_ball_size)
        if self._config.assistant_ball_position is not None:
            self.restore_ball_position(self._config.assistant_ball_position)

    def capture_visibility_snapshot(self) -> AssistantVisibilitySnapshot:
        return AssistantVisibilitySnapshot(
            input_visible=self.input_bar.isVisible(),
            bubble_visible=self.bubble.isVisible(),
            ball_visible=self.ball.isVisible(),
            ball_should_show=self.should_show_ball(),
            anchor=QRect(self.ball.geometry()),
        )

    def hide_all_for_screen_capture(self) -> None:
        self.input_bar.hide()
        self.bubble.hide()
        self.ball.hide()

    def restore_visibility_snapshot(
        self,
        snapshot: AssistantVisibilitySnapshot,
    ) -> None:
        if snapshot.bubble_visible:
            self.bubble.show_near(snapshot.anchor)
        if snapshot.input_visible:
            self.input_bar.show_focused(snapshot.anchor)
            return
        if snapshot.ball_visible:
            self.ball.move(snapshot.anchor.topLeft())
            self.ball.show_without_activation()

    def prepare_screen_recognition_result(
        self,
        snapshot: AssistantVisibilitySnapshot,
    ) -> None:
        self.input_bar.hide()
        self.ball.move(snapshot.anchor.topLeft())
        if self.should_show_ball():
            self.ball.show_without_activation()
        else:
            self.ball.hide()

    def restore_primary_input_focus(self) -> None:
        if self.input_bar.isVisible():
            self.input_bar.restore_focus()

    def show_notice(self, message: str) -> None:
        self._show_error(message)

    @Slot()
    def show_input(self) -> None:
        if not self.ball.isVisible():
            self._position_default_if_needed()
        anchor = self.ball.geometry()
        if self.should_show_ball():
            self.show_ball()
        self.input_bar.show_focused(anchor)
        if self.input_bar.isVisible() and self.ball.isVisible():
            self.ball.hide()
        if (
            self._config.voice_enabled
            and self._config.voice_auto_listen
            and self._config.voice_consent_version >= 1
            and not self._suppress_auto_listen
        ):
            self.auto_listen_requested.emit()

    def toggle_input(self) -> None:
        if self.input_bar.isVisible():
            self.input_bar.dismiss()
        else:
            self.show_input()

    @Slot(str)
    def send(self, question: str) -> None:
        self._send_request(question)

    def send_screen_recognition(
        self,
        image: QImage,
        prompt: str,
    ) -> bool:
        return self._send_request(
            prompt,
            image=image,
            status_text="正在识别当前屏幕",
        )

    def _send_request(
        self,
        question: str,
        *,
        image: QImage | None = None,
        status_text: str = "",
    ) -> bool:
        if self.is_busy or not question.strip():
            return False
        if self.is_listening:
            self._show_error("请先结束或取消本次语音输入。")
            return False
        if not self._api_key:
            self._show_error("尚未配置 API Key，请先在设置中填写并保存。")
            return False
        try:
            provider = create_chat_provider(self._config.access_method)
            image_data_url = None
            if image is not None:
                model_error = provider.image_support_error(
                    self._config.model
                )
                if model_error:
                    raise ValueError(model_error)
                image_data_url = image_to_data_url(
                    image,
                    max_edge=(
                        self._config.screen_recognition_image_max_edge
                    ),
                )
            messages = self._session.begin_turn(
                question,
                image_data_url=image_data_url,
            )
        except (
            ImagePayloadError,
            ProviderUnavailableError,
            RuntimeError,
            ValueError,
        ) as exc:
            self._show_error(str(exc))
            return False

        self.input_bar.input.clear()
        self.input_bar.hide()
        self.input_bar.set_busy(True)
        if self.should_show_ball():
            self.show_ball()
        self.bubble.begin_stream(status_text)
        self.bubble.show_near(self.ball.geometry())
        self.ball.set_state("thinking")
        self._stream_kind = ""
        self._stream_message = ""

        self._thread = QThread(self)
        self._worker = ProviderChatWorker(
            provider,
            ChatRequest(
                config=self._config,
                credential=self._api_key,
                messages=messages,
            ),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.chunk_ready.connect(self._chunk_received)
        self._worker.completed.connect(self._remember_completed)
        self._worker.cancelled.connect(self._remember_cancelled)
        self._worker.failed.connect(self._remember_failed)
        self._worker.completed.connect(self._worker.deleteLater)
        self._worker.cancelled.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._worker.completed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        self._thread.start()
        return True

    @Slot()
    def stop_generation(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
            self.bubble.stop_button.setEnabled(False)

    def stop_request_then(self, callback) -> None:
        if not self.is_busy:
            QTimer.singleShot(0, callback)
            return
        self._after_stop_callback = callback
        self.stop_generation()

    @Slot()
    def start_new_conversation(self) -> None:
        if self.is_busy or self.is_listening:
            return
        self._session.clear()
        self.bubble.clear_conversation()
        self.show_input()

    def move_ball(self, point: QPoint) -> None:
        self.ball.move(point)

    def current_ball_position(self) -> AssistantBallPosition:
        return AssistantBallPosition(self.ball.x(), self.ball.y())

    def restore_ball_position(self, position: AssistantBallPosition) -> None:
        center = QPoint(
            position.x + self.ball.width() // 2,
            position.y + self.ball.height() // 2,
        )
        screen = QGuiApplication.screenAt(center)
        screen = screen or QGuiApplication.primaryScreen()
        if screen is None:
            return
        clamped = _clamp_ball_position(
            position,
            self.ball.width(),
            self.ball.height(),
            screen.availableGeometry(),
        )
        self.ball.move(clamped)

    @Slot(str)
    def _chunk_received(self, chunk: str) -> None:
        self.ball.set_state("responding")
        self.bubble.append_markdown(chunk)

    @Slot(str)
    def _remember_completed(self, answer: str) -> None:
        self._stream_kind = "completed"
        self._stream_message = answer

    @Slot(str)
    def _remember_cancelled(self, partial_answer: str) -> None:
        self._stream_kind = "cancelled"
        self._stream_message = partial_answer

    @Slot(str)
    def _remember_failed(self, message: str) -> None:
        self._stream_kind = "failed"
        self._stream_message = message

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self.input_bar.set_busy(False)
        self.ball.set_state("idle")
        if self._stream_kind == "completed":
            self._session.complete_turn(self._stream_message)
            self.bubble.show_result()
        elif self._stream_kind == "cancelled":
            self._session.cancel_turn()
            self.bubble.show_result("已停止生成")
        else:
            self._session.cancel_turn()
            self.bubble.show_result(self._stream_message, error=True)
        callback = self._after_stop_callback
        self._after_stop_callback = None
        if callback is not None:
            QTimer.singleShot(0, callback)

    def _show_error(self, message: str) -> None:
        if not self.ball.isVisible():
            self._position_default_if_needed()
        anchor = QRect(self.ball.geometry())
        if self.should_show_ball():
            self.show_ball()
        if self.input_bar.isVisible():
            self.ball.hide()
        self.bubble.begin_stream()
        self.bubble.show_near(anchor)
        self.bubble.show_result(message, error=True)

    def start_voice_listening(self, context: str = "input") -> bool:
        if self.is_busy or self.is_listening:
            self._show_error("当前正在回答或聆听，请稍后再试。")
            return False
        if not self._config.voice_enabled:
            self._show_error("语音功能尚未启用，请先在设置中开启。")
            return False
        if self._config.voice_consent_version < 1:
            self._show_error("请先确认麦克风隐私说明。")
            return False
        if context == "input":
            if not self.input_bar.isVisible():
                self._suppress_auto_listen = True
                self.show_input()
                self._suppress_auto_listen = False
            if not self.input_bar.isVisible():
                return False
            self.input_bar.set_listening(True)
        self._voice_context = context
        started = self.voice.start(
            VoiceSettings(
                microphone_device=self._config.voice_microphone_device,
                language=self._config.voice_language,
                silence_seconds=self._config.voice_silence_seconds,
                max_record_seconds=self._config.voice_max_record_seconds,
                start_tone_enabled=self._config.voice_start_tone_enabled,
            )
        )
        if not started:
            self._reset_voice_ui()
            self._show_error("无法启动新的语音识别任务。")
        return started

    @Slot()
    def toggle_voice_input(self) -> None:
        if self.is_listening:
            self.stop_voice_listening()
        else:
            self.start_voice_listening("input")

    def stop_voice_listening(self) -> None:
        self.voice.stop()

    def cancel_voice_listening(self) -> None:
        self._pending_voice_auto_send = False
        if not self.voice.listening:
            return
        self.voice.cancel()
        self._reset_voice_ui()

    @Slot()
    def _voice_started(self) -> None:
        self.ball.set_state("listening")
        if self.input_bar.isVisible():
            self.input_bar.set_listening(True)
            self.input_bar.send_button.setEnabled(False)

    @Slot(str)
    def _voice_finished(self, transcript: str) -> None:
        context = self._voice_context
        self._voice_context = ""
        self._reset_voice_ui()
        if context == "preview":
            return
        self.input_bar.append_transcript(transcript)
        self.input_bar.send_button.setEnabled(True)
        if self._config.voice_auto_send:
            self._pending_voice_auto_send = True

    @Slot()
    def _voice_cancelled(self) -> None:
        self._pending_voice_auto_send = False
        self._voice_context = ""
        self._reset_voice_ui()

    @Slot(str)
    def _voice_failed(self, message: str) -> None:
        self._pending_voice_auto_send = False
        self._voice_context = ""
        self._reset_voice_ui()
        self._show_error(message)

    @Slot()
    def _voice_idle(self) -> None:
        if not self._pending_voice_auto_send:
            return
        self._pending_voice_auto_send = False
        self._emit_current_input()

    @Slot(int)
    def _voice_level_changed(self, level: int) -> None:
        self.input_bar.set_voice_level(level)
        self.ball.set_voice_level(level)

    def _reset_voice_ui(self) -> None:
        self.input_bar.set_listening(False)
        self.input_bar.send_button.setEnabled(True)
        self.ball.set_voice_level(0)
        if self.ball.state == "listening":
            self.ball.set_state("idle")

    def _emit_current_input(self) -> None:
        text = self.input_bar.input.text().strip()
        if text:
            self.send(text)

    def _show_result(self, message: str, error: bool = False) -> None:
        self.bubble.show_result(message, error=error)

    def _position_updated(self, point: QPoint) -> None:
        self.position_changed.emit(point)

    def _position_default_if_needed(self) -> None:
        if self._config.assistant_ball_position is not None:
            self.restore_ball_position(self._config.assistant_ball_position)
            return
        screen = QGuiApplication.screenAt(QCursor.pos())
        screen = screen or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.ball.move(
            area.right() - self.ball.width() - 20,
            area.center().y() - self.ball.height() // 2,
        )

    def _input_dismissed(self) -> None:
        self.cancel_voice_listening()
        self._apply_ball_visibility(animated=False)

    def _bubble_closed(self) -> None:
        self._apply_ball_visibility(animated=False)

    def _apply_ball_visibility(self, animated: bool) -> None:
        should_show = (
            self._mode_active
            and self.should_show_ball()
            and not self.input_bar.isVisible()
        )
        if should_show:
            if not self.ball.isVisible():
                self._position_default_if_needed()
            if animated:
                self.ball.set_visible_animated(True)
            else:
                self.ball.show_without_activation()
            return
        if self.ball.isVisible():
            if animated:
                self.ball.set_visible_animated(False)
            else:
                self.ball.hide()
