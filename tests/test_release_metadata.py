"""Release metadata and repository hygiene checks."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from ai_quiz_overlay.branding import APP_VERSION
from ai_quiz_overlay.config import ConfigError, validate_base_url
from ai_quiz_overlay.services.network_policy import (
    ALLOWED_MODEL_DOMAINS,
    OFFICIAL_API_ORIGIN,
)


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_release_version_is_one_zero_zero(self) -> None:
        self.assertEqual(APP_VERSION, "1.0.0")
        version_info = (ROOT / "build/version_info.txt").read_text(
            encoding="utf-8"
        )
        manifest = (ROOT / "build/app.manifest").read_text(
            encoding="utf-8"
        )
        self.assertIn("filevers=(1, 0, 0, 0)", version_info)
        self.assertIn("prodvers=(1, 0, 0, 0)", version_info)
        self.assertIn('FileVersion\', \'1.0.0.0\'', version_info)
        self.assertIn('version="1.0.0.0"', manifest)

    def test_runtime_requirements_are_exact(self) -> None:
        lines = [
            line.strip()
            for line in (ROOT / "requirements.lock").read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip() and not line.startswith("#")
        ]
        self.assertGreaterEqual(len(lines), 10)
        for line in lines:
            self.assertRegex(line, r"^[A-Za-z0-9_.-]+==[^=]+$")

    def test_third_party_notice_covers_bundled_subsystems(self) -> None:
        notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(
            encoding="utf-8"
        )
        for component in (
            "PySide6-Essentials",
            "Qt",
            "sherpa-onnx",
            "onnxruntime",
            "PortAudio",
            "sounddevice",
            "webrtcvad",
            "httpx",
        ):
            self.assertIn(component, notice)

    def test_gitignore_excludes_secrets_and_development_artifacts(self) -> None:
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in (
            "config.json",
            "api_key.bin",
            "personalization",
            "models/",
            "*.log",
            "work/",
            "dist/",
        ):
            self.assertIn(pattern, ignored)

    def test_api_origin_is_locked(self) -> None:
        self.assertEqual(OFFICIAL_API_ORIGIN, "https://api.deepseek.com")
        self.assertEqual(
            validate_base_url("https://api.deepseek.com/"),
            "https://api.deepseek.com",
        )
        with self.assertRaises(ConfigError):
            validate_base_url("https://example.com")
        with self.assertRaises(ConfigError):
            validate_base_url("http://api.deepseek.com")

    def test_model_domain_allowlist_is_exact(self) -> None:
        self.assertEqual(
            ALLOWED_MODEL_DOMAINS,
            {
                "hf-mirror.com",
                "cas-bridge.xethub.hf.co",
                "api.github.com",
                "release-assets.githubusercontent.com",
            },
        )

    def test_bundle_checker_has_release_guards(self) -> None:
        checker = (ROOT / "build/check_bundle.ps1").read_text(
            encoding="utf-8"
        )
        for guard in (
            "THIRD_PARTY_NOTICES.md",
            "config.json",
            "api_key.bin",
            "model.int8.onnx",
            "tokens.txt",
            "personalization",
            "official-web-host.exe",
            "official-web-manifest.json",
            "official_web_browser_host.py",
            "official_web_diagnostics.py",
            "official_web_diagnostic_build.py",
            "QtWebEngineProcess.exe",
            "Qt6WebEngineCore.dll",
        ):
            self.assertIn(guard, checker)

    def test_main_spec_excludes_optional_webengine_and_diagnostics(self) -> None:
        spec = (ROOT / "build/ai_quiz_overlay.spec").read_text(
            encoding="utf-8"
        )
        for module in (
            "PySide6.QtWebEngineCore",
            "PySide6.QtWebEngineWidgets",
            "official_web_browser_host",
            "official_web_diagnostics",
            "official_web_diagnostic_build",
        ):
            self.assertIn(f'"{module}"', spec)

    def test_readme_has_no_diagnostic_component_delivery_steps(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("--enable-diagnostics", readme)
        self.assertNotIn("official-web-component-diagnostics", readme)


if __name__ == "__main__":
    unittest.main()
