"""Stage 13A provider contract placeholder for official web access."""

from __future__ import annotations

from .chat_provider import (
    ChatRequest,
    ProviderCapabilities,
    ProviderUnavailableError,
)


class OfficialWebProvider:
    provider_id = "official_login"
    display_name = "官网账号接入（实验性）"
    capabilities = ProviderCapabilities(
        streaming=True,
        images=False,
        login_required=True,
        stop_generation=False,
    )

    def image_support_error(self, _model: str) -> str | None:
        return (
            "官网账号接入当前不支持上传图片，请改用 API 接入，"
            "或用文字描述图片内容。"
        )

    def open_stream(self, _request: ChatRequest):
        raise ProviderUnavailableError(
            "阶段 13A 只完成登录基础设施，收发消息将在 13B 实现。"
        )
