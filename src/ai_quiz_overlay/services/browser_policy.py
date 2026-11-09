"""Navigation and permission policy for the non-automating browser shell."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


OFFICIAL_BROWSER_URL = "https://chat.deepseek.com/"
ALLOWED_MAIN_FRAME_ROOT = "deepseek.com"
MAX_BROWSER_PERMISSION = "deny"

# Observed while loading only the public login page on 2026-11-08. These are
# resource/embed hosts, not approved top-level navigation destinations. A
# third-party login popup that needs one of them is deliberately opened in the
# system browser until the user explicitly approves a main-frame exception.
OBSERVED_PUBLIC_LOGIN_RESOURCE_HOSTS = (
    "chat.deepseek.com",
    "fe-static.deepseek.com",
    "appleid.cdn-apple.com",
    "castatic.fengkongcloud.cn",
    "fp-it-acc.portal101.cn",
    "gator.volces.com",
    "lf3-data.volccdn.com",
    "localhost.weixin.qq.com",
    "lp.open.weixin.qq.com",
    "open.weixin.qq.com",
    "res.wx.qq.com",
    "support.weixin.qq.com",
)


@dataclass(frozen=True)
class BrowserPermissionPolicy:
    permission: str
    behavior: str
    reason: str


PERMISSION_POLICIES = (
    BrowserPermissionPolicy(
        "摄像头、麦克风、音视频采集",
        "拒绝",
        "只在用户明确选择后由本机语音模块处理，不授予网页。",
    ),
    BrowserPermissionPolicy(
        "定位",
        "拒绝",
        "浏览器模式不向网页授予定位权限。",
    ),
    BrowserPermissionPolicy(
        "通知",
        "拒绝",
        "浏览器模式不创建网页通知权限。",
    ),
    BrowserPermissionPolicy(
        "屏幕共享",
        "拒绝",
        "浏览器模式不允许网页采集桌面。",
    ),
    BrowserPermissionPolicy(
        "剪贴板读取/写入",
        "拒绝",
        "剪贴板只由用户通过系统快捷键操作。",
    ),
    BrowserPermissionPolicy(
        "MIDI/USB/串口等设备",
        "拒绝",
        "不授予网页设备访问权限。",
    ),
    BrowserPermissionPolicy(
        "文件选择",
        "允许系统文件选择对话框",
        "仅由用户手动选择文件；软件不自动上传。",
    ),
    BrowserPermissionPolicy(
        "下载",
        "拒绝并提示",
        "请在系统浏览器中下载。",
    ),
)


def is_allowed_main_frame_url(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    return (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and not parsed.port
        and (
            host == ALLOWED_MAIN_FRAME_ROOT
            or host.endswith("." + ALLOWED_MAIN_FRAME_ROOT)
        )
    )


def address_display(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    if not host:
        return ""
    return f"{host}{path}"[:512]


def main_frame_action(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return "external"
    return "internal" if is_allowed_main_frame_url(url) else "external"


def popup_action(url: str) -> str:
    """Apply the same top-level URL policy to window.open-style popups."""
    return main_frame_action(url)


def permission_is_denied(_permission_name: str) -> bool:
    return True


def normal_browser_settings() -> tuple[tuple[str, bool], ...]:
    return (
        ("JavascriptCanOpenWindows", True),
        ("JavascriptCanAccessClipboard", False),
        ("JavascriptCanPaste", False),
        ("ScreenCaptureEnabled", False),
        ("AllowGeolocationOnInsecureOrigins", False),
        ("AllowRunningInsecureContent", False),
        ("AllowWindowActivationFromJavaScript", False),
    )
