"""Personalization image validation, encoding, and asset transaction tests."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import struct
import zlib

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.services import personalization_assets  # noqa: E402
from ai_quiz_overlay.services.personalization_assets import (  # noqa: E402
    PersonalizationAssetDraft,
    PersonalizationImageError,
    clear_personalization_assets_after_commit,
    load_local_image,
    masked_circle,
    write_multi_size_ico,
)


class PersonalizationAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _write_image(
        self,
        path: Path,
        width: int,
        height: int,
        image_format: str = "PNG",
    ) -> None:
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(QColor("#d9a93f"))
        image.setText("Comment", "private-location-metadata")
        self.assertTrue(image.save(str(path), image_format))

    def test_valid_image_is_loaded_and_metadata_is_removed_by_png_stage(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.png"
            self._write_image(path, 640, 480)
            loaded = load_local_image(path)
            self.assertFalse(loaded.image.isNull())
            self.assertFalse(loaded.animated)
            with mock.patch.object(
                personalization_assets,
                "personalization_directory",
                return_value=Path(directory) / "assets",
            ):
                draft = PersonalizationAssetDraft()
                try:
                    asset_id = draft.stage_background(loaded.image)
                    self.assertTrue(asset_id.endswith(".png"))
                    self.assertTrue(draft.preview_path(asset_id).is_file())
                    normalized = QImage(
                        str(draft.preview_path(asset_id))
                    )
                    self.assertFalse(normalized.text())
                finally:
                    draft.discard()

    def test_empty_and_oversize_files_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty.png"
            empty.write_bytes(b"")
            with self.assertRaises(PersonalizationImageError):
                load_local_image(empty)
            large = Path(directory) / "large.png"
            with large.open("wb") as handle:
                handle.truncate(20 * 1024 * 1024 + 1)
            with self.assertRaises(PersonalizationImageError):
                load_local_image(large)

    def test_chinese_path_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "中文图片目录"
            folder.mkdir()
            path = folder / "背景图.png"
            self._write_image(path, 320, 180)
            loaded = load_local_image(path)
            self.assertEqual(loaded.image.size(), QSize(320, 180))

    def test_heic_and_avif_get_conversion_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for extension in (".heic", ".AVIF"):
                path = Path(directory) / f"unsupported{extension}"
                path.write_bytes(b"not-a-real-image")
                with self.assertRaises(PersonalizationImageError) as caught:
                    load_local_image(path)
                self.assertIn("请先转换成 PNG 或 JPG", str(caught.exception))

    def test_corrupt_or_renamed_text_image_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "renamed-image.png"
            path.write_text("this is not an image", encoding="utf-8")
            with self.assertRaises(PersonalizationImageError) as caught:
                load_local_image(path)
            self.assertTrue(str(caught.exception))

    def test_oversized_dimensions_are_rejected_before_decode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wide.png"
            self._write_image(path, 8200, 1)
            with self.assertRaises(PersonalizationImageError) as caught:
                load_local_image(path)
            self.assertIn("8192", str(caught.exception))

    def test_pixel_count_limit_is_checked_from_header(self) -> None:
        def png_chunk(kind: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + kind
                + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pixel-bomb.png"
            header = struct.pack(
                ">IIBBBBB",
                6000,
                5000,
                8,
                6,
                0,
                0,
                0,
            )
            path.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + png_chunk(b"IHDR", header)
                + png_chunk(b"IDAT", zlib.compress(b"\x00"))
                + png_chunk(b"IEND", b"")
            )
            with self.assertRaises(PersonalizationImageError) as caught:
                load_local_image(path)
            self.assertIn("2400 万", str(caught.exception))

    def test_animation_is_reported_while_first_frame_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "animated.gif"
            path.write_bytes(
                b"GIF89a\x01\x00\x01\x00\x80\x00\x00"
                b"\x00\x00\x00\xff\xff\xff!\xf9\x04\x01"
                b"\x00\x00\x00\x00,\x00\x00\x00\x00"
                b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
            )
            with mock.patch(
                "PySide6.QtGui.QImageReader.supportsAnimation",
                return_value=True,
            ):
                loaded = load_local_image(path)
            self.assertTrue(loaded.animated)
            self.assertEqual(loaded.image.size(), QSize(1, 1))

    def test_multi_size_ico_contains_required_sizes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = QImage(512, 512, QImage.Format.Format_ARGB32)
            source.fill(QColor("#f0c568"))
            path = Path(directory) / "custom.ico"
            write_multi_size_ico(source, path)
            data = path.read_bytes()
            reserved, image_type, count = (
                int.from_bytes(data[0:2], "little"),
                int.from_bytes(data[2:4], "little"),
                int.from_bytes(data[4:6], "little"),
            )
            self.assertEqual((reserved, image_type, count), (0, 1, 7))
            sizes = set()
            for index in range(count):
                offset = 6 + index * 16
                width = data[offset] or 256
                height = data[offset + 1] or 256
                sizes.add((width, height))
            self.assertEqual(
                sizes,
                {
                    (16, 16),
                    (24, 24),
                    (32, 32),
                    (48, 48),
                    (64, 64),
                    (128, 128),
                    (256, 256),
                },
            )

    def test_circle_mask_has_transparent_corners(self) -> None:
        source = QImage(512, 512, QImage.Format.Format_ARGB32)
        source.fill(QColor("#f0c568"))
        image = masked_circle(source, 512)
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
        self.assertGreater(image.pixelColor(256, 256).alpha(), 0)

    def test_asset_commit_failure_preserves_old_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "assets"
            root.mkdir()
            old_file = root / "old-background.png"
            old_file.write_bytes(b"old")
            source = QImage(512, 512, QImage.Format.Format_ARGB32)
            source.fill(QColor("#f0c568"))
            with mock.patch.object(
                personalization_assets,
                "personalization_directory",
                return_value=root,
            ):
                draft = PersonalizationAssetDraft()
                square = source
                generated = draft.stage_icons(square)
                real_replace = personalization_assets.os.replace
                calls = {"count": 0}

                def failing_replace(src, dst):
                    calls["count"] += 1
                    if calls["count"] == 2:
                        raise OSError("disk full")
                    return real_replace(src, dst)

                with mock.patch.object(
                    personalization_assets.os,
                    "replace",
                    side_effect=failing_replace,
                ):
                    with self.assertRaises(PersonalizationImageError):
                        draft.commit()
            self.assertEqual(old_file.read_bytes(), b"old")
            for asset_id in (
                generated.app_icon_id,
                generated.title_logo_id,
                generated.ball_image_id,
            ):
                self.assertFalse((root / asset_id).exists())

    def test_full_reset_cleaner_removes_files_and_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "assets"
            root.mkdir()
            (root / "old.png").write_bytes(b"old")
            (root / ".draft-old").mkdir()
            (root / ".draft-old" / "temporary.png").write_bytes(b"temp")
            with mock.patch.object(
                personalization_assets,
                "personalization_directory",
                return_value=root,
            ):
                clear_personalization_assets_after_commit()
            self.assertFalse(root.exists() and any(root.iterdir()))


if __name__ == "__main__":
    unittest.main()
