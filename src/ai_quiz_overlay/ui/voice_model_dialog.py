"""Glass download dialog for the fixed local speech-recognition model."""

from __future__ import annotations

from pathlib import Path
import threading

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..platform_support import IS_WINDOWS
from ..personalization_runtime import BrandRuntime, current_brand_runtime
from ..services.voice_models import (
    MODEL_SOURCE_BY_KEY,
    MODEL_SOURCES,
    ModelDownloadError,
    import_model_directory,
    install_model_from_source,
)
from ..theme import APP_STYLE
from ..win32.acrylic import apply_acrylic_material
from ..win32.topmost import TopmostError, apply_topmost
from ..win32.window_style import WindowStyleError, set_no_activate
from .glass_renderer import draw_glass_window
from .brand_assets import load_app_icon
from .personalized_background import GlassSurfaceRenderer
from .selection_options import SelectionGroup, SelectionOption


class ModelOperationWorker(QObject):
    progress = Signal(int, int)
    failed = Signal(str)
    finished = Signal(str)
    completed = Signal()

    def __init__(
        self,
        operation,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self._operation = operation
        self._cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        try:
            result = self._operation(
                progress=self.progress.emit,
                cancel_event=self._cancel_event,
            )
            self.finished.emit(str(result))
        except ModelDownloadError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"模型安装失败：{exc}")
        finally:
            self.completed.emit()


