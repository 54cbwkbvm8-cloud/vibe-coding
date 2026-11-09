"""DeepSeek API implementation of the shared ChatProvider contract."""

from __future__ import annotations

import json
from threading import Event, Lock
from typing import Iterator

import httpx

from ..logging_config import log_event
from .chat_provider import (
    ChatRequest,
    ProviderCancelledError,
    ProviderCapabilities,
    ProviderRequestError,
)
from .deepseek_errors import http_error_message, redact_sensitive
from .vision_support import image_model_error


class DeepSeekStream:
    def __init__(self, request: ChatRequest) -> None:
        self._request = request
        self._stop_event = Event()
        self._state_lock = Lock()
        self._client: httpx.Client | None = None
        self._response: httpx.Response | None = None

    def __iter__(self) -> Iterator[str]:
        config = self._request.config
        api_key = self._request.credential
        try:
            if self._stop_event.is_set():
                raise ProviderCancelledError()

            timeout = httpx.Timeout(
                float(config.timeout_seconds),
                connect=min(10.0, float(config.timeout_seconds)),
            )
            client = httpx.Client(timeout=timeout, trust_env=False)
            with self._state_lock:
                self._client = client

            with client.stream(
                "POST",
                f"{config.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                json={
                    "model": config.model,
                    "messages": self._request.messages,
                    "stream": True,
                    "thinking": {"type": "disabled"},
                },
            ) as response:
                with self._state_lock:
                    self._response = response

                if response.status_code >= 400:
                    body = response.read()
                    log_event(
                        "api_http_error",
                        status_code=response.status_code,
                        error_type="http",
                    )
                    raise ProviderRequestError(
                        http_error_message(
                            response.status_code,
                            body,
                            api_key,
                        )
                    )

                for line in response.iter_lines():
                    if self._stop_event.is_set():
                        raise ProviderCancelledError()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    if not payload:
                        continue
                    try:
                        event = json.loads(payload)
                        choices = event.get("choices") or []
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                    except (
                        json.JSONDecodeError,
                        IndexError,
                        TypeError,
                        AttributeError,
                    ) as exc:
                        log_event(
                            "api_stream_parse_error",
                            error_type="stream_parse",
                        )
                        raise ProviderRequestError(
                            "DeepSeek 返回了无法解析的流式数据。"
                        ) from exc
                    if isinstance(content, str) and content:
                        yield content

            if self._stop_event.is_set():
                raise ProviderCancelledError()
        except httpx.TimeoutException as exc:
            log_event("api_request_timeout", error_type="timeout")
            if self._stop_event.is_set():
                raise ProviderCancelledError() from exc
            raise ProviderRequestError(
                f"请求超时，超过 {config.timeout_seconds} 秒未完成。"
                "请检查网络或调大超时时间。"
            ) from exc
        except httpx.ConnectError as exc:
            log_event("api_connect_error", error_type="connect")
            if self._stop_event.is_set():
                raise ProviderCancelledError() from exc
            raise ProviderRequestError(
                "无法连接 DeepSeek 服务。请检查网络连接和 base_url。"
            ) from exc
        except httpx.RequestError as exc:
            log_event(
                "api_request_error",
                error_type=type(exc).__name__,
            )
            if self._stop_event.is_set():
                raise ProviderCancelledError() from exc
            detail = redact_sensitive(str(exc)[:1000], api_key)[:300]
            raise ProviderRequestError(
                f"无法连接 DeepSeek：{detail or '请检查网络和 base_url。'}"
            ) from exc
        finally:
            self._request = ChatRequest(
                self._request.config,
                "",
                self._request.messages,
            )
            with self._state_lock:
                self._response = None
                self._client = None

    def close(self) -> None:
        self._stop_event.set()
        with self._state_lock:
            response = self._response
            client = self._client
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


class DeepSeekApiProvider:
    provider_id = "api"
    display_name = "API 接入"
    capabilities = ProviderCapabilities(
        streaming=True,
        images=True,
    )

    def image_support_error(self, model: str) -> str | None:
        return image_model_error(model)

    def open_stream(self, request: ChatRequest) -> DeepSeekStream:
        return DeepSeekStream(request)
