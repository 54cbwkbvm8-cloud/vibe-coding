"""在独立线程中产生分段文本的模拟工作对象。"""

from __future__ import annotations

from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from .simulation_text import build_simulated_answer, split_text


class SimulatedStreamWorker(QObject):
    """模拟流式服务；后续真实 API 客户端可以沿用相同信号结构。"""

    chunk_ready = Signal(str)
    finished = Signal(bool)

    def __init__(self, question: str) -> None:
        super().__init__()
        self._question = question
        self._stop_event = Event()

    @Slot()
    def run(self) -> None:
        """在工作线程中运行，不阻塞 Qt 主线程。"""
        answer = build_simulated_answer(self._question)

        for chunk in split_text(answer):
            if self._stop_event.is_set():
                self.finished.emit(False)
                return

            self.chunk_ready.emit(chunk)

            if self._stop_event.wait(0.035):
                self.finished.emit(False)
                return

        self.finished.emit(True)

    def request_stop(self) -> None:
        """设置线程安全的中断标志，让 run() 在下一次检查时退出。"""
        self._stop_event.set()
