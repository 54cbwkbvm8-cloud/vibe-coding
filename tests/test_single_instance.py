"""Windows 单实例互斥量测试。"""

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.win32.single_instance import SingleInstanceGuard  # noqa: E402


@unittest.skipUnless(sys.platform == "win32", "Windows mutex test")
class SingleInstanceTests(unittest.TestCase):
    def test_second_instance_is_rejected_until_first_releases(self) -> None:
        first = SingleInstanceGuard()
        second = SingleInstanceGuard()
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        first.release()
        self.assertTrue(second.acquire())
        second.release()


if __name__ == "__main__":
    unittest.main()