class VoiceModelDialog(QWidget):
    model_installed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._thread: QThread | None = None
        self._worker: ModelOperationWorker | None = None
        self._cancel_event: threading.Event | None = None
        self._cancel_requested = False
        self._brand_runtime = current_brand_runtime()
        self._glass_cache: QPixmap | None = None
        self._glass_cache_key: tuple | None = None
        self._background_renderer = GlassSurfaceRenderer(self)
        self._background_renderer.configure(self._brand_runtime)
        self._background_renderer.changed.connect(self.update)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet(APP_STYLE)
        self.resize(620, 430)
        self.setWindowTitle(
            self._brand_runtime.dialog_title(
                "安装本地语音识别模型"
            )
        )
        self.setWindowIcon(
            load_app_icon(str(self._brand_runtime.app_icon_path))
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(10)
        title = QLabel("安装本地语音识别模型")
        title.setObjectName("settingsGroupTitle")
        layout.addWidget(title)
        intro = QLabel(
            "模型下载只在点击“开始下载”后发起。失败时不会自动切换来源，"
            "请检查原因后手动选择另一个来源重试。"
        )
        intro.setObjectName("settingsHint")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        options = tuple(
            SelectionOption(
                key=source.key,
                label=source.label,
                enabled=True,
                subtitle="推荐" if source.recommended else "备用",
            )
            for source in MODEL_SOURCES
        )
        self.source_selection = SelectionGroup(options)
        self.source_selection.set_selected(MODEL_SOURCES[0].key)
        self.source_selection.changed.connect(self._source_changed)
        layout.addWidget(self.source_selection)
        self.source_detail = QLabel()
        self.source_detail.setObjectName("settingsHint")
        self.source_detail.setWordWrap(True)
        layout.addWidget(self.source_detail)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setFormat("等待开始")
        layout.addWidget(self.progress)
        self.status = QLabel("尚未发起任何网络请求。")
        self.status.setObjectName("settingsHint")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch()

        buttons = QHBoxLayout()
        self.close_button = QPushButton("关闭")
        self.close_button.setObjectName("secondaryButton")
        self.close_button.clicked.connect(self.close)
        self.start_button = QPushButton("开始下载")
        self.start_button.setObjectName("sendButton")
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_button.clicked.connect(self.start_download)
        buttons.addWidget(self.close_button)
        buttons.addStretch()
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)
        self._source_changed(MODEL_SOURCES[0].key)

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    @property
    def selected_source(self):
        return MODEL_SOURCE_BY_KEY[
            self.source_selection.selected_key() or MODEL_SOURCES[0].key
        ]

    def show_for(self, anchor: QWidget | None = None) -> None:
        if anchor is not None:
            parent_rect = anchor.frameGeometry()
            x = parent_rect.center().x() - self.width() // 2
            y = parent_rect.center().y() - self.height() // 2
            self.move(x, y)
        self.show()
        self.raise_()
        if IS_WINDOWS:
            try:
                set_no_activate(int(self.winId()), False)
                apply_acrylic_material(int(self.winId()), False)
                apply_topmost(int(self.winId()))
            except (WindowStyleError, TopmostError, OSError):
                pass
        self.activateWindow()

    def apply_brand(self, runtime: BrandRuntime) -> None:
        self._brand_runtime = runtime
        self.setWindowTitle(runtime.dialog_title("安装本地语音识别模型"))
        self.setWindowIcon(load_app_icon(str(runtime.app_icon_path)))
        self._background_renderer.configure(runtime)
        self._invalidate_glass_cache()
        self.update()

    @Slot()
    def start_download(self) -> None:
        source = self.selected_source
        self._run_operation(
            lambda progress, cancel_event: install_model_from_source(
                source,
                progress=progress,
                cancel_event=cancel_event,
            )
        )

    def import_folder(self, folder: Path) -> None:
        self.show_for()
        self._run_operation(
            lambda progress, cancel_event: import_model_directory(folder)
        )

    def _source_changed(self, key: str) -> None:
        source = MODEL_SOURCE_BY_KEY.get(key)
        if source is None:
            return
        domains = "、".join(source.domains)
        self.source_detail.setText(
            f"{source.description}\n允许的下载域名：{domains}"
        )

    def _run_operation(self, operation) -> None:
        if self.active:
            return
        self._cancel_requested = False
        self._cancel_event = threading.Event()
        self.source_selection.setEnabled(False)
        self.start_button.setEnabled(False)
        self.start_button.setText("正在安装…")
        self.close_button.setText("取消")
        self.progress.setValue(0)
        self.progress.setFormat("准备中…")
        self.status.setText("已开始。")
        self._thread = QThread(self)
        self._worker = ModelOperationWorker(
            operation,
            self._cancel_event,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._progress_changed)
        self._worker.failed.connect(self._operation_failed)
        self._worker.finished.connect(self._operation_finished)
        self._worker.completed.connect(self._thread.quit)
        self._worker.completed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        self._thread.start()

    @Slot(int, int)
    def _progress_changed(self, downloaded: int, total: int) -> None:
        if total > 0:
            self.progress.setValue(
                min(1000, round(downloaded / total * 1000))
            )
            self.progress.setFormat(
                f"{downloaded / (1024 * 1024):.1f} / "
                f"{total / (1024 * 1024):.1f} MiB"
            )
        else:
            self.progress.setFormat(
                f"已下载 {downloaded / (1024 * 1024):.1f} MiB"
            )

    @Slot(str)
    def _operation_failed(self, message: str) -> None:
        if self._cancel_requested:
            self.status.setText("已取消。下载文件已清理，可重新选择来源。")
            self.progress.setFormat("已取消")
        else:
            self.status.setText(f"失败：{message}")
            self.progress.setFormat("下载失败")

    @Slot(str)
    def _operation_finished(self, _result: str) -> None:
        self.status.setText("模型已安装并通过固定 SHA-256 校验。")
        self.progress.setValue(1000)
        self.progress.setFormat("安装完成")
        self.model_installed.emit()

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._cancel_event = None
        self.source_selection.setEnabled(True)
        self.start_button.setEnabled(True)
        self.start_button.setText("开始下载")
        self.close_button.setText("关闭")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.active and self._cancel_event is not None:
            self._cancel_requested = True
            self._cancel_event.set()
            self.status.setText("正在取消并清理临时文件…")
            event.ignore()
            return
        super().closeEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        self._glass_cache = self._background_renderer.pixmap_for(
            self.width(),
            self.height(),
            self.devicePixelRatioF(),
            opacity=0.92,
            active=self.isActiveWindow(),
        )
        if self._glass_cache is not None:
            painter.drawPixmap(0, 0, self._glass_cache)

    def _invalidate_glass_cache(self) -> None:
        self._glass_cache = None
        self._glass_cache_key = None
        self.update()
