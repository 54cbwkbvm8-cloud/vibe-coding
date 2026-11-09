"""Model supply-chain, fixed hashes, and safe archive extraction tests."""

from io import BytesIO
import hashlib
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.services import voice_models  # noqa: E402
from ai_quiz_overlay.services.voice_models import (  # noqa: E402
    GITHUB_ARCHIVE_PREFIX,
    GITHUB_RELEASE_SOURCE,
    HF_MIRROR_SOURCE,
    MODEL_FILE_NAME,
    MODEL_REVISION,
    MODEL_SHA256,
    MODEL_SOURCE_BY_KEY,
    TOKENS_FILE_NAME,
    TOKENS_SHA256,
    ModelDownloadError,
    _SafeRedirectHandler,
    _extract_required_archive_files,
    import_model_directory,
    install_model_from_source,
    validate_download_url,
)


class VoiceModelTests(unittest.TestCase):
    def test_expected_hashes_and_sources_are_hardcoded(self) -> None:
        self.assertEqual(
            MODEL_REVISION,
            "2365baeacb507f821a0c8120fcee3d484dba7a07",
        )
        self.assertEqual(
            MODEL_SHA256,
            "c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51",
        )
        self.assertEqual(
            TOKENS_SHA256,
            "f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc",
        )
        self.assertEqual(
            MODEL_SOURCE_BY_KEY["hf_mirror"].domains,
            ("hf-mirror.com", "cas-bridge.xethub.hf.co"),
        )
        self.assertEqual(
            MODEL_SOURCE_BY_KEY["github_release"].domains,
            (
                "api.github.com",
                "release-assets.githubusercontent.com",
            ),
        )
        self.assertTrue(HF_MIRROR_SOURCE.recommended)
        self.assertEqual(len(MODEL_SOURCE_BY_KEY), 2)
        self.assertNotIn("modelscope", MODEL_SOURCE_BY_KEY)

    def test_https_whitelist_rejects_http_and_unknown_domain(self) -> None:
        with self.assertRaises(ModelDownloadError):
            validate_download_url(
                "http://hf-mirror.com/model",
                HF_MIRROR_SOURCE.domains,
            )
        with self.assertRaises(ModelDownloadError):
            validate_download_url(
                "https://example.com/model",
                HF_MIRROR_SOURCE.domains,
            )

    def test_cross_domain_redirect_strips_cookie_and_authorization(self) -> None:
        handler = _SafeRedirectHandler(
            ("hf-mirror.com", "cas-bridge.xethub.hf.co")
        )
        bearer_value = "".join(("Bear", "er synthetic-placeholder"))
        request = urllib.request.Request(
            "https://hf-mirror.com/model",
            headers={
                "Authorization": bearer_value,
                "Cookie": "synthetic-session-placeholder",
                "Accept": "application/octet-stream",
            },
        )
        redirected = handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://cas-bridge.xethub.hf.co/object",
        )
        self.assertIsNotNone(redirected)
        self.assertNotIn("Authorization", redirected.headers)
        self.assertNotIn("Cookie", redirected.headers)
        self.assertEqual(
            redirected.headers["Accept"],
            "application/octet-stream",
        )

    def test_more_than_three_redirects_is_rejected(self) -> None:
        handler = _SafeRedirectHandler(("hf-mirror.com",))
        request = urllib.request.Request("https://hf-mirror.com/model")
        for _index in range(3):
            request = handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "https://hf-mirror.com/next",
            )
        with self.assertRaises(ModelDownloadError):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "https://hf-mirror.com/too-many",
            )

    def test_hash_failure_deletes_partial_download(self) -> None:
        artifact = HF_MIRROR_SOURCE.artifacts[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def fake_download(
                _artifact,
                _source,
                target,
                _progress,
                _cancel_event,
            ):
                target.write_bytes(b"wrong")

            with mock.patch.object(
                voice_models,
                "_download_artifact",
                side_effect=fake_download,
            ):
                with self.assertRaises(ModelDownloadError):
                    install_model_from_source(
                        HF_MIRROR_SOURCE,
                        root / "model",
                    )
            self.assertFalse((root / "model" / MODEL_FILE_NAME).exists())
            self.assertFalse((root / "model" / TOKENS_FILE_NAME).exists())
            self.assertEqual(
                list(root.glob(".voice-model-*")),
                [],
            )

    def test_disk_space_is_checked_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            download = mock.Mock()
            with (
                mock.patch.object(
                    voice_models,
                    "_download_artifact",
                    download,
                ),
                mock.patch.object(
                    voice_models,
                    "_ensure_disk_space",
                    side_effect=ModelDownloadError("磁盘空间不足"),
                ),
            ):
                with self.assertRaises(ModelDownloadError):
                    install_model_from_source(
                        HF_MIRROR_SOURCE,
                        root / "model",
                    )
            download.assert_not_called()

    def test_failed_download_can_be_retried_cleanly(self) -> None:
        payloads = {
            MODEL_FILE_NAME: b"model-ok",
            TOKENS_FILE_NAME: b"tokens-ok",
        }
        expected = {
            name: (
                len(content),
                hashlib.sha256(content).hexdigest(),
            )
            for name, content in payloads.items()
        }
        fail_once = {"value": True}

        def fake_download(
            artifact,
            _source,
            target,
            _progress,
            _cancel_event,
        ):
            if fail_once["value"]:
                fail_once["value"] = False
                target.write_bytes(b"partial")
                raise ModelDownloadError("网络中断")
            target.write_bytes(payloads[artifact.file_name])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.dict(
                    voice_models.EXPECTED_MODEL_FILES,
                    expected,
                    clear=True,
                ),
                mock.patch.object(
                    voice_models,
                    "_download_artifact",
                    side_effect=fake_download,
                ),
            ):
                with self.assertRaises(ModelDownloadError):
                    install_model_from_source(
                        HF_MIRROR_SOURCE,
                        root / "model",
                    )
                self.assertFalse((root / "model" / MODEL_FILE_NAME).exists())
                install_model_from_source(
                    HF_MIRROR_SOURCE,
                    root / "model",
                )
                valid, _message = voice_models.validate_model_directory(
                    root / "model"
                )
            self.assertTrue(valid)
            self.assertEqual(
                (root / "model" / MODEL_FILE_NAME).read_bytes(),
                payloads[MODEL_FILE_NAME],
            )

    def _write_archive(
        self,
        path: Path,
        entries: dict[str, bytes],
    ) -> None:
        with tarfile.open(path, "w:bz2") as archive:
            for name, content in entries.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, BytesIO(content))

    def test_archive_reads_only_exact_target_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "model.tar.bz2"
            self._write_archive(
                archive_path,
                {
                    f"{GITHUB_ARCHIVE_PREFIX}/{MODEL_FILE_NAME}": b"model",
                    f"{GITHUB_ARCHIVE_PREFIX}/{TOKENS_FILE_NAME}": b"tokens",
                    f"{GITHUB_ARCHIVE_PREFIX}/README.md": b"ignored",
                },
            )
            output = root / "out"
            output.mkdir()
            _extract_required_archive_files(archive_path, output)
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                sorted((MODEL_FILE_NAME, TOKENS_FILE_NAME)),
            )
            self.assertEqual(
                (output / MODEL_FILE_NAME).read_bytes(),
                b"model",
            )

    def test_archive_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "model.tar.bz2"
            self._write_archive(
                archive_path,
                {
                    "../escape.txt": b"bad",
                    f"{GITHUB_ARCHIVE_PREFIX}/{MODEL_FILE_NAME}": b"model",
                    f"{GITHUB_ARCHIVE_PREFIX}/{TOKENS_FILE_NAME}": b"tokens",
                },
            )
            with self.assertRaises(ModelDownloadError):
                _extract_required_archive_files(
                    archive_path,
                    root / "out",
                )

    def test_archive_rejects_windows_drive_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "model.tar.bz2"
            self._write_archive(
                archive_path,
                {
                    "C:/escape.txt": b"bad",
                    f"{GITHUB_ARCHIVE_PREFIX}/{MODEL_FILE_NAME}": b"model",
                    f"{GITHUB_ARCHIVE_PREFIX}/{TOKENS_FILE_NAME}": b"tokens",
                },
            )
            with self.assertRaises(ModelDownloadError):
                _extract_required_archive_files(
                    archive_path,
                    root / "out",
                )

    def test_archive_extraction_size_cap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "model.tar.bz2"
            self._write_archive(
                archive_path,
                {
                    f"{GITHUB_ARCHIVE_PREFIX}/{MODEL_FILE_NAME}": b"12345",
                    f"{GITHUB_ARCHIVE_PREFIX}/{TOKENS_FILE_NAME}": b"12345",
                },
            )
            with mock.patch.dict(
                voice_models.EXPECTED_MODEL_FILES,
                {
                    MODEL_FILE_NAME: (2, "a"),
                    TOKENS_FILE_NAME: (2, "b"),
                },
                clear=True,
            ):
                with self.assertRaises(ModelDownloadError):
                    _extract_required_archive_files(
                        archive_path,
                        root / "out",
                    )

    def test_manual_import_rejects_wrong_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / MODEL_FILE_NAME).write_bytes(b"model")
            (source / TOKENS_FILE_NAME).write_bytes(b"tokens")
            with (
                mock.patch.dict(
                    voice_models.EXPECTED_MODEL_FILES,
                    {
                        MODEL_FILE_NAME: (5, "0" * 64),
                        TOKENS_FILE_NAME: (6, "1" * 64),
                    },
                    clear=True,
                ),
            ):
                with self.assertRaises(ModelDownloadError):
                    import_model_directory(source, root / "model")
            self.assertFalse((root / "model" / MODEL_FILE_NAME).exists())

    def test_manual_import_accepts_matching_hashes(self) -> None:
        payloads = {
            MODEL_FILE_NAME: b"model-good",
            TOKENS_FILE_NAME: b"tokens-good",
        }
        expected = {
            name: (
                len(content),
                hashlib.sha256(content).hexdigest(),
            )
            for name, content in payloads.items()
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            for name, content in payloads.items():
                (source / name).write_bytes(content)
            with mock.patch.dict(
                voice_models.EXPECTED_MODEL_FILES,
                expected,
                clear=True,
            ):
                import_model_directory(source, root / "model")
            self.assertEqual(
                (root / "model" / TOKENS_FILE_NAME).read_bytes(),
                payloads[TOKENS_FILE_NAME],
            )

    def test_github_archive_metadata_matches_verified_release_asset(self) -> None:
        artifact = GITHUB_RELEASE_SOURCE.artifacts[0]
        self.assertEqual(artifact.size, 163_002_883)
        self.assertEqual(
            artifact.sha256,
            "7d1efa2138a65b0b488df37f8b89e3d91a60676e416f515b952358d83dfd347e",
        )


if __name__ == "__main__":
    unittest.main()
