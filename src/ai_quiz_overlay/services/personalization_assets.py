"""Safe image ingestion, crop outputs, icon generation, and asset transactions."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import struct
import tempfile
import uuid

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QImageReader,
    QImageWriter,
    QPainter,
    QPainterPath,
)

from ..config import PersonalizationConfig
from ..personalization_runtime import personalization_directory


MAX_IMAGE_FILE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_EDGE = 8192
MAX_IMAGE_PIXELS = 24_000_000
MAX_BACKGROUND_EDGE = 3840
ICON_MASTER_SIZE = 1024
MIN_HIGH_DPI_CROP_EDGE = 320
SUPPORTED_IMAGE_FORMATS = {
    "bmp",
    "gif",
    "jpeg",
    "jpg",
    "png",
    "webp",
}


class PersonalizationImageError(RuntimeError):
    """A localized, user-actionable image import error."""


@dataclass(frozen=True)
class LoadedImage:
    image: QImage
    actual_format: str
    animated: bool


@dataclass(frozen=True)
class GeneratedIconAssets:
    app_icon_id: str
    title_logo_id: str
    ball_image_id: str


def _unsupported_format_message(path: Path) -> str:
    suffix = path.suffix.casefold()
    if suffix in {".heic", ".heif", ".avif"}:
        return (
            "当前图片格式无法由 Qt 解码。请先转换成 PNG 或 JPG 后再选择。"
        )
    return "无法识别这张图片，请先转换成 PNG 或 JPG 后再选择。"


def load_local_image(path: Path) -> LoadedImage:
    """Validate headers and decode only a bounded local image."""
    if hasattr(QImageReader, "setAllocationLimit"):
        QImageReader.setAllocationLimit(128)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise PersonalizationImageError(
            f"无法读取所选图片：{exc}"
        ) from exc
    if size <= 0:
        raise PersonalizationImageError("所选图片是空文件。")
    if size > MAX_IMAGE_FILE_BYTES:
        raise PersonalizationImageError("图片不能超过 20 MiB。")

    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    reader.setDecideFormatFromContent(True)
    actual_format = bytes(reader.format()).decode(
        "ascii",
        errors="ignore",
    ).casefold()
    header_size = reader.size()
    if (
        actual_format not in SUPPORTED_IMAGE_FORMATS
        or not header_size.isValid()
    ):
        raise PersonalizationImageError(_unsupported_format_message(path))
    width = header_size.width()
    height = header_size.height()
    if width <= 0 or height <= 0:
        raise PersonalizationImageError("图片尺寸无效或文件已经损坏。")
    if width > MAX_IMAGE_EDGE or height > MAX_IMAGE_EDGE:
        raise PersonalizationImageError(
            "图片单边不能超过 8192 像素。"
        )
    if width * height > MAX_IMAGE_PIXELS:
        raise PersonalizationImageError(
            "图片总像素不能超过 2400 万，请先缩小后再选择。"
        )
    animated = bool(reader.supportsAnimation())
    image = reader.read()
    if image.isNull():
        raise PersonalizationImageError(
            f"图片解码失败：{reader.errorString() or '文件可能已损坏'}"
        )
    if max(image.width(), image.height()) > MAX_BACKGROUND_EDGE:
        image = image.scaled(
            MAX_BACKGROUND_EDGE,
            MAX_BACKGROUND_EDGE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return LoadedImage(
        image=image,
        actual_format=actual_format,
        animated=animated,
    )


def _write_image_atomic(image: QImage, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(_png_bytes(image))
        os.replace(temporary, path)
    except PersonalizationImageError:
        temporary.unlink(missing_ok=True)
        raise
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise PersonalizationImageError(
            f"无法写入个性化图片：{exc}"
        ) from exc


def _png_bytes(image: QImage) -> bytes:
    clean = QImage(
        image.size(),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    clean.fill(Qt.GlobalColor.transparent)
    clean_painter = QPainter(clean)
    clean_painter.drawImage(0, 0, image)
    clean_painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise PersonalizationImageError("无法生成图标 PNG 数据。")
    writer = QImageWriter(buffer, b"png")
    if not writer.write(clean):
        raise PersonalizationImageError(
            f"无法生成图标 PNG：{writer.errorString()}"
        )
    buffer.close()
    return bytes(data)


def write_multi_size_ico(source: QImage, path: Path) -> None:
    sizes = (16, 24, 32, 48, 64, 128, 256)
    frames = [
        _png_bytes(
            source.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        for size in sizes
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    offset = 6 + len(sizes) * 16
    try:
        with temporary.open("wb") as handle:
            handle.write(struct.pack("<HHH", 0, 1, len(sizes)))
            for size, frame in zip(sizes, frames, strict=True):
                encoded_size = 0 if size == 256 else size
                handle.write(
                    struct.pack(
                        "<BBBBHHII",
                        encoded_size,
                        encoded_size,
                        0,
                        0,
                        1,
                        32,
                        len(frame),
                        offset,
                    )
                )
                offset += len(frame)
            for frame in frames:
                handle.write(frame)
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise PersonalizationImageError(f"写入 ICO 失败：{exc}") from exc


def render_square_crop(
    source: QImage,
    crop_rect: QRectF,
    size: int = ICON_MASTER_SIZE,
) -> QImage:
    if source.isNull() or crop_rect.isEmpty():
        raise PersonalizationImageError("裁剪区域无效。")
    output = QImage(size, size, QImage.Format.Format_ARGB32)
    output.fill(Qt.GlobalColor.transparent)
    painter = QPainter(output)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(
        QRectF(0, 0, size, size),
        source,
        crop_rect,
    )
    painter.end()
    return output


def masked_circle(source: QImage, size: int = ICON_MASTER_SIZE) -> QImage:
    square = source.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    output = QImage(size, size, QImage.Format.Format_ARGB32)
    output.fill(Qt.GlobalColor.transparent)
    painter = QPainter(output)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addEllipse(QRectF(0, 0, size, size))
    painter.setClipPath(path)
    painter.drawImage(
        QRect(0, 0, size, size),
        square,
    )
    painter.end()
    return output


class PersonalizationAssetDraft:
    def __init__(self) -> None:
        root = personalization_directory()
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.directory = Path(
            tempfile.mkdtemp(prefix=".draft-", dir=root)
        )
        self.revision = uuid.uuid4().hex[:12]
        self._asset_ids: set[str] = set()

    def stage_background(self, image: QImage) -> str:
        asset_id = f"background-{self.revision}.png"
        _write_image_atomic(image, self.directory / asset_id)
        self._asset_ids.add(asset_id)
        return asset_id

    def stage_icons(self, square_icon: QImage) -> GeneratedIconAssets:
        square = square_icon.scaled(
            ICON_MASTER_SIZE,
            ICON_MASTER_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        app_id = f"app-icon-{self.revision}.ico"
        logo_id = f"title-logo-{self.revision}.png"
        ball_id = f"ball-{self.revision}.png"
        write_multi_size_ico(square, self.directory / app_id)
        _write_image_atomic(
            masked_circle(square),
            self.directory / logo_id,
        )
        _write_image_atomic(
            masked_circle(square),
            self.directory / ball_id,
        )
        self._asset_ids.update({app_id, logo_id, ball_id})
        return GeneratedIconAssets(
            app_icon_id=app_id,
            title_logo_id=logo_id,
            ball_image_id=ball_id,
        )

    def preview_path(self, asset_id: str) -> Path:
        return self.directory / asset_id

    def commit(self) -> set[str]:
        moved: list[Path] = []
        try:
            for asset_id in sorted(self._asset_ids):
                source = self.directory / asset_id
                target = self.root / asset_id
                os.replace(source, target)
                moved.append(target)
            return set(self._asset_ids)
        except OSError as exc:
            for target in moved:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
            raise PersonalizationImageError(
                f"保存个性化资产失败：{exc}"
            ) from exc
        finally:
            shutil.rmtree(self.directory, ignore_errors=True)

    def discard(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)


def current_asset_ids(personalization: PersonalizationConfig) -> set[str]:
    return {
        asset_id
        for asset_id in (
            personalization.background_asset,
            personalization.app_icon_asset,
            personalization.title_logo_asset,
            personalization.ball_image_asset,
        )
        if asset_id
    }


def delete_old_assets_after_commit(old_asset_ids: set[str]) -> None:
    root = personalization_directory()
    for asset_id in old_asset_ids:
        try:
            (root / asset_id).unlink(missing_ok=True)
        except OSError:
            pass
    try:
        (root / "app-icon.png").unlink(missing_ok=True)
    except OSError:
        pass


def clear_personalization_assets_after_commit() -> None:
    root = personalization_directory()
    if not root.exists():
        return
    for child in root.iterdir():
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
        except OSError:
            pass
