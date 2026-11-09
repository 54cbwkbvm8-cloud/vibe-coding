"""Win32 全局快捷键注册、WM_HOTKEY 截获和多热键分发。"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import time
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

from ..platform_support import IS_WINDOWS, require_windows


HOTKEY_ID = 0x4A51
SCREENSHOT_HOTKEY_ID = 0x4A52
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

MODIFIER_NAMES = {
    "ALT": MOD_ALT,
    "CTRL": MOD_CONTROL,
    "CONTROL": MOD_CONTROL,
    "SHIFT": MOD_SHIFT,
    "WIN": MOD_WIN,
    "WINDOWS": MOD_WIN,
}


class HotkeyConfigError(ValueError):
    """表示快捷键文本不符合约定格式。"""


class HotkeyRegistrationError(RuntimeError):
    """表示 Win32 系统拒绝了快捷键注册。"""


@dataclass(frozen=True)
class HotkeySpec:
    """解析后的 Win32 修饰符和虚拟键码。"""

    modifiers: int
    virtual_key: int


@dataclass(frozen=True)
class _Registration:
    hwnd: int
    action: str
    hotkey_text: str


def parse_hotkey(hotkey_text: str) -> HotkeySpec:
    """解析 Ctrl+Alt+Q 这类快捷键文本。"""
    parts = [part.strip().upper() for part in hotkey_text.split("+")]
    if len(parts) < 2 or any(not part for part in parts):
        raise HotkeyConfigError(
            f"快捷键格式无效：{hotkey_text!r}。示例：Ctrl+Alt+Q。"
        )

    key_name = parts[-1]
    if key_name in MODIFIER_NAMES:
        raise HotkeyConfigError("快捷键最后一项必须是普通按键，例如 Q、1 或 F8。")

    modifiers = 0
    for name in parts[:-1]:
        if name not in MODIFIER_NAMES:
            raise HotkeyConfigError(f"不支持的修饰键：{name}。")
        modifiers |= MODIFIER_NAMES[name]

    if modifiers == 0:
        raise HotkeyConfigError("全局快捷键至少需要一个 Ctrl、Alt、Shift 或 Win。")

    if len(key_name) == 1 and ("A" <= key_name <= "Z" or "0" <= key_name <= "9"):
        virtual_key = ord(key_name)
    elif key_name.startswith("F") and key_name[1:].isdigit():
        function_number = int(key_name[1:])
        if not 1 <= function_number <= 24:
            raise HotkeyConfigError("功能键只支持 F1 到 F24。")
        virtual_key = 0x70 + function_number - 1
    elif key_name == "SPACE":
        virtual_key = 0x20
    else:
        raise HotkeyConfigError(
            f"不支持的普通按键：{key_name}。当前支持 A-Z、0-9、F1-F24 和 Space。"
        )

    return HotkeySpec(
        modifiers=modifiers | MOD_NOREPEAT,
        virtual_key=virtual_key,
    )


class _NativeHotkeyFilter(QAbstractNativeEventFilter):
    """只安装一次，并根据 Win32 hotkey ID 分发给管理器。"""

    def __init__(self, callback: Callable[[int], bool]) -> None:
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message) -> bool:
        event_name = bytes(event_type).decode("ascii", errors="ignore").rstrip("\x00")
        if event_name != "windows_generic_MSG":
            return False

        require_windows("全局快捷键消息")
        from ctypes import wintypes

        native_message = wintypes.MSG.from_address(int(message))
        if native_message.message != WM_HOTKEY:
            return False
        return self._callback(int(native_message.wParam))


class GlobalHotkeyManager(QObject):
    """在同一个 Qt 原生过滤器下管理多个全局快捷键。"""

    activated = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._registrations: dict[int, _Registration] = {}
        self._event_filter: _NativeHotkeyFilter | None = None
        self._application: QCoreApplication | None = None
        self._last_activation_time: dict[int, float] = {}

    @property
    def hotkey_text(self) -> str | None:
        return self.text_for(HOTKEY_ID)

    def text_for(self, hotkey_id: int) -> str | None:
        registration = self._registrations.get(hotkey_id)
        return registration.hotkey_text if registration is not None else None

    @property
    def registered_count(self) -> int:
        return len(self._registrations)

    def register(
        self,
        hwnd: int,
        hotkey_text: str,
        hotkey_id: int,
        action: str,
    ) -> None:
        """注册一个热键；不同功能使用不同 hotkey_id。"""
        require_windows("全局快捷键")
        self.unregister(hotkey_id)
        spec = parse_hotkey(hotkey_text)

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_uint,
        ]
        user32.RegisterHotKey.restype = ctypes.c_bool
        user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.UnregisterHotKey.restype = ctypes.c_bool

        registered = user32.RegisterHotKey(
            ctypes.c_void_p(hwnd),
            hotkey_id,
            spec.modifiers,
            spec.virtual_key,
        )
        if not registered:
            error_code = ctypes.get_last_error()
            if error_code == 1409:
                raise HotkeyRegistrationError(
                    f"快捷键 {hotkey_text} 已被其他程序占用。"
                    "请换一个组合键。"
                )
            raise HotkeyRegistrationError(
                f"快捷键 {hotkey_text} 注册失败，Win32 错误码：{error_code}。"
            )

        application = QCoreApplication.instance()
        if application is None:
            user32.UnregisterHotKey(ctypes.c_void_p(hwnd), hotkey_id)
            raise HotkeyRegistrationError("Qt 应用尚未创建，无法接收快捷键消息。")

        self._registrations[hotkey_id] = _Registration(
            hwnd=hwnd,
            action=action,
            hotkey_text=hotkey_text,
        )
        self._last_activation_time[hotkey_id] = 0.0
        self._application = application

        if self._event_filter is None:
            self._event_filter = _NativeHotkeyFilter(self._handle_native_hotkey)
            application.installNativeEventFilter(self._event_filter)

    def unregister(self, hotkey_id: int | None = None) -> None:
        """注销指定的一个热键；传 None 时注销全部热键。"""
        ids = list(self._registrations) if hotkey_id is None else [hotkey_id]
        if IS_WINDOWS:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.UnregisterHotKey.restype = ctypes.c_bool
            for current_id in ids:
                registration = self._registrations.get(current_id)
                if registration is not None:
                    user32.UnregisterHotKey(
                        ctypes.c_void_p(registration.hwnd),
                        current_id,
                    )

        for current_id in ids:
            self._registrations.pop(current_id, None)
            self._last_activation_time.pop(current_id, None)

        if not self._registrations and self._event_filter is not None:
            if self._application is not None:
                self._application.removeNativeEventFilter(self._event_filter)
            self._event_filter = None
            self._application = None

    def _handle_native_hotkey(self, hotkey_id: int) -> bool:
        registration = self._registrations.get(hotkey_id)
        if registration is None:
            return False

        current_time = time.monotonic()
        previous_time = self._last_activation_time.get(hotkey_id, 0.0)
        if current_time - previous_time >= 0.08:
            self._last_activation_time[hotkey_id] = current_time
            self.activated.emit(registration.action)
        return True
