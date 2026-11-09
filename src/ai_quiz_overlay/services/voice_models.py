"""Fixed SenseVoice model metadata and secure local model installation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile
import threading
from urllib.parse import urlparse
import urllib.request

from ..config import get_config_directory
from .network_policy import MODEL_SOURCE_DOMAINS


MODEL_REPOSITORY = (
    "csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
)
MODEL_REVISION = "2365baeacb507f821a0c8120fcee3d484dba7a07"
MODEL_FILE_NAME = "model.int8.onnx"
TOKENS_FILE_NAME = "tokens.txt"
MODEL_FILE_SIZE = 239_233_841
TOKENS_FILE_SIZE = 315_894
MODEL_SHA256 = (
    "c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51"
)
TOKENS_SHA256 = (
    "f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc"
)
GITHUB_ARCHIVE_NAME = (
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2"
)
GITHUB_ARCHIVE_SIZE = 163_002_883
GITHUB_ARCHIVE_SHA256 = (
    "7d1efa2138a65b0b488df37f8b89e3d91a60676e416f515b952358d83dfd347e"
)
GITHUB_ARCHIVE_PREFIX = (
    "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
)
EXPECTED_MODEL_FILES = {
    MODEL_FILE_NAME: (MODEL_FILE_SIZE, MODEL_SHA256),
    TOKENS_FILE_NAME: (TOKENS_FILE_SIZE, TOKENS_SHA256),
}
ALLOWED_ARCHIVE_MEMBERS = {
    f"{GITHUB_ARCHIVE_PREFIX}/{name}": name
    for name in EXPECTED_MODEL_FILES
}
MAX_REDIRECTS = 3
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
DEFAULT_MODEL_DIRECTORY = (
    get_config_directory() / "models" / "sensevoice-small-int8"
)


class ModelDownloadError(RuntimeError):
    """A user-readable, non-secret model installation error."""


@dataclass(frozen=True)
class RemoteArtifact:
    url: str
    file_name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ModelSource:
    key: str
    label: str
    description: str
    domains: tuple[str, ...]
    artifacts: tuple[RemoteArtifact, ...]
    archive: bool = False
    recommended: bool = False


HF_MIRROR_SOURCE = ModelSource(
    key="hf_mirror",
    label="Hugging Face 镜像（推荐）",
    description="固定 revision；当前下载 CDN 为 cas-bridge.xethub.hf.co。",
    domains=MODEL_SOURCE_DOMAINS["hf_mirror"],
    artifacts=(
        RemoteArtifact(
            url=(
                f"https://hf-mirror.com/{MODEL_REPOSITORY}/resolve/"
                f"{MODEL_REVISION}/{MODEL_FILE_NAME}?download=true"
            ),
            file_name=MODEL_FILE_NAME,
            size=MODEL_FILE_SIZE,
            sha256=MODEL_SHA256,
        ),
        RemoteArtifact(
            url=(
                f"https://hf-mirror.com/{MODEL_REPOSITORY}/resolve/"
                f"{MODEL_REVISION}/{TOKENS_FILE_NAME}?download=true"
            ),
            file_name=TOKENS_FILE_NAME,
            size=TOKENS_FILE_SIZE,
            sha256=TOKENS_SHA256,
        ),
    ),
    recommended=True,
)

GITHUB_RELEASE_SOURCE = ModelSource(
    key="github_release",
    label="GitHub 官方 Release",
    description=(
        "官方资产压缩包；下载后只读取固定文件名的两个模型文件。"
    ),
    domains=MODEL_SOURCE_DOMAINS["github_release"],
    artifacts=(
        RemoteArtifact(
            url=(
                "https://api.github.com/repos/k2-fsa/sherpa-onnx/"
                "releases/assets/288366523"
            ),
            file_name=GITHUB_ARCHIVE_NAME,
            size=GITHUB_ARCHIVE_SIZE,
            sha256=GITHUB_ARCHIVE_SHA256,
        ),
    ),
    archive=True,
)

MODEL_SOURCES = (
    HF_MIRROR_SOURCE,
    GITHUB_RELEASE_SOURCE,
)
MODEL_SOURCE_BY_KEY = {source.key: source for source in MODEL_SOURCES}


def model_directory() -> Path:
    return DEFAULT_MODEL_DIRECTORY


def model_files(directory: Path | None = None) -> tuple[Path, Path]:
    root = directory or model_directory()
    return root / MODEL_FILE_NAME, root / TOKENS_FILE_NAME


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(DOWNLOAD_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_model_directory(directory: Path | None = None) -> tuple[bool, str]:
    root = directory or model_directory()
    for file_name, (expected_size, expected_hash) in EXPECTED_MODEL_FILES.items():
        path = root / file_name
        if not path.is_file():
            return False, f"缺少 {file_name}"
        try:
            actual_size = path.stat().st_size
        except OSError as exc:
            return False, f"无法读取 {file_name}：{exc}"
        if actual_size != expected_size:
            return False, f"{file_name} 大小不正确"
        try:
            actual_hash = sha256_file(path)
        except OSError as exc:
            return False, f"无法校验 {file_name}：{exc}"
        if actual_hash != expected_hash:
            return False, f"{file_name} SHA-256 校验失败"
    return True, "SenseVoice 模型已就绪"


def model_files_present(directory: Path | None = None) -> tuple[bool, str]:
    """Fast preflight before a worker performs the full hash validation."""
    root = directory or model_directory()
    for file_name in EXPECTED_MODEL_FILES:
        if not (root / file_name).is_file():
            return False, f"缺少 {file_name}"
    return True, "SenseVoice 模型文件存在"


def _normalized_domain(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower()


def validate_download_url(url: str, allowed_domains: tuple[str, ...]) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ModelDownloadError("模型下载只允许 HTTPS 地址。")
    host = (parsed.hostname or "").lower()
    allowed = {domain.lower() for domain in allowed_domains}
    if host not in allowed:
        raise ModelDownloadError(f"模型下载域名不在白名单：{host or '未知域名'}")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS

    def __init__(self, allowed_domains: tuple[str, ...]) -> None:
        super().__init__()
        self.allowed_domains = allowed_domains
        self.hop_count = 0
        self.hops: list[tuple[str, str]] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.hop_count += 1
        if self.hop_count > MAX_REDIRECTS:
            raise ModelDownloadError("模型下载重定向超过 3 次。")
        validate_download_url(newurl, self.allowed_domains)
        current_host = _normalized_domain(req.full_url)
        next_host = _normalized_domain(newurl)
        request_headers = dict(req.headers)
        if current_host != next_host:
            for name in (
                "Cookie",
                "Authorization",
                "Proxy-Authorization",
            ):
                request_headers.pop(name, None)
        self.hops.append((current_host, next_host))
        return urllib.request.Request(
            newurl,
            headers=request_headers,
            origin_req_host=req.origin_req_host,
            unverifiable=True,
        )


def _required_disk_bytes(source: ModelSource) -> int:
    remote_bytes = sum(artifact.size for artifact in source.artifacts)
    if source.archive:
        extracted_bytes = sum(size for size, _digest in EXPECTED_MODEL_FILES.values())
        return remote_bytes + extracted_bytes + 32 * 1024 * 1024
    return remote_bytes + 32 * 1024 * 1024


def _ensure_disk_space(destination: Path, required: int) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(destination).free
    if free < required:
        raise ModelDownloadError(
            "磁盘空间不足：模型安装至少还需要 "
            f"{required / (1024 * 1024):.0f} MiB。"
        )


def _download_artifact(
    artifact: RemoteArtifact,
    source: ModelSource,
    target: Path,
    progress,
    cancel_event: threading.Event,
) -> None:
    validate_download_url(artifact.url, source.domains)
    redirect_handler = _SafeRedirectHandler(source.domains)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        redirect_handler,
    )
    request = urllib.request.Request(
        artifact.url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "NaiwaGlory/1.0.0 model-installer",
        },
        method="GET",
    )
    downloaded = 0
    with opener.open(request, timeout=45) as response:
        content_length = response.headers.get("Content-Length")
        total = (
            int(content_length)
            if content_length and content_length.isdigit()
            else artifact.size
        )
        with target.open("wb") as handle:
            while True:
                if cancel_event.is_set():
                    raise ModelDownloadError("下载已取消。")
                chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if progress is not None:
                    progress(downloaded, total)
    if downloaded != artifact.size:
        raise ModelDownloadError(
            f"{artifact.file_name} 大小校验失败。"
        )
    actual_hash = sha256_file(target)
    if actual_hash != artifact.sha256:
        raise ModelDownloadError(
            f"{artifact.file_name} SHA-256 校验失败。"
        )


def _validate_archive_member(member: tarfile.TarInfo) -> None:
    normalized = member.name.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if (
        PurePosixPath(normalized).is_absolute()
        or ".." in parts
        or bool(re.match(r"^[A-Za-z]:", normalized))
        or member.issym()
        or member.islnk()
        or member.isdev()
        or member.isfifo()
    ):
        raise ModelDownloadError("模型压缩包包含不安全的条目。")


def _extract_required_archive_files(
    archive_path: Path,
    output: Path,
) -> None:
    found: set[str] = set()
    extracted_bytes = 0
    max_bytes = sum(size for size, _digest in EXPECTED_MODEL_FILES.values())
    with tarfile.open(archive_path, mode="r:bz2") as archive:
        for member in archive:
            _validate_archive_member(member)
            if member.isdir():
                continue
            if not member.isfile():
                continue
            output_name = ALLOWED_ARCHIVE_MEMBERS.get(
                member.name.replace("\\", "/")
            )
            if output_name is None:
                continue
            if output_name in found:
                raise ModelDownloadError("模型压缩包包含重复的目标文件。")
            extracted_bytes += member.size
            if extracted_bytes > max_bytes:
                raise ModelDownloadError("模型压缩包解压后超过安全大小限制。")
            source = archive.extractfile(member)
            if source is None:
                raise ModelDownloadError("无法读取模型压缩包目标文件。")
            target = output / output_name
            written = 0
            with source, target.open("wb") as handle:
                for chunk in iter(
                    lambda: source.read(DOWNLOAD_CHUNK_SIZE),
                    b"",
                ):
                    written += len(chunk)
                    if written > member.size:
                        raise ModelDownloadError("模型压缩包条目大小异常。")
                    handle.write(chunk)
            if written != member.size:
                raise ModelDownloadError("模型压缩包条目读取不完整。")
            found.add(output_name)
    if found != set(EXPECTED_MODEL_FILES):
        raise ModelDownloadError("模型压缩包缺少所需文件。")


def _validate_staged_files(staging: Path) -> None:
    for file_name, (expected_size, expected_hash) in EXPECTED_MODEL_FILES.items():
        path = staging / file_name
        if not path.is_file():
            raise ModelDownloadError(f"缺少 {file_name}。")
        if path.stat().st_size != expected_size:
            raise ModelDownloadError(f"{file_name} 大小校验失败。")
        if sha256_file(path) != expected_hash:
            raise ModelDownloadError(f"{file_name} SHA-256 校验失败。")


def _install_staged_files(staging: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    staged_paths: list[tuple[Path, Path]] = []
    try:
        for file_name in EXPECTED_MODEL_FILES:
            temporary = destination / f".{file_name}.new"
            shutil.copy2(staging / file_name, temporary)
            staged_paths.append((temporary, destination / file_name))
        for temporary, target in staged_paths:
            os.replace(temporary, target)
    finally:
        for temporary, _target in staged_paths:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    valid, message = validate_model_directory(destination)
    if not valid:
        raise ModelDownloadError(message)


def install_model_from_source(
    source: ModelSource,
    destination: Path | None = None,
    *,
    progress=None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Download, verify, and install one user-selected source."""
    root = destination or model_directory()
    cancel = cancel_event or threading.Event()
    already_valid, _message = validate_model_directory(root)
    if already_valid:
        return root
    _ensure_disk_space(root, _required_disk_bytes(source))
    staging = Path(
        tempfile.mkdtemp(prefix=".voice-model-", dir=root.parent)
    )
    try:
        if source.archive:
            artifact = source.artifacts[0]
            archive_path = staging / artifact.file_name
            _download_artifact(
                artifact,
                source,
                archive_path,
                progress,
                cancel,
            )
            extracted = staging / "extracted"
            extracted.mkdir()
            _extract_required_archive_files(archive_path, extracted)
            staged_files = extracted
            archive_path.unlink(missing_ok=True)
        else:
            staged_files = staging / "files"
            staged_files.mkdir()
            for artifact in source.artifacts:
                if cancel.is_set():
                    raise ModelDownloadError("下载已取消。")
                _download_artifact(
                    artifact,
                    source,
                    staged_files / artifact.file_name,
                    progress,
                    cancel,
                )
        _validate_staged_files(staged_files)
        _install_staged_files(staged_files, root)
        return root
    except Exception:
        if root.exists():
            for temporary in root.glob(".*.new"):
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def import_model_directory(
    source_directory: Path,
    destination: Path | None = None,
) -> Path:
    """Validate and install a manually selected local model folder."""
    root = destination or model_directory()
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=".voice-import-", dir=root.parent)
    )
    try:
        for file_name in EXPECTED_MODEL_FILES:
            source = source_directory / file_name
            if not source.is_file():
                raise ModelDownloadError(f"选择的文件夹缺少 {file_name}。")
            shutil.copy2(source, staging / file_name)
        _validate_staged_files(staging)
        _install_staged_files(staging, root)
        return root
    finally:
        shutil.rmtree(staging, ignore_errors=True)
