"""阶段 1 使用的纯文本模拟回答逻辑。"""

from __future__ import annotations


def build_simulated_answer(question: str) -> str:
    """生成一段能体现流式输出过程的模拟回答。"""
    clean_question = question.strip()
    short_question = clean_question
    if len(short_question) > 60:
        short_question = f"{short_question[:60]}..."

    return (
        "这是阶段 1 的模拟流式回答。\n\n"
        f"你输入的问题是：{short_question}\n\n"
        "当前程序还没有连接 DeepSeek API。这里的文字由后台工作线程分段发出，"
        "用来验证界面在接收内容时是否保持流畅。\n\n"
        "下一阶段会加入 Win32 全局快捷键和高层级置顶；之后再接入真实 API。"
    )


def split_text(text: str, chunk_size: int = 3) -> list[str]:
    """把文本切成固定长度的小段，模拟流式返回的数据块。"""
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")

    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]
