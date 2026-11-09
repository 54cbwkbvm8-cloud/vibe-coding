"""Direct IShellLink shortcut tests with command-injection markers."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.branding import asset_path  # noqa: E402
from ai_quiz_overlay.win32.shortcut import (  # noqa: E402
    ShortcutError,
    _write_shortcut,
    create_desktop_shortcut,
    delete_owned_desktop_shortcut,
    desktop_shortcut_path,
    inspect_shortcut,
    sanitize_shortcut_filename,
    shortcut_icon_location,
    shortcut_target,
    shortcut_working_directory,
)


@unittest.skipUnless(sys.platform == "win32", "Windows IShellLink only")
class ShortcutTests(unittest.TestCase):
    def test_special_characters_are_data_not_shell_commands(self) -> None:
        filename = sanitize_shortcut_filename(
            '"奶蛙"; & % `echo injected`'
        )
        self.assertTrue(filename.endswith(".lnk"))
        self.assertNotIn('"', filename)
        self.assertIn("&", filename)
        self.assertIn("%", filename)
        with tempfile.TemporaryDirectory() as directory:
            shortcut = Path(directory) / filename
            with (
                mock.patch.object(
                    subprocess,
                    "run",
                    side_effect=AssertionError("subprocess must not run"),
                ),
                mock.patch.object(
                    subprocess,
                    "Popen",
                    side_effect=AssertionError("subprocess must not run"),
                ),
            ):
                _write_shortcut(
                    shortcut,
                    target=Path(sys.executable),
                    working_directory=Path(sys.executable).parent,
                    icon_path=asset_path("brand", "app_icon.ico"),
                )
            inspection = inspect_shortcut(shortcut)
            self.assertTrue(inspection.exists)
            self.assertTrue(inspection.owned)
            self.assertEqual(
                Path(shortcut_target(shortcut)),
                Path(sys.executable),
            )
            self.assertEqual(
                Path(shortcut_working_directory(shortcut)),
                Path(sys.executable).parent,
            )
            self.assertEqual(
                Path(shortcut_icon_location(shortcut)),
                asset_path("brand", "app_icon.ico"),
            )

    def test_foreign_shortcut_is_not_considered_owned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "foreign.lnk"
            path.write_bytes(b"not a shell link")
            inspection = inspect_shortcut(path)
            self.assertTrue(inspection.exists)
            self.assertFalse(inspection.owned)

    def test_desktop_path_uses_known_folder_api(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            desktop = Path(directory)
            with mock.patch(
                "ai_quiz_overlay.win32.shortcut._known_desktop_directory",
                return_value=desktop,
            ):
                path = desktop_shortcut_path("奶蛙 & 朋友")
            self.assertEqual(path.parent, desktop)
            self.assertTrue(path.name.endswith(".lnk"))

    def test_foreign_shortcut_requires_explicit_overwrite_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            shortcut = Path(directory) / "foreign.lnk"
            shortcut.write_bytes(b"foreign")
            with mock.patch(
                "ai_quiz_overlay.win32.shortcut.desktop_shortcut_path",
                return_value=shortcut,
            ):
                with self.assertRaises(ShortcutError):
                    create_desktop_shortcut("foreign")
                with self.assertRaises(ShortcutError):
                    delete_owned_desktop_shortcut("foreign")
                result = create_desktop_shortcut(
                    "foreign",
                    target=Path(sys.executable),
                    icon_path=asset_path("brand", "app_icon.ico"),
                    overwrite_foreign=True,
                )
                self.assertEqual(result, shortcut)
                self.assertTrue(inspect_shortcut(shortcut).owned)
                self.assertTrue(delete_owned_desktop_shortcut("foreign"))
                self.assertFalse(shortcut.exists())

    def test_reserved_filename_is_prefixed(self) -> None:
        self.assertEqual(
            sanitize_shortcut_filename("CON"),
            "_CON.lnk",
        )
        self.assertEqual(
            sanitize_shortcut_filename('bad<>:"/\\|?*'),
            "bad.lnk",
        )


if __name__ == "__main__":
    unittest.main()
