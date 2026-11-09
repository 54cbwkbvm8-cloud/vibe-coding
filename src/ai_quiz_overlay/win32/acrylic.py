"""Windows 11 system Acrylic with a safe Qt fallback signal."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
import sys
from typing import Mapping

from ..platform_support import IS_WINDOWS


ACRYLIC_FALLBACK_ENV = "NAIWA_FORCE_GLASS_FALLBACK"
ACRYLIC_MIN_BUILD = 26100

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_NCRENDERING_POLICY = 2
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWA_REDIRECTIONBITMAP_ALPHA = 39

DWMWA_COLOR_NONE = 0xFFFFFFFE
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2
DWMNCRP_DISABLED = 1
DWMSBT_NONE = 1
DWMSBT_TRANSIENTWINDOW = 3

_TRUE_VALUES = {"1", "true", "yes", "on"}

# The Build 26200 experiment showed that Desktop Acrylic paints outside the
# Qt anti-aliased radius despite DWMWA_REDIRECTIONBITMAP_ALPHA. Keep this
# disabled so large rounded glass corners remain exact.
ROUNDED_ACRYLIC_VERIFIED = False


@dataclass(frozen=True)
class AcrylicAvailability:
    supported: bool
    reason: str


class MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


def fallback_forced(environment: Mapping[str, str] | None = None) -> bool:
    values = environment if environment is not None else os.environ
    return values.get(ACRYLIC_FALLBACK_ENV, "").strip().lower() in _TRUE_VALUES


def should_apply_acrylic(
    *,
    enabled: bool,
    windows_build: int,
    environment: Mapping[str, str] | None = None,
) -> bool:
    """Return whether the current Windows build can try system Acrylic."""
    availability = acrylic_availability(
        windows_build=windows_build,
        environment=environment,
    )
    return (
        enabled
        and IS_WINDOWS
        and availability.supported
    )


def acrylic_availability(
    *,
    windows_build: int,
    environment: Mapping[str, str] | None = None,
) -> AcrylicAvailability:
    """Describe whether rounded-window Acrylic can be used safely."""
    if fallback_forced(environment):
        return AcrylicAvailability(
            False,
            "已通过 NAIWA_FORCE_GLASS_FALLBACK 强制使用 Qt 自绘玻璃。",
        )
    if windows_build < 22000:
        return AcrylicAvailability(
            False,
            "Windows 10 不支持圆角窗口的系统毛玻璃，已使用 Qt 自绘玻璃。",
        )
    if windows_build < ACRYLIC_MIN_BUILD:
        return AcrylicAvailability(
            False,
            "当前 Windows 版本不支持圆角窗口的逐像素系统材质裁剪，"
            "已使用 Qt 自绘玻璃。",
        )
    if not ROUNDED_ACRYLIC_VERIFIED:
        return AcrylicAvailability(
            False,
            "当前 Windows 构建的圆角 Acrylic 裁剪验证未通过，"
            "已使用 Qt 自绘玻璃。",
        )
    return AcrylicAvailability(True, "")


def current_windows_build() -> int:
    if not IS_WINDOWS:
        return 0
    try:
        return int(sys.getwindowsversion().build)
    except (AttributeError, OSError):
        return 0


def corner_preference_for_backdrop(acrylic_enabled: bool) -> int:
    """Avoid DWM's rounded-window shadow when Qt paints the corner."""
    return DWMWCP_ROUND if acrylic_enabled else DWMWCP_DONOTROUND


def _set_backdrop_attribute(hwnd: int, enabled: bool) -> bool:
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    dwm_set = dwmapi.DwmSetWindowAttribute
    dwm_set.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    dwm_set.restype = ctypes.c_long

    dwm_extend = dwmapi.DwmExtendFrameIntoClientArea
    dwm_extend.argtypes = [wintypes.HWND, ctypes.POINTER(MARGINS)]
    dwm_extend.restype = ctypes.c_long

    dark_mode = ctypes.c_int(1)
    corner = ctypes.c_int(corner_preference_for_backdrop(enabled))
    border = wintypes.DWORD(DWMWA_COLOR_NONE)
    non_client_policy = ctypes.c_int(DWMNCRP_DISABLED)
    alpha_enabled = wintypes.BOOL(enabled)
    backdrop = ctypes.c_int(
        DWMSBT_TRANSIENTWINDOW if enabled else DWMSBT_NONE
    )
    margins = MARGINS(-1, -1, -1, -1) if enabled else MARGINS(0, 0, 0, 0)

    results = [
        dwm_extend(wintypes.HWND(hwnd), ctypes.byref(margins)),
        dwm_set(
            wintypes.HWND(hwnd),
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(dark_mode),
            ctypes.sizeof(dark_mode),
        ),
        dwm_set(
            wintypes.HWND(hwnd),
            DWMWA_NCRENDERING_POLICY,
            ctypes.byref(non_client_policy),
            ctypes.sizeof(non_client_policy),
        ),
        dwm_set(
            wintypes.HWND(hwnd),
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(corner),
            ctypes.sizeof(corner),
        ),
        dwm_set(
            wintypes.HWND(hwnd),
            DWMWA_BORDER_COLOR,
            ctypes.byref(border),
            ctypes.sizeof(border),
        ),
        dwm_set(
            wintypes.HWND(hwnd),
            DWMWA_REDIRECTIONBITMAP_ALPHA,
            ctypes.byref(alpha_enabled),
            ctypes.sizeof(alpha_enabled),
        ),
    ]
    results.append(
        dwm_set(
            wintypes.HWND(hwnd),
            DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(backdrop),
            ctypes.sizeof(backdrop),
        )
    )
    return all(result == 0 for result in results)


def apply_acrylic_material(
    hwnd: int,
    enabled: bool,
    *,
    environment: Mapping[str, str] | None = None,
) -> bool:
    """Try to apply or disable system Acrylic; never fail the application."""
    if not IS_WINDOWS or not hwnd:
        return False

    build = current_windows_build()
    availability = acrylic_availability(
        windows_build=build,
        environment=environment,
    )
    if not enabled or not availability.supported:
        try:
            _set_backdrop_attribute(hwnd, False)
        except (AttributeError, OSError, ValueError):
            return False
        return False

    try:
        active = _set_backdrop_attribute(hwnd, True)
        if not active:
            _set_backdrop_attribute(hwnd, False)
        return active
    except (AttributeError, OSError, ValueError):
        return False
