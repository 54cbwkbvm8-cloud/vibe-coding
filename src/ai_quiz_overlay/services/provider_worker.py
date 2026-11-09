"""Qt worker that turns any ChatProvider stream into standard signals."""

from __future__ import annotations

from threading import Event, Lock

from PySide6.QtCore import QObject, Signal, Slot

from ..logging_config import log_event
from .chat_provider import (
    ChatProvider,
    ChatRequest,
    ChatStream,
    ProviderCancelledError,
    ProviderRequestError,
)


class ProviderChatWorker(QObject):
    chunk_ready = Signal(str)
    completed = Signal(str)
    cancelled = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        provider: ChatProvider,
        request: ChatRequest,
    ) -> None:
        super().__init__()
        self._provider = provider
        self._request = request
        self._stop_event = Event()
        self._state_lock = Lock()
        self._stream: ChatStream | None = None
        self._terminal_emitted = False

    @Slot()
    def run(self) -> None:
        answer_parts: list[str] = []
        log_event("api_request_started")
        try:
            if self._stop_event.is_set():
                self._emit_cancelled("")
                return
            stream = self._provider.open_stream(self._request)
            with self._state_lock:
                self._stream = stream
            try:
                for chunk in stream:
                    if self._stop_event.is_set():
                        raise ProviderCancelledError()
                    answer_parts.append(chunk)
                    self.chunk_ready.emit(chunk)
            finally:
                stream.close()
                with self._state_lock:
                    self._stream = None

            if self._stop_event.is_set():
                log_event("api_request_cancelled")
                self._emit_cancelled("".join(answer_parts))
            else:
                log_event("api_request_completed")
                self._emit_completed("".join(answer_parts))
        except ProviderCancelledError:
            log_event("api_request_cancelled")
            self._emit_cancelled("".join(answer_parts))
        except ProviderRequestError as exc:
            self._emit_failed(str(exc))
        except Exception as exc:
            log_event(
                "api_unexpected_error",
                error_type=type(exc).__name__,
            )
            self._emit_failed("请求过程中发生错误，请检查网络或配置。")
        finally:
            self._request = ChatRequest(
                self._request.config,
                "",
                self._request.messages,
            )

    def request_stop(self) -> None:
        self._stop_event.set()
        with self._state_lock:
            stream = self._stream
        if stream is not None:
            stream.close()

    def _emit_completed(self, answer: str) -> None:
        if not self._terminal_emitted:
            self._terminal_emitted = True
            self.completed.emit(answer)

    def _emit_cancelled(self, answer: str) -> None:
        if not self._terminal_emitted:
            self._terminal_emitted = True
            self.cancelled.emit(answer)

    def _emit_failed(self, message: str) -> None:
        if not self._terminal_emitted:
            self._terminal_emitted = True
            self.failed.emit(message)
