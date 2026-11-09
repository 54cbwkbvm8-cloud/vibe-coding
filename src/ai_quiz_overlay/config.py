"""应用配置的读取、校验和首次创建。"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

from .hotkey_definitions import (
    DEFAULT_HOTKEY,
    DEFAULT_SCREENSHOT_HOTKEY,
    HOTKEY_DEFINITIONS,
    default_hotkeys,
)
from .services.network_policy import (
    OFFICIAL_API_HOST,
    OFFICIAL_API_ORIGIN,
)
from .theme import clamp_glass_opacity


APP_DIRECTORY_NAME = "AIQuizOverlay"
CONFIG_FILE_NAME = "config.json"
CONFIG_SCHEMA_VERSION = 2
DEFAULT_ACCESS_METHOD = "api"
DEFAULT_WORK_MODE = "quiz"
DEFAULT_BASE_URL = OFFICIAL_API_ORIGIN
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_IMAGE_MAX_EDGE = 1600
DEFAULT_OPACITY = 1.0
DEFAULT_ACRYLIC_ENABLED = True
DEFAULT_COMPACT_MODE = False
DEFAULT_ASSISTANT_BALL_PERSISTENT = True
DEFAULT_ASSISTANT_AUTO_HIDE_SECONDS = 60
DEFAULT_ASSISTANT_BALL_SIZE = 64
MIN_ASSISTANT_BALL_SIZE = 40
MAX_ASSISTANT_BALL_SIZE = 160
DEFAULT_SCREEN_RECOGNITION_PROMPT = (
    "请概括当前画面在做什么，提取关键文字，并指出需要注意的地方。"
)
DEFAULT_SCREEN_RECOGNITION_AUTO_SEND = False
DEFAULT_SCREEN_RECOGNITION_IMAGE_MAX_EDGE = 2048
SCREEN_RECOGNITION_CONSENT_VERSION = 1
DEFAULT_VOICE_ENABLED = False
DEFAULT_VOICE_AUTO_LISTEN = False
DEFAULT_VOICE_AUTO_SEND = False
DEFAULT_VOICE_LANGUAGE = "zh"
DEFAULT_VOICE_MICROPHONE_DEVICE = ""
DEFAULT_VOICE_SILENCE_SECONDS = 1.2
DEFAULT_VOICE_MAX_RECORD_SECONDS = 30
DEFAULT_VOICE_START_TONE_ENABLED = True
VOICE_CONSENT_VERSION = 1
OFFICIAL_LOGIN_CONSENT_VERSION = 1
OFFICIAL_LOGIN_TERMS_READ_DATE = "2026-11-08"
BROWSER_MODE_CONSENT_VERSION = 1
BROWSER_MODE_TERMS_READ_DATE = "2026-11-08"
DEFAULT_BROWSER_CLIPBOARD_AUTO_CLEAR = True
DEFAULT_BROWSER_CLIPBOARD_CLEAR_SECONDS = 60
MAX_INTERFACE_NAME_LENGTH = 32
MAX_SOFTWARE_NAME_LENGTH = 48
DEFAULT_BACKGROUND_MODE = "cover"
DEFAULT_BACKGROUND_BLUR = 8
DEFAULT_BACKGROUND_DIM = 55
MIN_BACKGROUND_DIM = 20
MAX_BACKGROUND_DIM = 80


class ConfigError(RuntimeError):
    """表示配置文件无法读取或内容不合法。"""


@dataclass(frozen=True)
class WindowGeometry:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class AssistantBallPosition:
    x: int
    y: int


@dataclass(frozen=True)
class PersonalizationConfig:
    interface_name: str = ""
    software_name: str = ""
    background_asset: str = ""
    background_mode: str = DEFAULT_BACKGROUND_MODE
    background_blur: int = DEFAULT_BACKGROUND_BLUR
    background_dim: int = DEFAULT_BACKGROUND_DIM
    app_icon_asset: str = ""
    title_logo_asset: str = ""
    ball_image_asset: str = ""


@dataclass(frozen=True)
class AppConfig:
    """应用的非敏感配置。API Key 不存放在这里。"""

    schema_version: int = CONFIG_SCHEMA_VERSION
    access_method: str = DEFAULT_ACCESS_METHOD
    work_mode: str = DEFAULT_WORK_MODE
    hotkeys: dict[str, str] = field(default_factory=default_hotkeys)
    auto_send_screenshot: bool = False
    image_max_edge: int = DEFAULT_IMAGE_MAX_EDGE
    no_focus_mode: bool = False
    opacity: float = DEFAULT_OPACITY
    acrylic_enabled: bool = DEFAULT_ACRYLIC_ENABLED
    compact_mode: bool = DEFAULT_COMPACT_MODE
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    window_geometry: WindowGeometry | None = None
    assistant_ball_persistent: bool = DEFAULT_ASSISTANT_BALL_PERSISTENT
    assistant_auto_hide_seconds: int = DEFAULT_ASSISTANT_AUTO_HIDE_SECONDS
    assistant_ball_size: int = DEFAULT_ASSISTANT_BALL_SIZE
    assistant_ball_position: AssistantBallPosition | None = None
    screen_recognition_auto_send: bool = (
        DEFAULT_SCREEN_RECOGNITION_AUTO_SEND
    )
    screen_recognition_prompt: str = DEFAULT_SCREEN_RECOGNITION_PROMPT
    screen_recognition_image_max_edge: int = (
        DEFAULT_SCREEN_RECOGNITION_IMAGE_MAX_EDGE
    )
    screen_recognition_consent_version: int = 0
    voice_enabled: bool = DEFAULT_VOICE_ENABLED
    voice_auto_listen: bool = DEFAULT_VOICE_AUTO_LISTEN
    voice_auto_send: bool = DEFAULT_VOICE_AUTO_SEND
    voice_language: str = DEFAULT_VOICE_LANGUAGE
    voice_microphone_device: str = DEFAULT_VOICE_MICROPHONE_DEVICE
    voice_silence_seconds: float = DEFAULT_VOICE_SILENCE_SECONDS
    voice_max_record_seconds: int = DEFAULT_VOICE_MAX_RECORD_SECONDS
    voice_start_tone_enabled: bool = DEFAULT_VOICE_START_TONE_ENABLED
    voice_consent_version: int = 0
    official_login_consent_version: int = 0
    official_login_terms_read_date: str = ""
    official_login_consent_at: str = ""
    browser_mode_consent_version: int = 0
    browser_mode_terms_read_date: str = ""
    browser_mode_consent_at: str = ""
    browser_clipboard_auto_clear_enabled: bool = (
        DEFAULT_BROWSER_CLIPBOARD_AUTO_CLEAR
    )
    browser_clipboard_clear_seconds: int = (
        DEFAULT_BROWSER_CLIPBOARD_CLEAR_SECONDS
    )
    browser_screen_capture_consent_version: int = 0
    browser_voice_consent_version: int = 0
    personalization: PersonalizationConfig = field(
        default_factory=PersonalizationConfig
    )

    def __post_init__(self) -> None:
        merged = default_hotkeys()
        merged.update(self.hotkeys)
        object.__setattr__(self, "hotkeys", merged)

    @property
    def hotkey(self) -> str:
        return self.hotkeys["chat"]

    @property
    def screenshot_hotkey(self) -> str:
        return self.hotkeys["screenshot"]


def get_config_directory() -> Path:
    """返回当前用户的本地配置目录。"""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_DIRECTORY_NAME
    return Path.home() / ".config" / APP_DIRECTORY_NAME


def get_config_path() -> Path:
    """返回配置文件完整路径。"""
    return get_config_directory() / CONFIG_FILE_NAME


def sanitize_display_name(value: str, max_length: int) -> str:
    """Trim UI names and remove control/format characters without rich text."""
    normalized = unicodedata.normalize("NFC", str(value))
    cleaned: list[str] = []
    for character in normalized:
        category = unicodedata.category(character)
        if category in {"Cc", "Cf"}:
            continue
        cleaned.append(character)
    return "".join(cleaned).strip()[:max_length]


def _validate_asset_id(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"personalization.{field_name} 必须是字符串。")
    normalized = value.strip()
    if normalized and not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", normalized):
        raise ConfigError(
            f"personalization.{field_name} 包含非法字符。"
        )
    return normalized


def _parse_personalization(raw: object) -> PersonalizationConfig:
    if raw is None:
        return PersonalizationConfig()
    if not isinstance(raw, dict):
        raise ConfigError("配置项 personalization 必须是对象。")
    background = raw.get("background", {})
    icons = raw.get("icons", {})
    if not isinstance(background, dict) or not isinstance(icons, dict):
        raise ConfigError(
            "personalization.background 和 personalization.icons 必须是对象。"
        )
    mode = background.get("mode", DEFAULT_BACKGROUND_MODE)
    if mode not in {"cover", "contain", "center"}:
        raise ConfigError(
            "personalization.background.mode 必须是 cover、contain 或 center。"
        )
    blur = background.get("blur", DEFAULT_BACKGROUND_BLUR)
    dim = background.get("dim", DEFAULT_BACKGROUND_DIM)
    if (
        isinstance(blur, bool)
        or not isinstance(blur, int)
        or not 0 <= blur <= 20
    ):
        raise ConfigError(
            "personalization.background.blur 必须是 0 到 20 的整数。"
        )
    if (
        isinstance(dim, bool)
        or not isinstance(dim, int)
        or not MIN_BACKGROUND_DIM <= dim <= MAX_BACKGROUND_DIM
    ):
        raise ConfigError(
            "personalization.background.dim 必须是 20 到 80 的整数。"
        )
    interface_name = raw.get("interface_name", "")
    software_name = raw.get("software_name", "")
    if not isinstance(interface_name, str) or not isinstance(software_name, str):
        raise ConfigError(
            "personalization.interface_name 和 software_name 必须是字符串。"
        )
    return PersonalizationConfig(
        interface_name=sanitize_display_name(
            interface_name,
            MAX_INTERFACE_NAME_LENGTH,
        ),
        software_name=sanitize_display_name(
            software_name,
            MAX_SOFTWARE_NAME_LENGTH,
        ),
        background_asset=_validate_asset_id(
            background.get("asset", ""),
            "background.asset",
        ),
        background_mode=mode,
        background_blur=blur,
        background_dim=dim,
        app_icon_asset=_validate_asset_id(
            icons.get("app", ""),
            "icons.app",
        ),
        title_logo_asset=_validate_asset_id(
            icons.get("title_logo", ""),
            "icons.title_logo",
        ),
        ball_image_asset=_validate_asset_id(
            icons.get("ball", ""),
            "icons.ball",
        ),
    )


def _config_data(config: AppConfig) -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "access_method": config.access_method,
        "work_mode": config.work_mode,
        "hotkeys": dict(config.hotkeys),
        "hotkey": config.hotkey,
        "screenshot_hotkey": config.screenshot_hotkey,
        "auto_send_screenshot": config.auto_send_screenshot,
        "image_max_edge": config.image_max_edge,
        "no_focus_mode": config.no_focus_mode,
        "opacity": config.opacity,
        "acrylic_enabled": config.acrylic_enabled,
        "compact_mode": config.compact_mode,
        "base_url": validate_base_url(config.base_url),
        "model": config.model.strip(),
        "timeout_seconds": config.timeout_seconds,
        "window_geometry": (
            {
                "x": config.window_geometry.x,
                "y": config.window_geometry.y,
                "width": config.window_geometry.width,
                "height": config.window_geometry.height,
            }
            if config.window_geometry is not None
            else None
        ),
        "assistant_ball_persistent": config.assistant_ball_persistent,
        "assistant_auto_hide_seconds": config.assistant_auto_hide_seconds,
        "assistant_ball_size": config.assistant_ball_size,
        "screen_recognition_auto_send": (
            config.screen_recognition_auto_send
        ),
        "screen_recognition_prompt": config.screen_recognition_prompt,
        "screen_recognition_image_max_edge": (
            config.screen_recognition_image_max_edge
        ),
        "screen_recognition_consent_version": (
            config.screen_recognition_consent_version
        ),
        "voice_enabled": config.voice_enabled,
        "voice_auto_listen": config.voice_auto_listen,
        "voice_auto_send": config.voice_auto_send,
        "voice_language": config.voice_language,
        "voice_microphone_device": config.voice_microphone_device,
        "voice_silence_seconds": config.voice_silence_seconds,
        "voice_max_record_seconds": config.voice_max_record_seconds,
        "voice_start_tone_enabled": config.voice_start_tone_enabled,
        "voice_consent_version": config.voice_consent_version,
        "official_login_consent_version": (
            config.official_login_consent_version
        ),
        "official_login_terms_read_date": (
            config.official_login_terms_read_date
        ),
        "official_login_consent_at": config.official_login_consent_at,
        "browser_mode_consent_version": (
            config.browser_mode_consent_version
        ),
        "browser_mode_terms_read_date": (
            config.browser_mode_terms_read_date
        ),
        "browser_mode_consent_at": config.browser_mode_consent_at,
        "browser_clipboard_auto_clear_enabled": (
            config.browser_clipboard_auto_clear_enabled
        ),
        "browser_clipboard_clear_seconds": (
            config.browser_clipboard_clear_seconds
        ),
        "browser_screen_capture_consent_version": (
            config.browser_screen_capture_consent_version
        ),
        "browser_voice_consent_version": (
            config.browser_voice_consent_version
        ),
        "personalization": {
            "interface_name": config.personalization.interface_name,
            "software_name": config.personalization.software_name,
            "background": {
                "asset": config.personalization.background_asset,
                "mode": config.personalization.background_mode,
                "blur": config.personalization.background_blur,
                "dim": config.personalization.background_dim,
            },
            "icons": {
                "app": config.personalization.app_icon_asset,
                "title_logo": config.personalization.title_logo_asset,
                "ball": config.personalization.ball_image_asset,
            },
        },
        "assistant_ball_position": (
            {
                "x": config.assistant_ball_position.x,
                "y": config.assistant_ball_position.y,
            }
            if config.assistant_ball_position is not None
            else None
        ),
    }


def _atomic_write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _merge_preserving_unknown(
    existing: object,
    updates: dict[str, object],
) -> dict[str, object]:
    merged = dict(existing) if isinstance(existing, dict) else {}
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_preserving_unknown(merged[key], value)
        else:
            merged[key] = value
    return merged


def _write_default_config(path: Path) -> None:
    _atomic_write_json(path, _config_data(AppConfig()))


def validate_base_url(base_url: str) -> str:
    """Allow only the official DeepSeek API origin."""
    normalized = base_url.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme != "https"
        or parsed.hostname != OFFICIAL_API_HOST
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigError(
            "当前版本仅允许官方 API 地址 https://api.deepseek.com。"
        )
    return DEFAULT_BASE_URL


def _parse_choice(
    raw: dict[str, object],
    name: str,
    default: str,
    allowed: set[str],
) -> str:
    value = raw.get(name, default)
    if not isinstance(value, str) or value not in allowed:
        raise ConfigError(
            f"配置项 {name} 必须是以下值之一：{', '.join(sorted(allowed))}。"
        )
    return value


def load_config(path: Path | None = None) -> AppConfig:
    """读取配置；文件不存在时创建一个默认配置文件。"""
    config_path = path or get_config_path()

    if not config_path.exists():
        _write_default_config(config_path)

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"无法读取配置文件 {config_path}：{exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"配置文件 {config_path} 的顶层必须是 JSON 对象。")

    schema_version = raw.get("schema_version", 1)
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version not in {1, CONFIG_SCHEMA_VERSION}
    ):
        raise ConfigError("配置项 schema_version 必须是 1 或 2。")
    needs_migration = schema_version < CONFIG_SCHEMA_VERSION

    access_method = _parse_choice(
        raw,
        "access_method",
        DEFAULT_ACCESS_METHOD,
        {"api", "official_login", "official_browser"},
    )
    work_mode = _parse_choice(
        raw,
        "work_mode",
        DEFAULT_WORK_MODE,
        {"quiz", "global_assistant"},
    )

    raw_hotkeys = raw.get("hotkeys")
    if raw_hotkeys is not None and not isinstance(raw_hotkeys, dict):
        raise ConfigError("配置项 hotkeys 必须是对象。")
    hotkeys: dict[str, str] = {}
    for definition in HOTKEY_DEFINITIONS:
        if isinstance(raw_hotkeys, dict):
            value = raw_hotkeys.get(definition.key)
        elif definition.key == "chat":
            value = raw.get("hotkey", DEFAULT_HOTKEY)
        elif definition.key == "screenshot":
            value = raw.get(
                "screenshot_hotkey",
                DEFAULT_SCREENSHOT_HOTKEY,
            )
        else:
            value = None
        if value is None:
            value = definition.default
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(
                f"配置项 hotkeys.{definition.key} 必须是非空字符串。"
            )
        hotkeys[definition.key] = value.strip()

    normalized_hotkeys = [value.lower() for value in hotkeys.values()]
    if len(set(normalized_hotkeys)) != len(normalized_hotkeys):
        raise ConfigError("所有功能热键不能使用相同的组合键。")

    auto_send_screenshot = raw.get("auto_send_screenshot", False)
    if not isinstance(auto_send_screenshot, bool):
        raise ConfigError("配置项 auto_send_screenshot 必须是 true 或 false。")

    image_max_edge = raw.get("image_max_edge", DEFAULT_IMAGE_MAX_EDGE)
    if (
        isinstance(image_max_edge, bool)
        or not isinstance(image_max_edge, int)
        or not 512 <= image_max_edge <= 4096
    ):
        raise ConfigError("image_max_edge 必须是 512 到 4096 之间的整数。")

    no_focus_mode = raw.get("no_focus_mode", False)
    if not isinstance(no_focus_mode, bool):
        raise ConfigError("配置项 no_focus_mode 必须是 true 或 false。")

    opacity = raw.get("opacity", DEFAULT_OPACITY)
    if (
        isinstance(opacity, bool)
        or not isinstance(opacity, (int, float))
        or not 0.0 <= float(opacity) <= 1.0
    ):
        raise ConfigError("opacity 必须是 0.0 到 1.0 之间的数字。")

    acrylic_enabled = raw.get("acrylic_enabled", DEFAULT_ACRYLIC_ENABLED)
    if not isinstance(acrylic_enabled, bool):
        raise ConfigError("配置项 acrylic_enabled 必须是 true 或 false。")

    compact_mode = raw.get("compact_mode", DEFAULT_COMPACT_MODE)
    if not isinstance(compact_mode, bool):
        raise ConfigError("配置项 compact_mode 必须是 true 或 false。")

    base_url = raw.get("base_url", DEFAULT_BASE_URL)
    if not isinstance(base_url, str):
        raise ConfigError("配置项 base_url 必须是字符串。")

    model = raw.get("model", DEFAULT_MODEL)
    if not isinstance(model, str) or not model.strip():
        raise ConfigError("配置项 model 必须是非空字符串。")

    timeout_seconds = raw.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or not 1 <= timeout_seconds <= 300
    ):
        raise ConfigError("配置项 timeout_seconds 必须是 1 到 300 之间的整数。")

    raw_geometry = raw.get("window_geometry")
    window_geometry = None
    if raw_geometry is not None:
        if not isinstance(raw_geometry, dict):
            raise ConfigError("window_geometry 必须是对象或 null。")
        try:
            geometry_values = {
                name: raw_geometry[name]
                for name in ("x", "y", "width", "height")
            }
        except KeyError as exc:
            raise ConfigError("window_geometry 缺少 x、y、width 或 height。") from exc
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in geometry_values.values()
        ):
            raise ConfigError("window_geometry 的所有字段必须是整数。")
        if geometry_values["width"] < 380 or geometry_values["height"] < 460:
            raise ConfigError("window_geometry 尺寸不能小于 380 x 460。")
        window_geometry = WindowGeometry(**geometry_values)

    assistant_ball_persistent = raw.get(
        "assistant_ball_persistent",
        DEFAULT_ASSISTANT_BALL_PERSISTENT,
    )
    if not isinstance(assistant_ball_persistent, bool):
        raise ConfigError(
            "配置项 assistant_ball_persistent 必须是 true 或 false。"
        )

    assistant_auto_hide_seconds = raw.get(
        "assistant_auto_hide_seconds",
        DEFAULT_ASSISTANT_AUTO_HIDE_SECONDS,
    )
    if (
        isinstance(assistant_auto_hide_seconds, bool)
        or not isinstance(assistant_auto_hide_seconds, int)
        or not 5 <= assistant_auto_hide_seconds <= 600
    ):
        raise ConfigError(
            "assistant_auto_hide_seconds 必须是 5 到 600 之间的整数。"
        )

    assistant_ball_size = raw.get(
        "assistant_ball_size",
        DEFAULT_ASSISTANT_BALL_SIZE,
    )
    if (
        isinstance(assistant_ball_size, bool)
        or not isinstance(assistant_ball_size, int)
        or not MIN_ASSISTANT_BALL_SIZE
        <= assistant_ball_size
        <= MAX_ASSISTANT_BALL_SIZE
    ):
        raise ConfigError(
            "assistant_ball_size 必须是 40 到 160 之间的整数。"
        )

    screen_recognition_auto_send = raw.get(
        "screen_recognition_auto_send",
        DEFAULT_SCREEN_RECOGNITION_AUTO_SEND,
    )
    if not isinstance(screen_recognition_auto_send, bool):
        raise ConfigError(
            "screen_recognition_auto_send 必须是 true 或 false。"
        )

    screen_recognition_prompt = raw.get(
        "screen_recognition_prompt",
        DEFAULT_SCREEN_RECOGNITION_PROMPT,
    )
    if (
        not isinstance(screen_recognition_prompt, str)
        or not screen_recognition_prompt.strip()
    ):
        raise ConfigError(
            "screen_recognition_prompt 必须是非空字符串。"
        )

    screen_recognition_image_max_edge = raw.get(
        "screen_recognition_image_max_edge",
        DEFAULT_SCREEN_RECOGNITION_IMAGE_MAX_EDGE,
    )
    if (
        isinstance(screen_recognition_image_max_edge, bool)
        or not isinstance(screen_recognition_image_max_edge, int)
        or not 512 <= screen_recognition_image_max_edge <= 4096
    ):
        raise ConfigError(
            "screen_recognition_image_max_edge 必须是 512 到 4096 "
            "之间的整数。"
        )

    screen_recognition_consent_version = raw.get(
        "screen_recognition_consent_version",
        0,
    )
    if (
        isinstance(screen_recognition_consent_version, bool)
        or not isinstance(screen_recognition_consent_version, int)
        or not 0 <= screen_recognition_consent_version <= 1
    ):
        raise ConfigError(
            "screen_recognition_consent_version 必须是 0 或 1。"
        )

    voice_enabled = raw.get("voice_enabled", DEFAULT_VOICE_ENABLED)
    if not isinstance(voice_enabled, bool):
        raise ConfigError("voice_enabled 必须是 true 或 false。")

    voice_auto_listen = raw.get(
        "voice_auto_listen",
        DEFAULT_VOICE_AUTO_LISTEN,
    )
    if not isinstance(voice_auto_listen, bool):
        raise ConfigError("voice_auto_listen 必须是 true 或 false。")

    voice_auto_send = raw.get(
        "voice_auto_send",
        DEFAULT_VOICE_AUTO_SEND,
    )
    if not isinstance(voice_auto_send, bool):
        raise ConfigError("voice_auto_send 必须是 true 或 false。")

    voice_language = raw.get(
        "voice_language",
        DEFAULT_VOICE_LANGUAGE,
    )
    if voice_language not in {"zh", "auto", "en", "ja", "ko", "yue"}:
        raise ConfigError(
            "voice_language 必须是 zh、auto、en、ja、ko 或 yue。"
        )

    voice_microphone_device = raw.get(
        "voice_microphone_device",
        DEFAULT_VOICE_MICROPHONE_DEVICE,
    )
    if not isinstance(voice_microphone_device, str):
        raise ConfigError("voice_microphone_device 必须是字符串。")

    voice_silence_seconds = raw.get(
        "voice_silence_seconds",
        DEFAULT_VOICE_SILENCE_SECONDS,
    )
    if (
        isinstance(voice_silence_seconds, bool)
        or not isinstance(voice_silence_seconds, (int, float))
        or not 0.3 <= float(voice_silence_seconds) <= 5.0
    ):
        raise ConfigError(
            "voice_silence_seconds 必须是 0.3 到 5.0 之间的数字。"
        )

    voice_max_record_seconds = raw.get(
        "voice_max_record_seconds",
        DEFAULT_VOICE_MAX_RECORD_SECONDS,
    )
    if (
        isinstance(voice_max_record_seconds, bool)
        or not isinstance(voice_max_record_seconds, int)
        or not 5 <= voice_max_record_seconds <= 120
    ):
        raise ConfigError(
            "voice_max_record_seconds 必须是 5 到 120 之间的整数。"
        )

    voice_start_tone_enabled = raw.get(
        "voice_start_tone_enabled",
        DEFAULT_VOICE_START_TONE_ENABLED,
    )
    if not isinstance(voice_start_tone_enabled, bool):
        raise ConfigError(
            "voice_start_tone_enabled 必须是 true 或 false。"
        )

    voice_consent_version = raw.get("voice_consent_version", 0)
    if (
        isinstance(voice_consent_version, bool)
        or not isinstance(voice_consent_version, int)
        or not 0 <= voice_consent_version <= VOICE_CONSENT_VERSION
    ):
        raise ConfigError("voice_consent_version 必须是 0 或 1。")

    official_login_consent_version = raw.get(
        "official_login_consent_version",
        0,
    )
    if (
        isinstance(official_login_consent_version, bool)
        or not isinstance(official_login_consent_version, int)
        or not 0
        <= official_login_consent_version
        <= OFFICIAL_LOGIN_CONSENT_VERSION
    ):
        raise ConfigError(
            "official_login_consent_version 必须是 0 或 1。"
        )
    official_login_terms_read_date = raw.get(
        "official_login_terms_read_date",
        "",
    )
    if not isinstance(official_login_terms_read_date, str):
        raise ConfigError(
            "official_login_terms_read_date 必须是字符串。"
        )
    official_login_consent_at = raw.get(
        "official_login_consent_at",
        "",
    )
    if not isinstance(official_login_consent_at, str):
        raise ConfigError("official_login_consent_at 必须是字符串。")
    browser_mode_consent_version = raw.get(
        "browser_mode_consent_version",
        0,
    )
    if (
        isinstance(browser_mode_consent_version, bool)
        or not isinstance(browser_mode_consent_version, int)
        or not 0 <= browser_mode_consent_version
        <= BROWSER_MODE_CONSENT_VERSION
    ):
        raise ConfigError("browser_mode_consent_version 必须是 0 或 1。")
    browser_mode_terms_read_date = raw.get(
        "browser_mode_terms_read_date",
        "",
    )
    if not isinstance(browser_mode_terms_read_date, str):
        raise ConfigError("browser_mode_terms_read_date 必须是字符串。")
    browser_mode_consent_at = raw.get("browser_mode_consent_at", "")
    if not isinstance(browser_mode_consent_at, str):
        raise ConfigError("browser_mode_consent_at 必须是字符串。")
    browser_clipboard_auto_clear_enabled = raw.get(
        "browser_clipboard_auto_clear_enabled",
        DEFAULT_BROWSER_CLIPBOARD_AUTO_CLEAR,
    )
    if not isinstance(browser_clipboard_auto_clear_enabled, bool):
        raise ConfigError(
            "browser_clipboard_auto_clear_enabled 必须是 true 或 false。"
        )
    browser_clipboard_clear_seconds = raw.get(
        "browser_clipboard_clear_seconds",
        DEFAULT_BROWSER_CLIPBOARD_CLEAR_SECONDS,
    )
    if (
        isinstance(browser_clipboard_clear_seconds, bool)
        or not isinstance(browser_clipboard_clear_seconds, int)
        or not 5 <= browser_clipboard_clear_seconds <= 300
    ):
        raise ConfigError(
            "browser_clipboard_clear_seconds 必须是 5 到 300 之间的整数。"
        )
    browser_screen_capture_consent_version = raw.get(
        "browser_screen_capture_consent_version",
        0,
    )
    if (
        isinstance(browser_screen_capture_consent_version, bool)
        or not isinstance(browser_screen_capture_consent_version, int)
        or not 0 <= browser_screen_capture_consent_version <= 1
    ):
        raise ConfigError(
            "browser_screen_capture_consent_version 必须是 0 或 1。"
        )
    browser_voice_consent_version = raw.get(
        "browser_voice_consent_version",
        0,
    )
    if (
        isinstance(browser_voice_consent_version, bool)
        or not isinstance(browser_voice_consent_version, int)
        or not 0 <= browser_voice_consent_version <= 1
    ):
        raise ConfigError(
            "browser_voice_consent_version 必须是 0 或 1。"
        )

    personalization = _parse_personalization(raw.get("personalization"))

    raw_assistant_position = raw.get("assistant_ball_position")
    assistant_ball_position = None
    if raw_assistant_position is not None:
        if not isinstance(raw_assistant_position, dict):
            raise ConfigError(
                "assistant_ball_position 必须是对象或 null。"
            )
        try:
            position_values = {
                name: raw_assistant_position[name]
                for name in ("x", "y")
            }
        except KeyError as exc:
            raise ConfigError(
                "assistant_ball_position 缺少 x 或 y。"
            ) from exc
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in position_values.values()
        ):
            raise ConfigError(
                "assistant_ball_position 的 x、y 必须是整数。"
            )
        assistant_ball_position = AssistantBallPosition(**position_values)

    config = AppConfig(
        schema_version=CONFIG_SCHEMA_VERSION,
        access_method=access_method,
        work_mode=work_mode,
        hotkeys=hotkeys,
        auto_send_screenshot=auto_send_screenshot,
        image_max_edge=image_max_edge,
        no_focus_mode=no_focus_mode,
        opacity=clamp_glass_opacity(float(opacity)),
        acrylic_enabled=acrylic_enabled,
        compact_mode=compact_mode,
        base_url=validate_base_url(base_url),
        model=model.strip(),
        timeout_seconds=timeout_seconds,
        window_geometry=window_geometry,
        assistant_ball_persistent=assistant_ball_persistent,
        assistant_auto_hide_seconds=assistant_auto_hide_seconds,
        assistant_ball_size=assistant_ball_size,
        assistant_ball_position=assistant_ball_position,
        screen_recognition_auto_send=screen_recognition_auto_send,
        screen_recognition_prompt=screen_recognition_prompt.strip(),
        screen_recognition_image_max_edge=(
            screen_recognition_image_max_edge
        ),
        screen_recognition_consent_version=(
            screen_recognition_consent_version
        ),
        voice_enabled=voice_enabled,
        voice_auto_listen=voice_auto_listen,
        voice_auto_send=voice_auto_send,
        voice_language=voice_language,
        voice_microphone_device=voice_microphone_device.strip(),
        voice_silence_seconds=float(voice_silence_seconds),
        voice_max_record_seconds=voice_max_record_seconds,
        voice_start_tone_enabled=voice_start_tone_enabled,
        voice_consent_version=voice_consent_version,
        official_login_consent_version=official_login_consent_version,
        official_login_terms_read_date=official_login_terms_read_date.strip(),
        official_login_consent_at=official_login_consent_at.strip(),
        browser_mode_consent_version=browser_mode_consent_version,
        browser_mode_terms_read_date=browser_mode_terms_read_date.strip(),
        browser_mode_consent_at=browser_mode_consent_at.strip(),
        browser_clipboard_auto_clear_enabled=(
            browser_clipboard_auto_clear_enabled
        ),
        browser_clipboard_clear_seconds=browser_clipboard_clear_seconds,
        browser_screen_capture_consent_version=(
            browser_screen_capture_consent_version
        ),
        browser_voice_consent_version=browser_voice_consent_version,
        personalization=personalization,
    )
    if needs_migration:
        backup_path = config_path.with_name("config.json.v1.bak")
        if not backup_path.exists():
            try:
                backup_path.write_bytes(config_path.read_bytes())
            except OSError as exc:
                raise ConfigError(
                    f"无法创建旧配置备份 {backup_path}：{exc}"
                ) from exc
        migrated = _merge_preserving_unknown(
            raw,
            _config_data(config),
        )
        try:
            _atomic_write_json(config_path, migrated)
        except OSError as exc:
            raise ConfigError(
                f"无法升级配置文件 {config_path}：{exc}"
            ) from exc
    return config


def save_config(config: AppConfig, path: Path | None = None) -> None:
    """保存非敏感配置，不写入 API Key。"""
    config_path = path or get_config_path()
    existing: object = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(
                f"无法读取现有配置文件以保留未知字段：{exc}"
            ) from exc
    _atomic_write_json(
        config_path,
        _merge_preserving_unknown(existing, _config_data(config)),
    )
