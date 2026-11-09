"""多轮对话历史管理。"""

from __future__ import annotations

import copy


SYSTEM_PROMPT = (
    "你是一名耐心的学习辅导助手。回答必须遵循以下顺序："
    "1. 先说明解题思路；"
    "2. 再按步骤推导和解释；"
    "3. 最后明确给出最终答案。"
    "不要跳过思路直接给答案。代码使用 Markdown 代码块；"
    "数学公式使用可读的 LaTeX 或纯文本表示。"
)

ASSISTANT_SYSTEM_PROMPT = (
    "你是一名简洁、可靠的通用助手。直接回答问题，优先给出结论和可执行建议；"
    "不要强行使用“思路—步骤—答案”的搜题格式。需要解释时保持清楚，"
    "但不要重复用户问题。代码使用 Markdown 代码块。"
)


class ChatSession:
    """保存除 system 提示词之外的多轮 user/assistant 消息。"""

    def __init__(self, system_prompt: str = SYSTEM_PROMPT) -> None:
        self._system_prompt = system_prompt
        self._messages: list[dict[str, object]] = []
        self._pending_user = False
        self._pending_history_content: str | None = None

    @property
    def messages(self) -> list[dict[str, object]]:
        return copy.deepcopy(self._messages)

    @property
    def turn_count(self) -> int:
        return sum(1 for message in self._messages if message["role"] == "user")

    def begin_turn(
        self,
        question: str,
        image_data_url: str | None = None,
    ) -> list[dict[str, object]]:
        """加入本轮问题并返回可直接发送的完整消息列表。"""
        if self._pending_user:
            raise RuntimeError("上一轮对话尚未结束。")

        clean_question = question.strip()
        if not clean_question and image_data_url:
            clean_question = "请解答这张截图中的题目。"
        if not clean_question:
            raise ValueError("问题不能为空。")

        if image_data_url:
            api_content = [
                {"type": "text", "text": clean_question},
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_url},
                },
            ]
            history_content = (
                f"{clean_question}\n\n"
                "[本轮包含一张截图；为避免重复上传，后续历史只保留问题和回答。]"
            )
        else:
            api_content = clean_question
            history_content = clean_question

        self._messages.append({"role": "user", "content": api_content})
        self._pending_user = True
        self._pending_history_content = history_content
        return copy.deepcopy([
            {"role": "system", "content": self._system_prompt},
            *self._messages,
        ])

    def complete_turn(self, answer: str) -> None:
        if not self._pending_user:
            raise RuntimeError("没有等待完成的对话。")
        if self._pending_history_content is not None:
            self._messages[-1]["content"] = self._pending_history_content
        self._messages.append({"role": "assistant", "content": answer})
        self._pending_user = False
        self._pending_history_content = None

    def cancel_turn(self) -> None:
        if self._pending_user and self._messages:
            self._messages.pop()
        self._pending_user = False
        self._pending_history_content = None

    def clear(self) -> None:
        self._messages.clear()
        self._pending_user = False
        self._pending_history_content = None
