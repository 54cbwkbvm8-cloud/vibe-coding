"""Registry for mutually independent access methods."""

from __future__ import annotations

from dataclasses import dataclass

from .chat_provider import ChatProvider, ProviderUnavailableError
from .deepseek_provider import DeepSeekApiProvider
from .official_web_provider import OfficialWebProvider


@dataclass(frozen=True)
class AccessMethodDefinition:
    key: str
    label: str
    enabled: bool
    unavailable_reason: str = ""


ACCESS_METHODS = (
    AccessMethodDefinition(
        key="api",
        label="API 接入",
        enabled=True,
    ),
    AccessMethodDefinition(
        key="official_login",
        label="官网账号接入（实验性）",
        enabled=True,
        unavailable_reason="需要先导入实验性官网组件并接受风险说明",
    ),
    AccessMethodDefinition(
        key="official_browser",
        label="DeepSeek 官网（浏览器模式）",
        enabled=True,
        unavailable_reason="需要先导入实验性官网组件并接受浏览器模式风险说明",
    ),
)

ACCESS_METHOD_BY_KEY = {
    definition.key: definition
    for definition in ACCESS_METHODS
}


def create_chat_provider(access_method: str) -> ChatProvider:
    if access_method == "api":
        return DeepSeekApiProvider()
    if access_method == "official_login":
        return OfficialWebProvider()
    if access_method == "official_browser":
        raise ProviderUnavailableError(
            "浏览器模式不是 ChatProvider，不会发送 API 或读取官网页面。"
        )
    definition = ACCESS_METHOD_BY_KEY.get(access_method)
    if definition is None:
        raise ProviderUnavailableError("未知的接入方式。")
    raise ProviderUnavailableError(
        f"{definition.label}尚未启用：{definition.unavailable_reason}。"
    )
