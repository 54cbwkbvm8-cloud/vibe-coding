"""DeepSeek HTTP 错误提示测试。"""

from pathlib import Path
import json
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.services.deepseek_errors import http_error_message  # noqa: E402


class DeepSeekErrorTests(unittest.TestCase):
    def test_authentication_message(self) -> None:
        message = http_error_message(401, b"{}")
        self.assertIn("API Key 无效", message)

    def test_balance_message(self) -> None:
        message = http_error_message(402, b"{}")
        self.assertIn("余额不足", message)

    def test_rate_limit_message(self) -> None:
        message = http_error_message(429, b"{}")
        self.assertIn("限流", message)

    def test_api_key_is_redacted_from_provider_message(self) -> None:
        secret = "redaction-test-placeholder"
        body = json.dumps(
            {"error": {"message": f"request used {secret}"}}
        ).encode("utf-8")
        message = http_error_message(400, body, secret)
        self.assertNotIn(secret, message)
        self.assertIn("[已隐藏]", message)

    def test_base64_image_is_redacted_from_error(self) -> None:
        body = json.dumps(
            {
                "error": {
                    "message": "bad image data:image/png;base64,QUJDREVGRw=="
                }
            }
        ).encode("utf-8")
        message = http_error_message(400, body)
        self.assertNotIn("QUJDREVGRw", message)
        self.assertIn("[图片数据已隐藏]", message)


if __name__ == "__main__":
    unittest.main()
