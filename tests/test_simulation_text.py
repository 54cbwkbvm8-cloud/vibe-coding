"""不依赖 Qt 的模拟文本测试。"""

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.services.simulation_text import (  # noqa: E402
    build_simulated_answer,
    split_text,
)


class SimulationTextTests(unittest.TestCase):
    def test_answer_contains_question(self) -> None:
        answer = build_simulated_answer("什么是变量？")
        self.assertIn("什么是变量？", answer)
        self.assertIn("阶段 1", answer)

    def test_long_question_is_truncated(self) -> None:
        answer = build_simulated_answer("测" * 80)
        self.assertIn("...", answer)
        self.assertNotIn("测" * 80, answer)

    def test_chunks_rebuild_original_text(self) -> None:
        text = "模拟流式回答不会丢失任何字符。"
        chunks = split_text(text, chunk_size=4)
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(1 <= len(chunk) <= 4 for chunk in chunks))

    def test_invalid_chunk_size_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            split_text("abc", chunk_size=0)


if __name__ == "__main__":
    unittest.main()
