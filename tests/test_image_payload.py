"""截图缩放和内存编码测试，不使用真实屏幕。"""

from pathlib import Path
import sys
import unittest

from PySide6.QtGui import QColor, QImage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.services.image_payload import (  # noqa: E402
    image_to_data_url,
    resize_for_api,
)


class ImagePayloadTests(unittest.TestCase):
    def test_resize_keeps_aspect_ratio(self) -> None:
        image = QImage(3200, 1800, QImage.Format.Format_RGB32)
        image.fill(QColor("#336699"))
        resized = resize_for_api(image)
        self.assertEqual(max(resized.width(), resized.height()), 1600)
        self.assertAlmostEqual(resized.width() / resized.height(), 3200 / 1800)

    def test_data_url_uses_supported_inline_format(self) -> None:
        image = QImage(400, 300, QImage.Format.Format_RGB32)
        image.fill(QColor("#f0d080"))
        data_url = image_to_data_url(image)
        self.assertTrue(
            data_url.startswith("data:image/png;base64,")
            or data_url.startswith("data:image/jpeg;base64,")
        )
        self.assertGreater(len(data_url), 100)

    def test_custom_long_edge_is_respected(self) -> None:
        image = QImage(2000, 1000, QImage.Format.Format_RGB32)
        image.fill(QColor("#778899"))
        resized = resize_for_api(image, max_edge=1200)
        self.assertEqual(max(resized.width(), resized.height()), 1200)


if __name__ == "__main__":
    unittest.main()
