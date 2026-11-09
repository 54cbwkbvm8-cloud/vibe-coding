"""Brand names, DPI assets, and Windows icon packaging tests."""

from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QLabel


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.branding import (  # noqa: E402
    APP_VERSION,
    INTERFACE_NAME,
    SOFTWARE_NAME,
    asset_path,
)
from ai_quiz_overlay.config import APP_DIRECTORY_NAME  # noqa: E402
from ai_quiz_overlay.config import AppConfig, PersonalizationConfig  # noqa: E402
from ai_quiz_overlay.personalization_runtime import (  # noqa: E402
    runtime_from_config,
    runtime_from_personalization,
    set_brand_runtime,
)
from ai_quiz_overlay.ui.tray_controller import TrayController  # noqa: E402
from ai_quiz_overlay.ui.brand_assets import (  # noqa: E402
    LOGO_LOGICAL_SIZE,
    load_app_icon,
    load_logo_icon,
)
from ai_quiz_overlay.ui.main_window import MainWindow  # noqa: E402
from ai_quiz_overlay.ui.title_bar import TitleBar  # noqa: E402
from ai_quiz_overlay.ui.about_dialog import show_about_dialog  # noqa: E402
from ai_quiz_overlay.ui.assistant_ball import AssistantBall  # noqa: E402
from ai_quiz_overlay.services.personalization_assets import (  # noqa: E402
    masked_circle,
    write_multi_size_ico,
)


class BrandingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_names_and_compatibility_path_are_stable(self) -> None:
        self.assertEqual(INTERFACE_NAME, "超级奶蛙助手")
        self.assertEqual(SOFTWARE_NAME, "奶蛙的荣光")
        self.assertEqual(APP_VERSION, "1.0.0")
        self.assertEqual(APP_DIRECTORY_NAME, "AIQuizOverlay")

    def test_logo_assets_have_expected_sizes_and_transparent_corners(self) -> None:
        for scale in (1, 2, 3):
            path = asset_path("brand", f"logo@{scale}x.png")
            image = QImage(str(path))
            self.assertFalse(image.isNull())
            expected = LOGO_LOGICAL_SIZE * scale
            self.assertEqual(image.size(), QSize(expected, expected))
            self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
            center = image.pixelColor(expected // 2, expected // 2)
            self.assertGreater(center.alpha(), 0)

    def test_windows_icon_contains_all_required_sizes(self) -> None:
        icon_path = asset_path("brand", "app_icon.ico")
        data = icon_path.read_bytes()
        reserved, image_type, count = struct.unpack_from("<HHH", data)
        self.assertEqual((reserved, image_type), (0, 1))
        sizes = set()
        for index in range(count):
            offset = 6 + index * 16
            width, height = data[offset], data[offset + 1]
            sizes.add(
                (
                    256 if width == 0 else width,
                    256 if height == 0 else height,
                )
            )
        self.assertEqual(
            sizes,
            {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)},
        )

    def test_assistant_ball_assets_support_max_high_dpi_size(self) -> None:
        source = QImage(
            str(asset_path("brand", "assistant_ball_1024.png"))
        )
        self.assertEqual(source.size(), QSize(1024, 1024))
        self.assertEqual(source.pixelColor(0, 0).alpha(), 0)
        for scale, expected in ((1, 160), (2, 320), (3, 480)):
            image = QImage(
                str(asset_path("brand", f"assistant_ball@{scale}x.png"))
            )
            self.assertEqual(image.size(), QSize(expected, expected))
            self.assertEqual(image.pixelColor(0, 0).alpha(), 0)
            self.assertGreater(
                image.pixelColor(expected // 2, expected // 2).alpha(),
                0,
            )

    def test_qt_icons_load_high_dpi_assets(self) -> None:
        logo = load_logo_icon()
        app_icon = load_app_icon()
        self.assertFalse(logo.isNull())
        self.assertFalse(app_icon.isNull())
        self.assertIn(QSize(28, 28), logo.availableSizes())
        self.assertIn(QSize(56, 56), logo.availableSizes())
        self.assertIn(QSize(84, 84), logo.availableSizes())

    def test_title_bar_uses_interface_name_and_logo(self) -> None:
        title_bar = TitleBar()
        title = title_bar.findChild(QLabel, "titleLabel")
        logo = title_bar.findChild(QLabel, "titleLogo")
        self.assertIsNotNone(title)
        self.assertIsNotNone(logo)
        self.assertEqual(title.text(), INTERFACE_NAME)
        self.assertFalse(logo.pixmap().isNull())
        self.assertEqual(logo.size(), QSize(LOGO_LOGICAL_SIZE, LOGO_LOGICAL_SIZE))

    def test_main_window_uses_software_name_and_app_icon(self) -> None:
        window = MainWindow()
        self.assertEqual(window.windowTitle(), SOFTWARE_NAME)
        self.assertFalse(window.windowIcon().isNull())
        window.deleteLater()

    def test_custom_names_remain_plain_text_in_title_and_tray(self) -> None:
        runtime = runtime_from_config(
            AppConfig(
                personalization=PersonalizationConfig(
                    interface_name="<b>A&B</b>",
                    software_name="S&T <b>Studio</b>",
                )
            ),
            revision=7,
        )
        set_brand_runtime(runtime)
        try:
            title_bar = TitleBar()
            self.assertEqual(
                title_bar.title_label.textFormat(),
                Qt.TextFormat.PlainText,
            )
            self.assertEqual(title_bar.interface_name, "<b>A&B</b>")
            tray = TrayController()
            self.assertEqual(
                tray.show_action.text(),
                "显示<b>A&&B</b>",
            )
            self.assertEqual(
                tray.about_action.text(),
                "关于 S&&T <b>Studio</b>",
            )
            tray.deleteLater()
            title_bar.deleteLater()
        finally:
            set_brand_runtime(runtime_from_config(AppConfig()))

    def test_custom_app_logo_and_ball_assets_apply_at_runtime(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            square = QImage(512, 512, QImage.Format.Format_ARGB32)
            square.fill(QColor("#d51fd1"))
            write_multi_size_ico(square, root / "app.ico")
            masked_circle(square, 512).save(
                str(root / "logo.png"),
                "PNG",
            )
            masked_circle(square, 512).save(
                str(root / "ball.png"),
                "PNG",
            )
            runtime = runtime_from_personalization(
                PersonalizationConfig(
                    app_icon_asset="app.ico",
                    title_logo_asset="logo.png",
                    ball_image_asset="ball.png",
                ),
                asset_directory=root,
                revision=22,
            )
            set_brand_runtime(runtime)
            try:
                title = TitleBar()
                title.apply_brand(runtime)
                self.assertFalse(title.logo.pixmap().isNull())
                window = MainWindow()
                window.apply_brand(runtime)
                self.assertTrue(
                    window.windowIcon().availableSizes()
                )
                ball = AssistantBall()
                ball.apply_brand(runtime)
                ball.show_without_activation()
                self.app.processEvents()
                center = ball.grab().toImage().pixelColor(
                    ball.width() // 2,
                    ball.height() // 2,
                )
                self.assertGreater(center.red(), center.green())
                ball.hide()
                ball.deleteLater()
                window.deleteLater()
                title.deleteLater()
            finally:
                set_brand_runtime(runtime_from_config(AppConfig()))

    def test_about_dialog_uses_plain_custom_names(self) -> None:
        runtime = runtime_from_config(
            AppConfig(
                personalization=PersonalizationConfig(
                    interface_name="<b>界面</b> & 名称",
                    software_name="<b>软件</b> & 名称",
                )
            ),
            revision=31,
        )
        set_brand_runtime(runtime)
        dialog = MagicMock()
        dialog.button.return_value = None
        try:
            with patch(
                "ai_quiz_overlay.ui.about_dialog.QMessageBox",
                return_value=dialog,
            ):
                show_about_dialog()
            dialog.setTextFormat.assert_called_with(
                Qt.TextFormat.PlainText
            )
            self.assertIn(
                "<b>软件</b> & 名称",
                dialog.setText.call_args.args[0],
            )
            self.assertIn(
                "<b>界面</b> & 名称",
                dialog.setInformativeText.call_args.args[0],
            )
        finally:
            set_brand_runtime(runtime_from_config(AppConfig()))


if __name__ == "__main__":
    unittest.main()
