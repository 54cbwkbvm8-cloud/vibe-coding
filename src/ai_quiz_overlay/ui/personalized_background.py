"""Cached, DPI-aware glass compositor for personalized surfaces."""

from __future__ import annotations

from pathlib import Path
import time

from PySide6.QtCore import (
    QCoreApplication,
    QObject,
    QRect,
    QRectF,
    QThread,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QWidget,
)

from ..personalization_runtime import BrandRuntime
from .glass_renderer import draw_glass_window


def _source_image(path: Path | None) -> QImage | None:
    if path is None:
        return None
    image = QImage(str(path))
    return None if image.isNull() else image


def _blur_pixmap(pixmap: QPixmap, radius: float) -> QPixmap:
    if radius <= 0:
        return pixmap
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(pixmap)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius)
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    result = QPixmap(pixmap.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    scene.render(
        painter,
        QRectF(result.rect()),
        QRectF(pixmap.rect()),
    )
    painter.end()
    return result


def _compose_background(
    source: QImage,
    width: int,
    height: int,
    device_ratio: float,
    mode: str,
    blur: int,
    dim: int,
) -> QPixmap:
    physical_width = max(1, round(width * device_ratio))
    physical_height = max(1, round(height * device_ratio))
    target = QPixmap(physical_width, physical_height)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if mode == "cover":
        scaled = QPixmap.fromImage(source).scaled(
            physical_width,
            physical_height,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (physical_width - scaled.width()) // 2
        y = (physical_height - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
    elif mode == "contain":
        scaled = QPixmap.fromImage(source).scaled(
            physical_width,
            physical_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (physical_width - scaled.width()) // 2
        y = (physical_height - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
    else:
        source_pixmap = QPixmap.fromImage(source)
        x = (physical_width - source_pixmap.width()) // 2
        y = (physical_height - source_pixmap.height()) // 2
        painter.drawPixmap(x, y, source_pixmap)
    painter.end()
    blurred = _blur_pixmap(target, blur * device_ratio)
    painter = QPainter(blurred)
    alpha = round(max(0, min(80, int(dim))) / 100 * 255)
    painter.fillRect(blurred.rect(), QColor(5, 8, 18, alpha))
    painter.end()
    blurred.setDevicePixelRatio(device_ratio)
    return blurred


class _SourceLoadWorker(QObject):
    loaded = Signal(int, object, int)
    completed = Signal()

    def __init__(self, generation: int, path: Path) -> None:
        super().__init__()
        self._generation = generation
        self._path = path

    @Slot()
    def run(self) -> None:
        started = time.perf_counter()
        image = QImage(str(self._path))
        elapsed_microseconds = round(
            (time.perf_counter() - started) * 1_000_000
        )
        self.loaded.emit(self._generation, image, elapsed_microseconds)
        self.completed.emit()


class GlassSurfaceRenderer(QObject):
    """Store only the final size/DPR composite, never the decoded source."""

    changed = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._runtime = None
        self._pixmap = QPixmap()
        self._key: tuple | None = None
        self._pending: tuple | None = None
        self.last_render_ms = 0.0
        self.last_decode_ms = 0.0
        self.last_background_ms = 0.0
        self._generation = 0
        self._load_thread: QThread | None = None
        self._load_worker: _SourceLoadWorker | None = None
        self._loading_generation = -1
        self._shutting_down = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._render_pending)
        parent.destroyed.connect(self.shutdown)
        application = QCoreApplication.instance()
        if application is not None:
            application.aboutToQuit.connect(self.shutdown)

    @property
    def cached_pixmap(self) -> QPixmap:
        return self._pixmap

    @property
    def retained_source(self) -> QImage | None:
        return None

    def configure(self, runtime: BrandRuntime) -> None:
        if self._shutting_down:
            return
        previous = self._runtime
        self._runtime = runtime
        if previous is None or (
            previous.background_path,
            previous.background_mode,
            previous.background_blur,
            previous.background_dim,
        ) != (
            runtime.background_path,
            runtime.background_mode,
            runtime.background_blur,
            runtime.background_dim,
        ):
            self._pixmap = QPixmap()
            self._key = None
            self._pending = None
            self._timer.stop()
            self._generation += 1
            self.changed.emit()

    def pixmap_for(
        self,
        width: int,
        height: int,
        device_ratio: float,
        *,
        opacity: float,
        active: bool,
        acrylic_active: bool = False,
    ) -> QPixmap:
        if self._shutting_down or self._runtime is None:
            return QPixmap()
        key = (
            max(1, int(width)),
            max(1, int(height)),
            round(device_ratio, 2),
            round(opacity, 4),
            bool(active),
            bool(acrylic_active),
            str(self._runtime.background_path or ""),
            self._runtime.background_mode,
            self._runtime.background_blur,
            self._runtime.background_dim,
        )
        if key == self._key:
            return self._pixmap
        if key != self._pending:
            self._generation += 1
        self._pending = key
        if not self._pixmap.isNull():
            self._timer.start()
            quick = self._pixmap.scaled(
                max(1, round(width * device_ratio)),
                max(1, round(height * device_ratio)),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            quick.setDevicePixelRatio(device_ratio)
            return quick
        self._render_sync(key)
        return self._pixmap

    def shutdown(self) -> None:
        """Stop the decoder and release its thread before the parent dies."""
        if self._shutting_down:
            return
        self._shutting_down = True
        self._timer.stop()
        self._generation += 1
        self._pending = None
        thread = self._active_load_thread()
        if thread is None:
            return
        try:
            thread.quit()
            if thread.isRunning():
                thread.wait()
        except RuntimeError:
            pass
        self._load_thread = None
        self._load_worker = None

    def _active_load_thread(self) -> QThread | None:
        thread = self._load_thread
        if thread is None:
            return None
        try:
            thread.isRunning()
        except RuntimeError:
            self._load_thread = None
            self._load_worker = None
            return None
        return thread

    def _render_pending(self) -> None:
        if self._pending is None:
            return
        key = self._pending
        background_text = key[6]
        if background_text:
            self._start_source_load(key)
        else:
            self._render_key(key, None)
            self.changed.emit()

    def _start_source_load(self, key: tuple) -> None:
        if (
            self._shutting_down
            or self._active_load_thread() is not None
        ):
            return
        generation = self._generation
        self._loading_generation = generation
        path = Path(key[6])
        self._load_thread = QThread(self)
        self._load_worker = _SourceLoadWorker(generation, path)
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.loaded.connect(self._source_loaded)
        self._load_worker.completed.connect(self._load_thread.quit)
        self._load_worker.completed.connect(
            self._load_worker.deleteLater
        )
        self._load_thread.finished.connect(
            self._load_thread_finished
        )
        self._load_thread.start()

    @Slot(int, object, int)
    def _source_loaded(
        self,
        generation: int,
        image: QImage,
        elapsed_microseconds: int,
    ) -> None:
        self.last_decode_ms = elapsed_microseconds / 1000
        if generation != self._generation or self._pending is None:
            return
        key = self._pending
        if image.isNull():
            self._render_key(key, None)
        else:
            self._render_key(key, image)
        self.changed.emit()

    @Slot()
    def _load_thread_finished(self) -> None:
        thread = self._load_thread
        self._load_thread = None
        self._load_worker = None
        if thread is not None:
            thread.deleteLater()
        if (
            not self._shutting_down
            and self._pending is not None
            and self._pending != self._key
        ):
            self._render_pending()

    def _render_sync(self, key: tuple) -> None:
        decode_started = time.perf_counter()
        background_text = key[6]
        source = _source_image(
            Path(background_text) if background_text else None
        )
        self.last_decode_ms = (
            time.perf_counter() - decode_started
        ) * 1000
        self._render_key(key, source)

    def _render_key(
        self,
        key: tuple,
        source: QImage | None,
    ) -> None:
        started = time.perf_counter()
        (
            width,
            height,
            ratio,
            opacity,
            active,
            acrylic_active,
            background_text,
            mode,
            blur,
            dim,
        ) = key
        background_started = time.perf_counter()
        background = (
            _compose_background(
                source,
                width,
                height,
                ratio,
                mode,
                blur,
                dim,
            )
            if source is not None
            else None
        )
        self.last_background_ms = (
            time.perf_counter() - background_started
        ) * 1000
        pixmap = QPixmap(
            max(1, round(width * ratio)),
            max(1, round(height * ratio)),
        )
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        draw_glass_window(
            painter,
            QRect(0, 0, width, height),
            opacity=opacity,
            acrylic_active=acrylic_active,
            active=active,
            background_pixmap=background,
        )
        painter.end()
        self._pixmap = pixmap
        self._key = key
        self._pending = None
        self.last_render_ms = (
            time.perf_counter() - started
        ) * 1000
