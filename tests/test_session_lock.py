"""Session lock notification routing tests."""

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.win32.session_lock import (  # noqa: E402
    WM_WTSSESSION_CHANGE,
    WTS_SESSION_LOCK,
    WTS_SESSION_LOGOFF,
    is_recording_stop_session_event,
)


class SessionLockTests(unittest.TestCase):
    def test_lock_and_logoff_stop_recording(self) -> None:
        self.assertTrue(
            is_recording_stop_session_event(
                WM_WTSSESSION_CHANGE,
                WTS_SESSION_LOCK,
            )
        )
        self.assertTrue(
            is_recording_stop_session_event(
                WM_WTSSESSION_CHANGE,
                WTS_SESSION_LOGOFF,
            )
        )

    def test_unrelated_session_change_does_not_stop_recording(self) -> None:
        self.assertFalse(is_recording_stop_session_event(0x0100, 7))
        self.assertFalse(
            is_recording_stop_session_event(WM_WTSSESSION_CHANGE, 1)
        )


if __name__ == "__main__":
    unittest.main()
