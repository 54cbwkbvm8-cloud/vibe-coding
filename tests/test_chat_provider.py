"""Unified ChatProvider and generic worker tests with local fake data."""

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from ai_quiz_overlay.config import AppConfig  # noqa: E402
from ai_quiz_overlay.services.chat_provider import (  # noqa: E402
    ChatRequest,
    ProviderCancelledError,
    ProviderCapabilities,
    ProviderUnavailableError,
)
from ai_quiz_overlay.services.deepseek_provider import (  # noqa: E402
    DeepSeekApiProvider,
)
from ai_quiz_overlay.services.provider_registry import (  # noqa: E402
    create_chat_provider,
)
from ai_quiz_overlay.services.official_web_provider import (  # noqa: E402
    OfficialWebProvider,
)
from ai_quiz_overlay.services.provider_worker import ProviderChatWorker  # noqa: E402
from mock_deepseek_server import MockDeepSeekServer  # noqa: E402


class FakeStream:
    def __init__(self, chunks: list[str], cancelled: bool = False) -> None:
        self._chunks = chunks
        self._cancelled = cancelled
        self.closed = False

    def __iter__(self):
        if self._cancelled:
            raise ProviderCancelledError()
        yield from self._chunks

    def close(self) -> None:
        self.closed = True


class FakeProvider:
    provider_id = "fake"
    display_name = "Fake"
    capabilities = ProviderCapabilities(streaming=True, images=False)

    def __init__(self, stream: FakeStream) -> None:
        self.stream = stream

    def image_support_error(self, model: str) -> str | None:
        return "fake-images-unsupported"

    def open_stream(self, request: ChatRequest):
        return self.stream


class ChatProviderTests(unittest.TestCase):
    def test_provider_registry_enables_api_and_rejects_future_login(
        self,
    ) -> None:
        self.assertIsInstance(create_chat_provider("api"), DeepSeekApiProvider)
        official = create_chat_provider("official_login")
        self.assertIsInstance(official, OfficialWebProvider)
        self.assertTrue(official.capabilities.login_required)
        self.assertFalse(official.capabilities.images)
        self.assertFalse(official.capabilities.stop_generation)
        with self.assertRaises(ProviderUnavailableError):
            official.open_stream(ChatRequest(AppConfig(), "", []))
        with self.assertRaises(ProviderUnavailableError):
            create_chat_provider("official_browser")

    def test_generic_worker_emits_standard_stream_signals(self) -> None:
        stream = FakeStream(["甲", "乙"])
        worker = ProviderChatWorker(
            FakeProvider(stream),
            ChatRequest(AppConfig(), "fake", []),
        )
        chunks: list[str] = []
        completed: list[str] = []
        worker.chunk_ready.connect(chunks.append)
        worker.completed.connect(completed.append)
        worker.run()
        self.assertEqual(chunks, ["甲", "乙"])
        self.assertEqual(completed, ["甲乙"])
        self.assertTrue(stream.closed)

    def test_generic_worker_preserves_cancellation(self) -> None:
        stream = FakeStream([], cancelled=True)
        worker = ProviderChatWorker(
            FakeProvider(stream),
            ChatRequest(AppConfig(), "fake", []),
        )
        cancelled: list[str] = []
        worker.cancelled.connect(cancelled.append)
        worker.run()
        self.assertEqual(cancelled, [""])
        self.assertTrue(stream.closed)

    def test_deepseek_provider_reads_local_mock_stream(self) -> None:
        server = MockDeepSeekServer()
        server.start()
        try:
            config = AppConfig(
                base_url=server.base_url,
                model="deepseek-flash",
                timeout_seconds=3,
            )
            provider = DeepSeekApiProvider()
            stream = provider.open_stream(
                ChatRequest(config, "fake-ok", [{"role": "user", "content": "题"}])
            )
            try:
                answer = "".join(stream)
            finally:
                stream.close()
            self.assertIn("结果是 5", answer)
            self.assertIsNone(provider.image_support_error("deepseek-flash"))
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
