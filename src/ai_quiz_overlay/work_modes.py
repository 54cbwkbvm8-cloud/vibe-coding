"""Work-mode contracts and availability registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .hotkey_definitions import active_hotkey_keys


class WorkModeUnavailableError(RuntimeError):
    """The selected work mode is not implemented or enabled."""


@dataclass(frozen=True)
class WorkModeDefinition:
    key: str
    label: str
    enabled: bool
    unavailable_reason: str = ""


WORK_MODES = (
    WorkModeDefinition(
        key="quiz",
        label="搜题模式",
        enabled=True,
    ),
    WorkModeDefinition(
        key="global_assistant",
        label="全局助手模式",
        enabled=True,
    ),
)

WORK_MODE_BY_KEY = {
    definition.key: definition
    for definition in WORK_MODES
}


class WorkMode(Protocol):
    definition: WorkModeDefinition

    def active_hotkey_keys(self) -> tuple[str, ...]: ...
    def activate(self) -> None: ...
    def deactivate(self, cancel_request: bool = True) -> None: ...
    def is_busy(self) -> bool: ...


class QuizWorkMode:
    definition = WORK_MODE_BY_KEY["quiz"]

    def __init__(self, window=None) -> None:
        self._window = window

    def active_hotkey_keys(self) -> tuple[str, ...]:
        return active_hotkey_keys(self.definition.key)

    def activate(self) -> None:
        if self._window is not None:
            self._window.show_overlay()

    def deactivate(self, cancel_request: bool = True) -> None:
        if self._window is not None:
            if cancel_request and self._window.is_busy:
                self._window.stop_request_then(lambda: None)
            self._window.hide_overlay()

    def is_busy(self) -> bool:
        return bool(self._window is not None and self._window.is_busy)


class GlobalAssistantWorkMode:
    definition = WORK_MODE_BY_KEY["global_assistant"]

    def __init__(self, assistant=None) -> None:
        self._assistant = assistant

    def active_hotkey_keys(self) -> tuple[str, ...]:
        return active_hotkey_keys(self.definition.key)

    def activate(self) -> None:
        if self._assistant is not None:
            self._assistant.activate()

    def deactivate(self, cancel_request: bool = True) -> None:
        if self._assistant is not None:
            self._assistant.deactivate(cancel_request=cancel_request)

    def is_busy(self) -> bool:
        return bool(self._assistant is not None and self._assistant.is_busy)


def create_work_mode(
    work_mode: str,
    *,
    window=None,
    assistant=None,
) -> WorkMode:
    if work_mode == "quiz":
        return QuizWorkMode(window)
    if work_mode == "global_assistant":
        return GlobalAssistantWorkMode(assistant)
    definition = WORK_MODE_BY_KEY.get(work_mode)
    if definition is None:
        raise WorkModeUnavailableError("未知的工作模式。")
    raise WorkModeUnavailableError(
        f"{definition.label}尚未启用：{definition.unavailable_reason}。"
    )
