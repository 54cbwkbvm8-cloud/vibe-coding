"""多轮对话历史测试。"""

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_quiz_overlay.services.chat_session import (  # noqa: E402
    ASSISTANT_SYSTEM_PROMPT,
    ChatSession,
    SYSTEM_PROMPT,
)


class ChatSessionTests(unittest.TestCase):
    def test_assistant_prompt_does_not_use_quiz_format(self) -> None:
        session = ChatSession(ASSISTANT_SYSTEM_PROMPT)
        messages = session.begin_turn("你好")
        self.assertEqual(
            messages[0]["content"],
            ASSISTANT_SYSTEM_PROMPT,
        )
        self.assertIn("直接回答", messages[0]["content"])
        self.assertNotIn("回答必须遵循以下顺序", messages[0]["content"])

    def test_completed_turns_are_included_in_next_request(self) -> None:
        session = ChatSession()
        first_messages = session.begin_turn("第一问")
        self.assertEqual(first_messages[0]["content"], SYSTEM_PROMPT)
        session.complete_turn("第一答")

        second_messages = session.begin_turn("第二问")
        self.assertEqual(
            [item["role"] for item in second_messages],
            ["system", "user", "assistant", "user"],
        )
        self.assertEqual(second_messages[1]["content"], "第一问")
        self.assertEqual(second_messages[2]["content"], "第一答")

    def test_cancelled_turn_rolls_back_user_message(self) -> None:
        session = ChatSession()
        session.begin_turn("不会保留的问题")
        session.cancel_turn()
        self.assertEqual(session.messages, [])
        self.assertEqual(session.turn_count, 0)

    def test_clear_removes_history(self) -> None:
        session = ChatSession()
        session.begin_turn("问题")
        session.complete_turn("回答")
        session.clear()
        self.assertEqual(session.messages, [])

    def test_image_is_removed_from_follow_up_history(self) -> None:
        session = ChatSession()
        image_url = "data:image/png;base64,FAKE_IMAGE_DATA"
        first = session.begin_turn("看图回答", image_data_url=image_url)
        self.assertIsInstance(first[-1]["content"], list)
        session.complete_turn("截图答案")

        second = session.begin_turn("继续追问")
        serialized = str(second)
        self.assertNotIn(image_url, serialized)
        self.assertIn("本轮包含一张截图", serialized)


if __name__ == "__main__":
    unittest.main()
