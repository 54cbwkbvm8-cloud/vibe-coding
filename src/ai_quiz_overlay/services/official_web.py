"""Experimental official-account access policy and lifecycle constants."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime

from ..branding import APP_VERSION
from ..config import (
    AppConfig,
    BROWSER_MODE_CONSENT_VERSION,
    BROWSER_MODE_TERMS_READ_DATE,
    OFFICIAL_LOGIN_CONSENT_VERSION,
    OFFICIAL_LOGIN_TERMS_READ_DATE,
)


OFFICIAL_LOGIN_RISK_VERSION = OFFICIAL_LOGIN_CONSENT_VERSION
BROWSER_MODE_RISK_VERSION = BROWSER_MODE_CONSENT_VERSION
OFFICIAL_LOGIN_TERMS_URL = (
    "https://cdn.deepseek.com/policies/zh-CN/deepseek-terms-of-use.html"
)
OFFICIAL_LOGIN_PRIVACY_URL = (
    "https://cdn.deepseek.com/policies/zh-CN/deepseek-privacy-policy.html"
)
OFFICIAL_LOGIN_COMPONENT_ID = "official-web"
OFFICIAL_LOGIN_COMPONENT_VERSION = "13c-1"
OFFICIAL_LOGIN_COMPONENT_APP_VERSION = APP_VERSION
OFFICIAL_LOGIN_SESSION_DIRECTORY = "web_session"


@dataclass(frozen=True)
class RiskItem:
    title: str
    body: str


BROWSER_MODE_RISK_ITEMS = (
    RiskItem(
        "1. 协议风险",
        "重新核对的 DeepSeek 用户协议第 3.5 条第（3）项限制通过机器人、"
        "爬虫或其他自动设置抓取、复制本服务内容；第 8.1 条规定，若认为"
        "你违反协议，服务方可以限制账号功能、暂停使用、关闭账号或删除内容。",
    ),
    RiskItem(
        "2. 非官方客户端",
        "本软件与 DeepSeek 无隶属、代理、合作或背书关系，本模式不是"
        "DeepSeek 官方客户端，也不代表官网授权第三方封装。",
    ),
    RiskItem(
        "3. 网页权限边界",
        "本模式只做浏览器显示和普通导航，不注入脚本、不读取页面内容或"
        "Cookie、不自动填表、不自动点击发送、不修改网页样式或 User-Agent。"
        "但“不读取页面”不等于官网一定允许嵌入。",
    ),
    RiskItem(
        "4. 登录数据",
        "登录状态保存在本机：%APPDATA%\\AIQuizOverlay\\web_session。"
        "能访问这台电脑的人或程序可能使用该状态。不要在公用电脑使用。",
    ),
    RiskItem(
        "5. 隐私",
        "你在官网页面输入的消息会进入 DeepSeek 官网账号历史。按官网隐私"
        "政策，输入输出可能用于优化，除非你在官网关闭相关选项。不要向"
        "官网发送密码、验证码、Token、财务或他人敏感信息。",
    ),
    RiskItem(
        "6. 账号风险",
        "账号可能被限制、暂停或关闭，历史对话和额度可能丢失，申诉不一定"
        "成功。建议只使用不重要的账号。",
    ),
    RiskItem(
        "7. 剪贴板辅助",
        "截图和语音文字会短暂进入系统剪贴板；请在官网页面自行按 Ctrl+V，"
        "并自行确认和发送。软件不会自动粘贴或自动发送。",
    ),
    RiskItem(
        "8. 第三方链接和登录",
        "当前版本的内嵌窗口提供手机号登录和微信扫码入口，可用：手机号、"
        "微信扫码。Apple 登录需要跳转到 appleid.apple.com，当前白名单会"
        "把它交给系统默认浏览器，因此内嵌窗口不支持 Apple 登录。官网中的"
        "第三方链接和登录服务由第三方处理，本软件不负责；不会为了登录擅自"
        "扩大白名单。",
    ),
    RiskItem(
        "9. 使用者责任",
        "你应自行遵守所在地法律和官网条款，并自行承担使用后果，包括账号"
        "受限、数据丢失或服务中断。本摘要不是法律意见，不能改变官网协议"
        "的约束。",
    ),
)


OFFICIAL_LOGIN_RISK_ITEMS = (
    RiskItem(
        "1. 协议风险",
        "DeepSeek 用户协议第 3.5 条第（3）项写明："
        "“以任何方式（包括但不限于通过任何机器人、爬虫、其他自动设置、"
        "设置镜像）来抓取、复制本服务及其所包含的任何内容等。”"
        "第 8.1 条规定，若认为你违反协议，服务方可以限制账号功能、"
        "暂停使用、关闭账号、禁止重新注册或删除相关内容。",
    ),
    RiskItem(
        "2. 账号风险",
        "账号可能被限制、暂停或关闭，历史对话和额度可能丢失，"
        "申诉不一定成功。建议不要使用重要账号。",
    ),
    RiskItem(
        "3. 非官方、无支持",
        "本软件与 DeepSeek 无隶属关系，不是官方客户端。"
        "本功能可能随时被调整或移除；官网改版、验证码、限频和服务繁忙"
        "需要你手动处理。",
    ),
    RiskItem(
        "4. 隐私",
        "发送的消息会进入你的 DeepSeek 官网账号历史。按官网隐私政策，"
        "输入输出可能被用于优化，除非你在官网关闭相关选项。"
        "不要发送敏感信息；每个新官网对话的第一条消息会带一段模式说明。",
    ),
    RiskItem(
        "5. 本机登录数据",
        "登录状态保存在本机：%APPDATA%\\AIQuizOverlay\\web_session。"
        "能访问这台电脑的人或程序可能使用该状态。不要在公用电脑使用。"
        "设置中可以退出登录并清除全部登录数据。",
    ),
    RiskItem(
        "6. 功能限制",
        "可能不支持图片、停止生成、自定义系统提示词；回答由官网生成，"
        "质量和内容不受本软件控制，读取也可能不完整。",
    ),
    RiskItem(
        "7. 使用者责任",
        "你应自行遵守所在地法律和 DeepSeek 官网条款，并自行承担使用后果。"
        "本摘要不是法律意见，不能改变官网协议的约束。",
    ),
    RiskItem(
        "8. 免责声明摘要",
        "本功能按现状提供，不提供任何明示或暗示担保。与 DeepSeek 无隶属"
        "关系；因账号限制或关闭、数据丢失、经济或其他损失，软件作者和"
        "贡献者不承担责任。仅供个人学习研究，不用于商业用途。"
    ),
)


def consent_is_current(config: AppConfig) -> bool:
    return (
        config.official_login_consent_version
        == OFFICIAL_LOGIN_RISK_VERSION
        and config.official_login_terms_read_date
        == OFFICIAL_LOGIN_TERMS_READ_DATE
        and bool(config.official_login_consent_at.strip())
    )


def browser_consent_is_current(config: AppConfig) -> bool:
    return (
        config.browser_mode_consent_version == BROWSER_MODE_RISK_VERSION
        and config.browser_mode_terms_read_date
        == BROWSER_MODE_TERMS_READ_DATE
        and bool(config.browser_mode_consent_at.strip())
    )


def consent_timestamp_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def runtime_access_method(
    config: AppConfig,
    *,
    component_installed: bool = True,
    with_reason: bool = False,
):
    if config.access_method in {"official_login", "official_browser"}:
        valid_consent = (
            consent_is_current(config)
            if config.access_method == "official_login"
            else browser_consent_is_current(config)
        )
        if not valid_consent:
            reason = "官网接入的风险同意已失效，已回退到 API 接入。"
            return ("api", reason) if with_reason else "api"
        if not component_installed:
            reason = "实验性官网组件尚未导入，已回退到 API 接入。"
            return ("api", reason) if with_reason else "api"
    if with_reason:
        return config.access_method, ""
    return config.access_method


def official_web_ready(
    config: AppConfig,
    component_installed: bool,
    component_message: str = "",
) -> tuple[bool, str]:
    if not consent_is_current(config):
        return False, "请先阅读并接受官网账号接入风险说明。"
    if not component_installed:
        return False, component_message or "实验性官网组件尚未导入。"
    return True, "官网账号接入已就绪。"


def browser_mode_ready(
    config: AppConfig,
    component_installed: bool,
    component_message: str = "",
) -> tuple[bool, str]:
    if not browser_consent_is_current(config):
        return False, "请先阅读并接受浏览器模式风险说明。"
    if not component_installed:
        return False, component_message or "实验性官网组件尚未导入。"
    return True, "官网浏览器模式已就绪。"


def startup_access_config(
    config: AppConfig,
    *,
    component_installed: bool,
) -> tuple[AppConfig, str]:
    resolved, reason = runtime_access_method(
        config,
        component_installed=component_installed,
        with_reason=True,
    )
    if resolved == config.access_method:
        return config, ""
    updated = replace(config, access_method=resolved)
    if config.access_method == "official_login" and not consent_is_current(config):
        updated = replace(
            updated,
            official_login_consent_version=0,
            official_login_terms_read_date="",
            official_login_consent_at="",
        )
    if (
        config.access_method == "official_browser"
        and not browser_consent_is_current(config)
    ):
        updated = replace(
            updated,
            browser_mode_consent_version=0,
            browser_mode_terms_read_date="",
            browser_mode_consent_at="",
        )
    return updated, reason


def risk_text_plain() -> str:
    return "\n\n".join(
        f"{item.title}\n{item.body}"
        for item in OFFICIAL_LOGIN_RISK_ITEMS
    )
