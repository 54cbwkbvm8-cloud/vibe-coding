"""轮转日志和统一异常日志入口。"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from .config import get_config_directory


LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3
LOGGER_NAME = "ai_quiz_overlay"


def get_log_directory() -> Path:
    return get_config_directory() / "logs"


def create_rotating_handler(
    log_file: Path,
    max_bytes: int = LOG_MAX_BYTES,
    backup_count: int = LOG_BACKUP_COUNT,
) -> RotatingFileHandler:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    return handler


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not any(
        isinstance(handler, RotatingFileHandler)
        for handler in logger.handlers
    ):
        try:
            logger.addHandler(
                create_rotating_handler(get_log_directory() / "app.log")
            )
        except OSError:
            logger.addHandler(logging.NullHandler())
    return logger


def log_event(
    event: str,
    status_code: int | None = None,
    error_type: str | None = None,
) -> None:
    """调用方无法通过该接口写入问题、回答、Key 或图片内容。"""
    get_logger().info(
        "event=%s status_code=%s error_type=%s",
        event,
        status_code if status_code is not None else "-",
        error_type or "-",
    )


def get_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        return configure_logging()
    return logger


def log_exception(exception: BaseException) -> None:
    """只记录异常类型和栈帧，不记录异常文本。"""
    _log_frames(type(exception).__name__, exception.__traceback__)


def _log_frames(error_type: str, traceback_object) -> None:
    logger = get_logger()
    frame = traceback_object
    if frame is None:
        logger.error(
            "event=unhandled_exception error_type=%s location=-",
            error_type,
        )
        return

    while frame is not None:
        code = frame.tb_frame.f_code
        logger.error(
            "event=unhandled_exception error_type=%s "
            "file=%s line=%s function=%s",
            error_type,
            Path(code.co_filename).name,
            frame.tb_lineno,
            code.co_name,
        )
        frame = frame.tb_next


def install_exception_hook() -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    def handle_exception(
        exception_type,
        exception,
        exception_traceback,
    ) -> None:
        _log_frames(exception_type.__name__, exception_traceback)
        app = QApplication.instance()
        if app is not None:
            from .personalization_runtime import current_brand_runtime

            dialog = QMessageBox()
            dialog.setIcon(QMessageBox.Icon.Critical)
            dialog.setTextFormat(Qt.TextFormat.PlainText)
            dialog.setWindowTitle(
                current_brand_runtime().dialog_title("程序错误")
            )
            dialog.setText(
                "程序发生未预期错误，已写入日志。请重新启动程序。"
            )
            dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
            dialog.exec()

    sys.excepthook = handle_exception
