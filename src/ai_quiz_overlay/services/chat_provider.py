"""Provider contracts shared by API and future login-based backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Protocol

from ..config import AppConfig


class ProviderUnavailableError(RuntimeError):
    """The selected access method is not implemented or enabled."""


class ProviderRequestError(RuntimeError):
    """A provider returned a user-readable request failure."""


class ProviderCancelledError(RuntimeError):
    """Provider streaming was cancelled by the user."""


@dataclass(frozen=True)
class ProviderCapabilities:
    streaming: bool
    images: bool
    login_required: bool = False
    stop_generation: bool = False


@dataclass(frozen=True)
class ChatRequest:
    config: AppConfig
    credential: str
    messages: list[dict[str, object]]


class ChatStream(Protocol):
    def __iter__(self) -> Iterator[str]: ...

    def close(self) -> None: ...


class ChatProvider(Protocol):
    provider_id: str
    display_name: str
    capabilities: ProviderCapabilities

    def image_support_error(self, model: str) -> str | None: ...

    def open_stream(self, request: ChatRequest) -> ChatStream: ...
