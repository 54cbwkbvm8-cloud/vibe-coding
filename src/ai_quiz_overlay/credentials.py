"""API Key 的 DPAPI 加密存储，不写入普通配置。"""

from __future__ import annotations

from pathlib import Path

from .config import get_config_directory
from .win32.dpapi import DPAPIError, protect_bytes, unprotect_bytes


API_KEY_FILE_NAME = "api_key.bin"


class CredentialError(RuntimeError):
    """表示 API Key 无法安全保存或读取。"""


def get_api_key_path() -> Path:
    return get_config_directory() / API_KEY_FILE_NAME


def save_api_key(api_key: str, path: Path | None = None) -> None:
    """保存非空 API Key；明文只存在于内存中。"""
    clean_key = api_key.strip()
    if not clean_key:
        raise CredentialError("API Key 不能为空。")

    key_path = path or get_api_key_path()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        encrypted = protect_bytes(clean_key.encode("utf-8"))
    except DPAPIError as exc:
        raise CredentialError(str(exc)) from exc

    temporary_path = key_path.with_suffix(".tmp")
    temporary_path.write_bytes(encrypted)
    temporary_path.replace(key_path)


def load_api_key(path: Path | None = None) -> str | None:
    """读取并解密 API Key；文件不存在时返回 None。"""
    key_path = path or get_api_key_path()
    if not key_path.exists():
        return None

    try:
        decrypted = unprotect_bytes(key_path.read_bytes())
        return decrypted.decode("utf-8")
    except (OSError, UnicodeDecodeError, DPAPIError) as exc:
        raise CredentialError(
            "已保存的 API Key 无法解密。请重新在设置中输入 Key。"
        ) from exc


def delete_api_key(path: Path | None = None) -> None:
    """删除本地 API Key 密文文件。"""
    key_path = path or get_api_key_path()
    if key_path.exists():
        key_path.unlink()
