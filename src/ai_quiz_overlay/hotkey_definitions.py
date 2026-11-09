"""Declarative definitions for global hotkey features."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_HOTKEY = "Ctrl+Alt+Q"
DEFAULT_SCREENSHOT_HOTKEY = "Ctrl+Alt+A"
DEFAULT_ASSISTANT_HOTKEY = "Ctrl+Alt+Space"
DEFAULT_BALL_VISIBILITY_HOTKEY = "Ctrl+Alt+B"
DEFAULT_SCREEN_RECOGNITION_HOTKEY = "Ctrl+Alt+S"


@dataclass(frozen=True)
class HotkeyDefinition:
    key: str
    label: str
    default: str
    action: str
    mode_keys: tuple[str, ...] | None
    implemented: bool


HOTKEY_DEFINITIONS = (
    HotkeyDefinition(
        key="chat",
        label="问答唤出",
        default=DEFAULT_HOTKEY,
        action="chat",
        mode_keys=("quiz", "official_browser"),
        implemented=True,
    ),
    HotkeyDefinition(
        key="screenshot",
        label="区域截图",
        default=DEFAULT_SCREENSHOT_HOTKEY,
        action="screenshot",
        mode_keys=("quiz", "official_browser"),
        implemented=True,
    ),
    HotkeyDefinition(
        key="assistant",
        label="助手唤出",
        default=DEFAULT_ASSISTANT_HOTKEY,
        action="assistant",
        mode_keys=("global_assistant",),
        implemented=True,
    ),
    HotkeyDefinition(
        key="ball_visibility",
        label="显示/隐藏悬浮球",
        default=DEFAULT_BALL_VISIBILITY_HOTKEY,
        action="ball_visibility",
        mode_keys=("global_assistant",),
        implemented=True,
    ),
    HotkeyDefinition(
        key="screen_recognition",
        label="一键识别屏幕",
        default=DEFAULT_SCREEN_RECOGNITION_HOTKEY,
        action="screen_recognition",
        mode_keys=None,
        implemented=True,
    ),
)

HOTKEY_BY_KEY = {definition.key: definition for definition in HOTKEY_DEFINITIONS}


def default_hotkeys() -> dict[str, str]:
    return {
        definition.key: definition.default
        for definition in HOTKEY_DEFINITIONS
    }


def active_hotkey_keys(scope: str) -> tuple[str, ...]:
    return tuple(
        definition.key
        for definition in HOTKEY_DEFINITIONS
        if definition.implemented
        and (
            definition.mode_keys is None
            or scope in definition.mode_keys
        )
    )


def active_context_hotkey_keys(
    access_method: str,
    work_mode: str,
) -> tuple[str, ...]:
    """Return the union required by one active access/work context."""
    if access_method == "official_browser":
        return active_hotkey_keys("official_browser")
    return active_hotkey_keys(work_mode)
