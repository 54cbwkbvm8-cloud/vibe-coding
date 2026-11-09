"""Windows session-lock notifications for microphone shutdown."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter

from ..platform_support import IS_WINDOWS


WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_LOGOFF = 0x5
NOTIFY_FOR_THIS_SESSION = 0


def is_recording_stop_session_event(message: int, wparam: int) -> bool:
    return (
        message == WM_WTSSESSION_CHANGE
        and wparam in {WTS_SESSION_LOCK, WTS_SESSION_LOGOFF}
    )


class SessionLockFilter(QAbstractNativeEventFilter):
    def __init__(self, hwnd: int, callback: Callable[[], None]) -> None:
        super().__init__()
        self._hwnd = int(hwnd)
        self._callback = callback
        self._wtsapi32 = None
        if IS_WINDOWS:
            try:
                self._wtsapi32 = ctypes.WinDLL(
                    "wtsapi32",
                    use_last_error=True,
                )
                self._wtsapi32.WTSRegisterSessionNotification(
                    wintypes.HWND(self._hwnd),
                    NOTIFY_FOR_THIS_SESSION,
                )
            except Exception:
                self._wtsapi32 = None

    def nativeEventFilter(self, event_type, message):
        if not IS_WINDOWS or message is None:
            return False
        try:
            name = bytes(event_type).decode(
                "ascii",
                errors="ignore",
            ).rstrip("\x00")
            if name != "windows_generic_MSG":
                return False
            native_message = wintypes.MSG.from_address(int(message))
            if int(native_message.hWnd or 0) != self._hwnd:
                return False
            if is_recording_stop_session_event(
                int(native_message.message),
                int(native_message.wParam),
            ):
                self._callback()
            return False
        except Exception:
            return False

    def close(self) -> None:
        if self._wtsapi32 is None:
            return
        try:
            self._wtsapi32.WTSUnRegisterSessionNotification(
                wintypes.HWND(self._hwnd)
            )
        except Exception:
            pass
        self._wtsapi32 = None
