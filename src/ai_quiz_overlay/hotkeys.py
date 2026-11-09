"""Declarative global-hotkey registry with transactional updates."""

from __future__ import annotations

from typing import Callable, Mapping, Protocol

from .config import AppConfig
from .hotkey_definitions import (
    HOTKEY_BY_KEY,
    HOTKEY_DEFINITIONS,
    active_hotkey_keys,
    default_hotkeys,
)
from .win32.hotkey import HotkeyConfigError, parse_hotkey


class HotkeyBackend(Protocol):
    def register(
        self,
        hwnd: int,
        hotkey_text: str,
        hotkey_id: int,
        action: str,
    ) -> None: ...

    def unregister(self, hotkey_id: int | None = None) -> None: ...


def hotkey_values(config: AppConfig) -> dict[str, str]:
    defaults = default_hotkeys()
    return {
        definition.key: config.hotkeys.get(
            definition.key,
            defaults[definition.key],
        )
        for definition in HOTKEY_DEFINITIONS
    }


def validate_hotkey_values(values: Mapping[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    parsed: dict[tuple[int, int], str] = {}
    for definition in HOTKEY_DEFINITIONS:
        raw = values.get(definition.key, definition.default)
        hotkey_text = str(raw).strip()
        spec = parse_hotkey(hotkey_text)
        signature = (spec.modifiers, spec.virtual_key)
        previous = parsed.get(signature)
        if previous is not None:
            raise HotkeyConfigError(
                f"{previous}和{definition.label}不能使用相同组合键。"
            )
        parsed[signature] = definition.label
        normalized[definition.key] = hotkey_text
    return normalized


class PreparedHotkeyUpdate:
    def __init__(
        self,
        registry: HotkeyRegistry,
        values: dict[str, str],
        new_ids: dict[str, int],
        changed_keys: tuple[str, ...],
        removed_keys: tuple[str, ...],
        active_keys: tuple[str, ...],
    ) -> None:
        self._registry = registry
        self._values = values
        self._new_ids = new_ids
        self._changed_keys = changed_keys
        self._removed_keys = removed_keys
        self._active_keys = active_keys
        self._committed = False
        self._rolled_back = False

    @property
    def changed_keys(self) -> tuple[str, ...]:
        return self._changed_keys

    def commit(self) -> None:
        if self._committed or self._rolled_back:
            return
        for key in self._changed_keys:
            old_id = self._registry._active_ids.get(key)
            if old_id is not None:
                self._registry._backend.unregister(old_id)
                self._registry._active_ids.pop(key, None)
        for key in self._removed_keys:
            old_id = self._registry._active_ids.get(key)
            if old_id is not None:
                self._registry._backend.unregister(old_id)
                self._registry._active_ids.pop(key, None)
        for key, hotkey_id in self._new_ids.items():
            self._registry._active_ids[key] = hotkey_id
            self._registry._reserved_ids.discard(hotkey_id)
        self._registry._active_keys = self._active_keys
        self._registry._active_values = {
            key: self._values[key]
            for key in self._active_keys
        }
        self._registry._configured_values = dict(self._values)
        self._committed = True

    def rollback(self) -> None:
        if self._committed or self._rolled_back:
            return
        for hotkey_id in self._new_ids.values():
            self._registry._backend.unregister(hotkey_id)
            self._registry._reserved_ids.discard(hotkey_id)
        self._rolled_back = True


class HotkeyRegistry:
    """Own dynamic Win32 IDs and update changed bindings transactionally."""

    def __init__(
        self,
        backend: HotkeyBackend,
        hwnd_provider: Callable[[], int],
    ) -> None:
        self._backend = backend
        self._hwnd_provider = hwnd_provider
        self._active_ids: dict[str, int] = {}
        self._active_values: dict[str, str] = {}
        self._configured_values: dict[str, str] = default_hotkeys()
        self._active_keys: tuple[str, ...] = ()
        self._reserved_ids: set[int] = set()
        self._next_id = 0x7000
        self._suspended = False

    @property
    def active_values(self) -> dict[str, str]:
        return dict(self._active_values)

    @property
    def active_ids(self) -> dict[str, int]:
        return dict(self._active_ids)

    @property
    def suspended(self) -> bool:
        return self._suspended

    def prepare(
        self,
        values: Mapping[str, str],
        active_keys: tuple[str, ...],
    ) -> PreparedHotkeyUpdate:
        if self._suspended:
            raise HotkeyConfigError(
                "快捷键正在录制，请先离开录制框再保存。"
            )
        normalized = validate_hotkey_values(values)
        unknown_keys = set(active_keys) - set(HOTKEY_BY_KEY)
        if unknown_keys:
            raise HotkeyConfigError(
                f"未登记的快捷键功能：{', '.join(sorted(unknown_keys))}。"
            )
        changed_keys = tuple(
            definition.key
            for definition in HOTKEY_DEFINITIONS
            if (
                definition.key in active_keys
                and (
                    definition.key not in self._active_ids
                    or self._active_values.get(definition.key)
                    != normalized[definition.key]
                )
            )
        )
        removed_keys = tuple(
            key
            for key in self._active_ids
            if key not in active_keys
        )
        new_ids: dict[str, int] = {}
        hwnd = int(self._hwnd_provider())
        try:
            for definition in HOTKEY_DEFINITIONS:
                if definition.key not in changed_keys:
                    continue
                hotkey_id = self._allocate_id()
                self._reserved_ids.add(hotkey_id)
                self._backend.register(
                    hwnd,
                    normalized[definition.key],
                    hotkey_id,
                    definition.action,
                )
                new_ids[definition.key] = hotkey_id
        except Exception:
            for hotkey_id in new_ids.values():
                self._backend.unregister(hotkey_id)
                self._reserved_ids.discard(hotkey_id)
            raise
        return PreparedHotkeyUpdate(
            self,
            normalized,
            new_ids,
            changed_keys,
            removed_keys,
            active_keys,
        )

    def register_initial(
        self,
        values: Mapping[str, str],
        active_keys: tuple[str, ...],
    ) -> None:
        prepared = self.prepare(values, active_keys)
        prepared.commit()

    def suspend(self) -> None:
        if self._suspended:
            return
        for hotkey_id in self._active_ids.values():
            self._backend.unregister(hotkey_id)
        self._active_ids.clear()
        self._suspended = True

    def resume(self) -> PreparedHotkeyUpdate:
        if not self._suspended:
            return self.prepare(
                self._configured_values,
                self._active_keys,
            )
        values = self._configured_values
        self._suspended = False
        try:
            prepared = self.prepare(values, self._active_keys)
            prepared.commit()
        except Exception:
            self._suspended = True
            raise
        return prepared

    def unregister_all(self) -> None:
        for hotkey_id in self._active_ids.values():
            self._backend.unregister(hotkey_id)
        self._active_ids.clear()
        for hotkey_id in self._reserved_ids:
            self._backend.unregister(hotkey_id)
        self._reserved_ids.clear()

    def _allocate_id(self) -> int:
        used = set(self._active_ids.values()) | self._reserved_ids
        while self._next_id in used:
            self._next_id += 1
            if self._next_id > 0xBFFF:
                self._next_id = 0x100
        hotkey_id = self._next_id
        self._next_id += 1
        return hotkey_id
