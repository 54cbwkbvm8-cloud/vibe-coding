"""DeepSeek HTTP 错误到中文提示的映射。"""

from __future__ import annotations

import json
import re


def redact_sensitive(text: str, secret: str | None = None) -> str:
    if secret:
        text = text.replace(secret, "[已隐藏]")
    return re.sub(
        r"base64,[A-Za-z0-9+/=\r\n]+",
        "base64,[图片数据已隐藏]",
        text,
    )


def _extract_provider_message(body: bytes | str, secret: str | None) -> str:
    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="replace")
    else:
        text = body

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return ""

    if not isinstance(parsed, dict):
        return ""
    error = parsed.get("error")
    if not isinstance(error, dict):
        return ""
    message = error.get("message")
    if not isinstance(message, str):
        return ""
    return redact_sensitive(message.strip(), secret)[:300]


def http_error_message(
    status_code: int,
    body: bytes | str,
    api_key: str | None = None,
) -> str:
    provider_message = _extract_provider_message(body, api_key)

    fixed_messages = {
        400: "请求格式不正确，请检查模型名和消息内容。",
        401: "API Key 无效或认证失败，请在设置中检查 Key。",
        402: "DeepSeek 账户余额不足，请到官方平台充值后重试。",
        403: "当前 API Key 无权访问该接口。",
        404: "接口地址或模型不存在，请检查 base_url 和模型名。",
        422: "请求参数不合法，请检查设置后重试。",
        429: "请求过于频繁或已达到限流，请稍后再试。",
        500: "DeepSeek 服务端发生错误，请稍后重试。",
        503: "DeepSeek 服务繁忙，请稍后重试。",
    }
    base_message = fixed_messages.get(
        status_code,
        f"DeepSeek 请求失败，HTTP 状态码：{status_code}。",
    )
    if provider_message:
        return f"{base_message}\n服务端说明：{provider_message}"
    return base_message
