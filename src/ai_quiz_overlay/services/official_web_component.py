"""Local-only component packaging, validation, import, and self-check."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import time
from typing import Callable
import uuid
import zipfile

from ..config import get_config_directory
from .official_web import (
    OFFICIAL_LOGIN_COMPONENT_ID,
    OFFICIAL_LOGIN_COMPONENT_VERSION,
)
from .official_web_component_expected import (
    EXPECTED_OFFICIAL_WEB_MANIFEST_SHA256,
)


COMPONENT_MANIFEST_NAME = "official-web-manifest.json"
COMPONENT_MANIFEST_SCHEMA = 1
MAX_COMPONENT_MEMBERS = 5000
MAX_COMPONENT_EXTRACTED_BYTES = 900 * 1024 * 1024
MAX_COMPONENT_FILE_BYTES = 512 * 1024 * 1024


class ComponentImportError(RuntimeError):
    """The local component failed validation or installation."""


@dataclass(frozen=True)
class ComponentInstall:
    version: str
    entrypoint: Path
    manifest_sha256: str
    install_path: Path


@dataclass(frozen=True)
class ComponentStatus:
    installed: bool
    message: str
    version: str = ""
    entrypoint: Path | None = None
    manifest_sha256: str = ""


def component_install_root() -> Path:
    return get_config_directory() / "components" / "official-web"


def component_install_path(
    install_root: Path | None = None,
    version: str = OFFICIAL_LOGIN_COMPONENT_VERSION,
) -> Path:
    return (install_root or component_install_root()) / version


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> str:
    if not isinstance(value, str):
        raise ComponentImportError("组件文件路径必须是字符串。")
    if not value or "\\" in value or value.startswith("/"):
        raise ComponentImportError("组件包含非法绝对或反斜杠路径。")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ComponentImportError("组件包含路径穿越或非法相对路径。")
    return path.as_posix()


def _manifest_file_entries(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ComponentImportError("组件文件夹不能包含符号链接。")
        if not path.is_file() or path.name == COMPONENT_MANIFEST_NAME:
            continue
        relative = _safe_relative(path.relative_to(root).as_posix())
        if path.stat().st_size > MAX_COMPONENT_FILE_BYTES:
            raise ComponentImportError("组件内单个文件过大。")
        total_bytes += path.stat().st_size
        if len(files) >= MAX_COMPONENT_MEMBERS:
            raise ComponentImportError("组件文件数量超过限制。")
        if total_bytes > MAX_COMPONENT_EXTRACTED_BYTES:
            raise ComponentImportError("组件总大小超过限制。")
        files[relative] = _sha256_file(path)
    return files


def manifest_bytes_for_files(
    root: Path,
    *,
    component_version: str,
    app_version: str,
    entrypoint: str,
) -> bytes:
    root = Path(root)
    files = _manifest_file_entries(root)
    entry = _safe_relative(entrypoint)
    if entry not in files:
        raise ComponentImportError("组件入口文件不在文件清单中。")
    payload = {
        "schema": COMPONENT_MANIFEST_SCHEMA,
        "component_id": OFFICIAL_LOGIN_COMPONENT_ID,
        "component_version": component_version,
        "app_version": app_version,
        "platform": "win-amd64",
        "entrypoint": entry,
        "files": files,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _parse_manifest(
    raw: bytes,
    *,
    expected_manifest_sha256: str,
    expected_app_version: str,
    expected_component_version: str,
) -> dict:
    actual_hash = _sha256_bytes(raw)
    if not expected_manifest_sha256 or not _constant_time_equal(
        actual_hash,
        expected_manifest_sha256.lower(),
    ):
        raise ComponentImportError("组件清单哈希不匹配。")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ComponentImportError("组件清单不是有效的 UTF-8 JSON。") from exc
    if not isinstance(payload, dict):
        raise ComponentImportError("组件清单顶层必须是对象。")
    if payload.get("schema") != COMPONENT_MANIFEST_SCHEMA:
        raise ComponentImportError("组件清单版本不受支持。")
    if payload.get("component_id") != OFFICIAL_LOGIN_COMPONENT_ID:
        raise ComponentImportError("组件标识不匹配。")
    if payload.get("component_version") != expected_component_version:
        raise ComponentImportError("组件版本与主程序不匹配。")
    if payload.get("app_version") != expected_app_version:
        raise ComponentImportError("组件声明的软件版本与主程序不匹配。")
    if payload.get("platform") != "win-amd64":
        raise ComponentImportError("组件平台必须是 win-amd64。")
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ComponentImportError("组件清单 files 必须是对象。")
    for relative, digest in files.items():
        _safe_relative(relative)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in digest)
        ):
            raise ComponentImportError("组件清单包含非法文件哈希。")
    entrypoint = _safe_relative(str(payload.get("entrypoint", "")))
    if entrypoint not in files:
        raise ComponentImportError("组件入口文件不在文件清单中。")
    return {**payload, "entrypoint": entrypoint, "files": files}


def _constant_time_equal(first: str, second: str) -> bool:
    import hmac

    return hmac.compare_digest(first, second)


def _validate_stage(
    stage: Path,
    *,
    expected_manifest_sha256: str,
    expected_app_version: str,
    expected_component_version: str,
) -> dict:
    manifest_path = stage / COMPONENT_MANIFEST_NAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ComponentImportError("组件缺少根目录清单文件。")
    payload = _parse_manifest(
        manifest_path.read_bytes(),
        expected_manifest_sha256=expected_manifest_sha256,
        expected_app_version=expected_app_version,
        expected_component_version=expected_component_version,
    )
    actual_files = _manifest_file_entries(stage)
    expected_files = payload["files"]
    if set(actual_files) != set(expected_files):
        raise ComponentImportError("组件文件清单与实际文件不一致。")
    for relative, expected_hash in expected_files.items():
        if not _constant_time_equal(actual_files[relative], expected_hash.lower()):
            raise ComponentImportError(f"组件文件哈希不匹配：{relative}")
    return payload


def _safe_zip_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if len(members) > MAX_COMPONENT_MEMBERS:
        raise ComponentImportError("组件压缩包文件数量超过限制。")
    seen: set[str] = set()
    total = 0
    safe_members: list[zipfile.ZipInfo] = []
    for member in members:
        relative = _safe_relative(member.filename.rstrip("/"))
        if relative in seen:
            raise ComponentImportError("组件压缩包包含重复路径。")
        seen.add(relative)
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ComponentImportError("组件压缩包不能包含符号链接。")
        if member.file_size > MAX_COMPONENT_FILE_BYTES:
            raise ComponentImportError("组件压缩包内单个文件过大。")
        total += member.file_size
        if total > MAX_COMPONENT_EXTRACTED_BYTES:
            raise ComponentImportError("组件解压后总大小超过限制。")
        safe_members.append(member)
    return safe_members


def _extract_zip(stage: Path, archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for member in _safe_zip_members(archive):
            relative = _safe_relative(member.filename.rstrip("/"))
            target = stage.joinpath(*PurePosixPath(relative).parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _copy_folder(stage: Path, source: Path) -> None:
    if source.is_symlink():
        raise ComponentImportError("组件文件夹不能是符号链接。")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ComponentImportError("组件文件夹不能包含符号链接。")
        relative = _safe_relative(path.relative_to(source).as_posix())
        target = stage.joinpath(*PurePosixPath(relative).parts)
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _remove_tree_with_retries(path: Path) -> None:
    for attempt in range(8):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == 7:
                raise
            time.sleep(0.15 * (attempt + 1))


def remove_session_directory(path: Path) -> None:
    if path.exists():
        _remove_tree_with_retries(path)


def _default_self_check(entrypoint: Path) -> None:
    try:
        completed = subprocess.run(
            [str(entrypoint), "--self-check"],
            cwd=str(entrypoint.parent),
            capture_output=True,
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ComponentImportError("组件自检无法启动或超时。") from exc
    if completed.returncode != 0:
        raise ComponentImportError("组件自检失败。")


def import_component(
    source: Path,
    *,
    install_root: Path | None = None,
    expected_manifest_sha256: str = EXPECTED_OFFICIAL_WEB_MANIFEST_SHA256,
    expected_app_version: str,
    expected_component_version: str = OFFICIAL_LOGIN_COMPONENT_VERSION,
    self_check: Callable[[Path], None] | None = None,
) -> ComponentInstall:
    source = Path(source)
    if not source.exists():
        raise ComponentImportError("组件来源不存在。")
    install_root = Path(install_root or component_install_root())
    install_root.mkdir(parents=True, exist_ok=True)
    stage = install_root / f".stage-{uuid.uuid4().hex}"
    stage.mkdir()
    try:
        if source.is_dir():
            _copy_folder(stage, source)
        elif source.suffix.lower() == ".zip":
            _extract_zip(stage, source)
        else:
            raise ComponentImportError("组件必须是 zip 文件或文件夹。")
        payload = _validate_stage(
            stage,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_app_version=expected_app_version,
            expected_component_version=expected_component_version,
        )
        final = install_root / expected_component_version
        backup: Path | None = None
        if final.exists():
            if component_status(
                install_root,
                expected_app_version=expected_app_version,
                expected_component_version=expected_component_version,
                expected_manifest_sha256=expected_manifest_sha256,
            ).installed:
                return ComponentInstall(
                    expected_component_version,
                    final.joinpath(*PurePosixPath(payload["entrypoint"]).parts),
                    expected_manifest_sha256,
                    final,
                )
            backup = install_root / f".backup-{uuid.uuid4().hex}"
            final.rename(backup)
        try:
            stage.rename(final)
        except Exception:
            if backup is not None and backup.exists():
                backup.rename(final)
            raise
        entrypoint = final.joinpath(*PurePosixPath(payload["entrypoint"]).parts)
        try:
            (self_check or _default_self_check)(entrypoint)
        except Exception:
            try:
                _remove_tree_with_retries(final)
            except OSError:
                pass
            if backup is not None and backup.exists():
                backup.rename(final)
            raise
        if backup is not None:
            try:
                _remove_tree_with_retries(backup)
            except OSError:
                pass
        return ComponentInstall(
            expected_component_version,
            entrypoint,
            expected_manifest_sha256,
            final,
        )
    except OSError as exc:
        raise ComponentImportError(f"组件安装失败：{exc}") from exc
    finally:
        if stage.exists():
            try:
                _remove_tree_with_retries(stage)
            except OSError:
                pass


def component_status(
    install_root: Path | None = None,
    *,
    expected_app_version: str,
    expected_component_version: str = OFFICIAL_LOGIN_COMPONENT_VERSION,
    expected_manifest_sha256: str = EXPECTED_OFFICIAL_WEB_MANIFEST_SHA256,
) -> ComponentStatus:
    root = Path(install_root or component_install_root())
    final = root / expected_component_version
    if not final.is_dir():
        return ComponentStatus(False, "实验性官网组件尚未导入。")
    try:
        payload = _validate_stage(
            final,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_app_version=expected_app_version,
            expected_component_version=expected_component_version,
        )
    except ComponentImportError as exc:
        return ComponentStatus(False, f"组件校验失败：{exc}")
    return ComponentStatus(
        True,
        "实验性官网组件已安装并通过校验。",
        expected_component_version,
        final.joinpath(*PurePosixPath(payload["entrypoint"]).parts),
        expected_manifest_sha256,
    )
