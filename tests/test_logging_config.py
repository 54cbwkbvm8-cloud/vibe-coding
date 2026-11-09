"""日志轮转测试。"""

from pathlib import Path
import logging
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.logging_config import create_rotating_handler  # noqa: E402


class LoggingConfigTests(unittest.TestCase):
    def test_log_file_rotates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_file = Path(directory) / "app.log"
            handler = create_rotating_handler(
                log_file,
                max_bytes=220,
                backup_count=2,
            )
            logger = logging.getLogger("rotation-test")
            logger.setLevel(logging.INFO)
            logger.propagate = False
            logger.handlers.clear()
            logger.addHandler(handler)

            for index in range(30):
                logger.info("event=test status_code=- error_type=- index=%s", index)

            handler.close()
            logger.removeHandler(handler)
            self.assertTrue(log_file.exists())
            self.assertTrue((Path(directory) / "app.log.1").exists())


if __name__ == "__main__":
    unittest.main()
