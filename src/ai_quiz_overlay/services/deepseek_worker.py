"""Compatibility wrapper around the shared provider worker."""

from __future__ import annotations

from ..config import AppConfig
from .chat_provider import ChatRequest
from .deepseek_provider import DeepSeekApiProvider
from .provider_worker import ProviderChatWorker


class DeepSeekChatWorker(ProviderChatWorker):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int,
        messages: list[dict[str, object]],
    ) -> None:
        config = AppConfig(
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
        )
        super().__init__(
            DeepSeekApiProvider(),
            ChatRequest(
                config=config,
                credential=api_key,
                messages=messages,
            ),
        )
