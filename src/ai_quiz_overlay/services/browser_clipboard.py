"""Short-lived clipboard helper for browser mode."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import struct
import sys

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication


CF_DIB = 8
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0042

EXCLUDE_FORMAT = "ExcludeClipboardContentFromMonitorProcessing"
HISTORY_FORMAT = "CanIncludeInClipboardHistory"
CLOUD_FORMAT = "CanUploadToCloudClipboard"


class ClipboardError(RuntimeError):
    """Clipboard operation failed."""


def _register_format(user32, name: str) -> int:
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    result = int(user32.RegisterClipboardFormatW(name))
    if not result:
        raise ctypes.WinError()
    return result


def _alloc_handle(data: bytes):
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise ctypes.WinError()
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        kernel32.GlobalFree(handle)
        raise ctypes.WinError()
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)
    return handle


def _set_windows_clipboard(
    formats: tuple[tuple[int, bytes], ...],
) -> int:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    if not user32.OpenClipboard(None):
        raise ClipboardError("剪贴板正被其他程序占用。")
    handles = []
    try:
        if not user32.EmptyClipboard():
            raise ClipboardError("无法清空剪贴板。")
        for format_id, data in formats:
            handle = _alloc_handle(data)
            handles.append(handle)
            if not user32.SetClipboardData(format_id, handle):
                raise ClipboardError("无法写入剪贴板。")
            handles[-1] = None
    finally:
        for handle in handles:
            if handle:
                kernel32.GlobalFree(handle)
        user32.CloseClipboard()
    return int(user32.GetClipboardSequenceNumber())


def _image_dib(image: QImage) -> bytes:
    image = image.convertToFormat(QImage.Format.Format_RGB32)
    width = max(1, image.width())
    height = max(1, image.height())
    stride = width * 4
    pixels = bytes(image.constBits())
    header = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height,
        1,
        32,
        0,
        stride * height,
        0,
        0,
        0,
        0,
    )
    rows = []
    for y in range(height - 1, -1, -1):
        rows.append(pixels[y * stride:(y + 1) * stride])
    return header + b"".join(rows)


class BrowserClipboardGuard(QObject):
    """Set clipboard data with Windows history/cloud exclusions and auto-clear."""

    def __init__(
        self,
        *,
        auto_clear_enabled: bool = True,
        clear_seconds: int = 60,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._auto_clear_enabled = bool(auto_clear_enabled)
        self._clear_seconds = max(5, min(300, int(clear_seconds)))
        self._sequence = 0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.clear_if_unchanged)

    @property
    def sequence(self) -> int:
        return self._sequence

    def configure(
        self,
        *,
        auto_clear_enabled: bool,
        clear_seconds: int,
    ) -> None:
        self._auto_clear_enabled = bool(auto_clear_enabled)
        self._clear_seconds = max(5, min(300, int(clear_seconds)))

    def set_text(self, text: str) -> None:
        if sys.platform != "win32":
            QApplication.clipboard().setText(text)
            return
        payload = text.encode("utf-16-le") + b"\x00\x00"
        self._set_formats(
            (
                (CF_UNICODETEXT, payload),
                *self._exclusion_formats(),
            )
        )

    def set_image(self, image: QImage) -> None:
        if sys.platform != "win32":
            QApplication.clipboard().setImage(image)
            return
        self._set_formats(
            (
                (CF_DIB, _image_dib(image)),
                *self._exclusion_formats(),
            )
        )

    def _exclusion_formats(self) -> tuple[tuple[int, bytes], ...]:
        user32 = ctypes.windll.user32
        return (
            (_register_format(user32, EXCLUDE_FORMAT), struct.pack("<I", 1)),
            (_register_format(user32, HISTORY_FORMAT), struct.pack("<I", 0)),
            (_register_format(user32, CLOUD_FORMAT), struct.pack("<I", 0)),
        )

    def _set_formats(self, formats: tuple[tuple[int, bytes], ...]) -> None:
        self._sequence = _set_windows_clipboard(formats)
        if self._auto_clear_enabled:
            self._timer.start(self._clear_seconds * 1000)

    def clear_if_unchanged(self) -> bool:
        if self._sequence == 0:
            return False
        if sys.platform != "win32":
            return False
        current = int(ctypes.windll.user32.GetClipboardSequenceNumber())
        if current != self._sequence:
            self._sequence = 0
            return False
        user32 = ctypes.windll.user32
        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
        finally:
            user32.CloseClipboard()
        self._sequence = 0
        return True
