"""ModeCoordinator transition tests."""

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.mode_coordinator import ModeCoordinator  # noqa: E402


class FakeMode:
    def __init__(self, key: str, events: list[str]) -> None:
        self.definition = type("Definition", (), {"key": key})()
        self.events = events

    def activate(self) -> None:
        self.events.append(f"activate:{self.definition.key}")

    def deactivate(self, cancel_request: bool = True) -> None:
        self.events.append(
            f"deactivate:{self.definition.key}:{cancel_request}"
        )

    def is_busy(self) -> bool:
        return False


class ModeCoordinatorTests(unittest.TestCase):
    def test_transition_deactivates_old_before_activating_new(self) -> None:
        events: list[str] = []
        quiz = FakeMode("quiz", events)
        assistant = FakeMode("global_assistant", events)
        coordinator = ModeCoordinator(quiz)
        coordinator.activate()
        coordinator.transition_to(assistant, cancel_request=False)
        self.assertEqual(
            events,
            [
                "activate:quiz",
                "deactivate:quiz:False",
                "activate:global_assistant",
            ],
        )
        self.assertIs(coordinator.current, assistant)

    def test_same_mode_transition_does_not_reactivate(self) -> None:
        events: list[str] = []
        quiz = FakeMode("quiz", events)
        replacement = FakeMode("quiz", events)
        coordinator = ModeCoordinator(quiz)
        coordinator.transition_to(replacement)
        self.assertEqual(events, [])
        self.assertIs(coordinator.current, replacement)


if __name__ == "__main__":
    unittest.main()
