"""Application-level WM_NCHITTEST handling for frameless resizing."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QPoint


WM_NCHITTEST = 0x0084


class NativeResizeFilter(QAbstractNativeEventFilter):
    def __init__(
        self,
        hwnd: int,
        hit_test: Callable[[QPoint], int],
    ) -> None:
        super().__init__()
        self._hwnd = hwnd
        self._hit_test = hit_test

    def nativeEventFilter(self, event_type, message):
        try:
            name = bytes(event_type).decode(
                "ascii",
                errors="ignore",
            ).rstrip("\x00")
            if name != "windows_generic_MSG":
                return False
            if message is None:
                return False
            native_message = wintypes.MSG.from_address(int(message))
            if native_message.hWnd is None:
                return False
            if int(native_message.hWnd) != self._hwnd:
                return False

            if native_message.message == WM_NCHITTEST:
                x = ctypes.c_short(native_message.lParam & 0xFFFF).value
                y = ctypes.c_short((native_message.lParam >> 16) & 0xFFFF).value
                result = self._hit_test(QPoint(x, y))
                if result:
                    return True, result
            return False
        except Exception as exc:
            print(
                f"NATIVE_RESIZE_FILTER_ERROR={type(exc).__name__}:{exc}",
                flush=True,
            )
            return False
