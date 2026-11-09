"""当前已确认支持图片输入的模型。"""

from __future__ import annotations


VISION_MODELS = frozenset({"deepseek-flash"})


def image_model_error(model: str) -> str | None:
    """返回不支持的提示；None 表示可以发送图片。"""
    normalized = model.strip().lower()
    if normalized in VISION_MODELS:
        return None
    if normalized == "deepseek-v4-pro":
        return (
            "当前模型 deepseek-v4-pro 不支持图片输入。"
            "请在设置中改用 deepseek-flash。"
        )
    return (
        f"当前模型 {model} 未在已验证支持图片的模型列表中。"
        "当前版本固定使用 DeepSeek 官方 API，请改用 deepseek-flash。"
    )
