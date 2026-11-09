"""Windows Acrylic capability and forced fallback tests."""

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.win32.acrylic import (  # noqa: E402
    ACRYLIC_FALLBACK_ENV,
    DWMWCP_DONOTROUND,
    DWMWCP_ROUND,
    acrylic_availability,
    corner_preference_for_backdrop,
    should_apply_acrylic,
)


class AcrylicTests(unittest.TestCase):
    def test_win10_routes_to_qt_fallback(self) -> None:
        self.assertFalse(
            should_apply_acrylic(
                enabled=True,
                windows_build=19045,
                environment={},
            )
        )

    def test_win11_before_alpha_rounding_routes_to_fallback(self) -> None:
        self.assertFalse(
            should_apply_acrylic(
                enabled=True,
                windows_build=22621,
                environment={},
            )
        )

    def test_win11_26100_and_above_use_qt_after_validation_failed(
        self,
    ) -> None:
        for build in (26100, 26200):
            with self.subTest(build=build):
                availability = acrylic_availability(
                    windows_build=build,
                    environment={},
                )
                self.assertFalse(availability.supported)
                self.assertIn("验证未通过", availability.reason)
                self.assertIn("自绘玻璃", availability.reason)

    def test_win11_22621_to_26099_explains_round_capability_limit(
        self,
    ) -> None:
        for build in (22621, 26099):
            with self.subTest(build=build):
                availability = acrylic_availability(
                    windows_build=build,
                    environment={},
                )
                self.assertFalse(availability.supported)
                self.assertIn("圆角窗口", availability.reason)

    def test_windows10_explains_fallback(self) -> None:
        availability = acrylic_availability(
            windows_build=19045,
            environment={},
        )
        self.assertFalse(availability.supported)
        self.assertIn("Windows 10", availability.reason)

    def test_disabled_setting_forces_fallback(self) -> None:
        self.assertFalse(
            should_apply_acrylic(
                enabled=False,
                windows_build=26100,
                environment={},
            )
        )

    def test_environment_override_forces_fallback(self) -> None:
        self.assertFalse(
            should_apply_acrylic(
                enabled=True,
                windows_build=26200,
                environment={ACRYLIC_FALLBACK_ENV: "1"},
            )
        )

    def test_qt_fallback_disables_dwm_round_corner_shadow(self) -> None:
        self.assertEqual(
            corner_preference_for_backdrop(False),
            DWMWCP_DONOTROUND,
        )
        self.assertEqual(
            corner_preference_for_backdrop(True),
            DWMWCP_ROUND,
        )


if __name__ == "__main__":
    unittest.main()
