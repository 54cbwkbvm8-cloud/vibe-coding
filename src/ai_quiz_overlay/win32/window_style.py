"""WS_EX_NOACTIVATE 等扩展窗口样式。"""

from __future__ import annotations

import ctypes

from ..platform_support import require_windows


GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SW_RESTORE = 9


class WindowStyleError(RuntimeError):
    """表示扩展窗口样式设置失败。"""


def set_no_activate(hwnd: int, enabled: bool) -> None:
    """切换 WS_EX_NOACTIVATE，不移动或激活窗口。"""
    require_windows("不抢焦点窗口模式")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_style = user32.GetWindowLongPtrW
    set_style = user32.SetWindowLongPtrW
    get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    set_style.restype = ctypes.c_ssize_t
    user32.SetWindowPos.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = ctypes.c_bool

    style = int(get_style(ctypes.c_void_p(hwnd), GWL_EXSTYLE))
    updated = style | WS_EX_NOACTIVATE if enabled else style & ~WS_EX_NOACTIVATE

    ctypes.set_last_error(0)
    previous = set_style(
        ctypes.c_void_p(hwnd),
        GWL_EXSTYLE,
        ctypes.c_ssize_t(updated),
    )
    error_code = ctypes.get_last_error()
    if previous == 0 and error_code != 0:
        raise WindowStyleError(
            f"设置 WS_EX_NOACTIVATE 失败，Win32 错误码：{error_code}。"
        )

    user32.SetWindowPos(
        ctypes.c_void_p(hwnd),
        None,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )


def has_no_activate(hwnd: int) -> bool:
    """读取 WS_EX_NOACTIVATE，供自动测试使用。"""
    require_windows("读取不抢焦点窗口状态")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_style = user32.GetWindowLongPtrW
    get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    style = get_style(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
    return bool(style & WS_EX_NOACTIVATE)


def activate_foreground(hwnd: int) -> bool:
    """Bring the window to the foreground and focus it from a trusted action."""
    require_windows("全局助手输入焦点")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    user32.AttachThreadInput.argtypes = [
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_bool,
    ]
    user32.AttachThreadInput.restype = ctypes.c_bool
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.ShowWindow.restype = ctypes.c_bool
    user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
    user32.BringWindowToTop.restype = ctypes.c_bool
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow.restype = ctypes.c_bool
    user32.SetFocus.argtypes = [ctypes.c_void_p]
    user32.SetFocus.restype = ctypes.c_void_p
    kernel32.GetCurrentThreadId.restype = ctypes.c_ulong

    target = ctypes.c_void_p(hwnd)
    current_thread = int(kernel32.GetCurrentThreadId())
    target_thread = int(
        user32.GetWindowThreadProcessId(target, None)
    )
    foreground = user32.GetForegroundWindow()
    foreground_thread = (
        int(user32.GetWindowThreadProcessId(foreground, None))
        if foreground
        else 0
    )

    attached_threads: list[int] = []
    for thread_id in {target_thread, foreground_thread}:
        if (
            thread_id
            and thread_id != current_thread
            and user32.AttachThreadInput(
                current_thread,
                thread_id,
                True,
            )
        ):
            attached_threads.append(thread_id)
    try:
        user32.ShowWindow(target, SW_RESTORE)
        user32.BringWindowToTop(target)
        user32.SetForegroundWindow(target)
        user32.SetFocus(target)
        current_foreground = user32.GetForegroundWindow()
        return bool(current_foreground) and int(current_foreground) == hwnd
    finally:
        for thread_id in reversed(attached_threads):
            user32.AttachThreadInput(
                current_thread,
                thread_id,
                False,
            )


def foreground_window() -> int:
    """Return the current foreground window handle."""
    require_windows("读取前台窗口")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    return int(user32.GetForegroundWindow() or 0)
