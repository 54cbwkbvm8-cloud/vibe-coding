"""图片模型预检查测试。"""

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.services.vision_support import image_model_error  # noqa: E402


class VisionSupportTests(unittest.TestCase):
    def test_flash_supports_images(self) -> None:
        self.assertIsNone(image_model_error("deepseek-flash"))

    def test_v4_pro_is_rejected(self) -> None:
        message = image_model_error("deepseek-v4-pro")
        self.assertIsNotNone(message)
        self.assertIn("不支持图片", message or "")

    def test_unknown_model_is_rejected(self) -> None:
        message = image_model_error("custom-model")
        self.assertIn("未在已验证", message or "")


if __name__ == "__main__":
    unittest.main()
