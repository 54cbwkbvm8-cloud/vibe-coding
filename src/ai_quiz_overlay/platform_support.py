"""跨平台导入时使用的运行环境检查。"""

from __future__ import annotations

import sys


IS_WINDOWS = sys.platform == "win32"


class UnsupportedPlatformError(RuntimeError):
    """表示某项功能只能在 Windows 上运行。"""


def require_windows(feature: str) -> None:
    """在实际调用 Windows 功能前检查平台，导入模块时不触发。"""
    if not IS_WINDOWS:
        raise UnsupportedPlatformError(
            f"{feature} 只能在 Windows 上运行；当前平台是 {sys.platform!r}。"
        )
