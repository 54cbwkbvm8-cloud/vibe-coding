"""通过 SetWindowPos 把窗口放入 Windows 的 topmost 层级。"""

from __future__ import annotations

import ctypes

from ..platform_support import require_windows


HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200
SWP_SHOWWINDOW = 0x0040
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008


class TopmostError(RuntimeError):
    """表示 SetWindowPos 调用失败。"""


def apply_topmost(hwnd: int) -> None:
    """在不移动、不改变大小和不抢焦点的前提下重新置顶。"""
    require_windows("窗口置顶")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
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

    flags = (
        SWP_NOMOVE
        | SWP_NOSIZE
        | SWP_NOACTIVATE
        | SWP_NOOWNERZORDER
        | SWP_SHOWWINDOW
    )
    succeeded = user32.SetWindowPos(
        ctypes.c_void_p(hwnd),
        ctypes.c_void_p(HWND_TOPMOST),
        0,
        0,
        0,
        0,
        flags,
    )
    if not succeeded:
        raise TopmostError(
            f"SetWindowPos 置顶失败，Win32 错误码：{ctypes.get_last_error()}。"
        )


def has_topmost_style(hwnd: int) -> bool:
    """读取扩展窗口样式，供自动测试确认 WS_EX_TOPMOST。"""
    require_windows("读取窗口置顶状态")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_window_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    get_window_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get_window_long.restype = ctypes.c_ssize_t
    style = get_window_long(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
    return bool(style & WS_EX_TOPMOST)
