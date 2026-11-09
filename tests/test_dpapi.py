"""DPAPI 本轮只允许在 Windows 上执行。"""

from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.credentials import (  # noqa: E402
    delete_api_key,
    load_api_key,
    save_api_key,
)


@unittest.skipUnless(sys.platform == "win32", "DPAPI requires Windows")
class DPAPITests(unittest.TestCase):
    def test_round_trip_and_ciphertext_does_not_contain_plaintext(self) -> None:
        fake_key = "fake-test-key-never-use-in-chat"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "api_key.bin"
            save_api_key(fake_key, path)
            encrypted = path.read_bytes()
            self.assertNotIn(fake_key.encode("utf-8"), encrypted)
            self.assertEqual(load_api_key(path), fake_key)
            delete_api_key(path)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
