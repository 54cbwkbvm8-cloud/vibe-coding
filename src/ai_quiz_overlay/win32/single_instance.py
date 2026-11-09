"""Windows 命名互斥量单实例保护。"""

from __future__ import annotations

import ctypes

from ..platform_support import require_windows


ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Local\\AIQuizOverlaySingleInstance"


class SingleInstanceGuard:
    def __init__(self) -> None:
        self._handle: int | None = None

    def acquire(self) -> bool:
        require_windows("单实例保护")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_bool,
            ctypes.c_wchar_p,
        ]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_bool

        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not handle:
            return False

        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False

        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_bool
        kernel32.CloseHandle(ctypes.c_void_p(self._handle))
        self._handle = None
