"""Direct IShellLink-based desktop shortcut creation without shell parsing."""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
from pathlib import Path
import re
import sys
import unicodedata
import uuid

from ..branding import SOFTWARE_NAME


CLSID_ShellLink = uuid.UUID("00021401-0000-0000-C000-000000000046")
IID_IShellLinkW = uuid.UUID("000214F9-0000-0000-C000-000000000046")
IID_IPersistFile = uuid.UUID("0000010B-0000-0000-C000-000000000046")
FOLDERID_Desktop = uuid.UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641")
OWNERSHIP_MARKER = "AIQuizOverlayManagedShortcut:v1"
CLSCTX_INPROC_SERVER = 0x1
COINIT_APARTMENTTHREADED = 0x2
HRESULT = ctypes.c_long
S_OK = 0
S_FALSE = 1
RPC_E_CHANGED_MODE = -2147417850
INVALID_SHORTCUT_CHARS = frozenset('<>:"/\\|?*')
RESERVED_WINDOWS_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}
SHCNE_ASSOCCHANGED = 0x08000000
SHCNF_IDLIST = 0x0000


class ShortcutError(RuntimeError):
    """A localized shortcut creation error."""


class GUID(ctypes.Structure):
    _fields_ = (
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    )

    @classmethod
    def from_uuid(cls, value: uuid.UUID) -> "GUID":
        raw = value.bytes_le
        return cls(
            int.from_bytes(raw[0:4], "little"),
            int.from_bytes(raw[4:6], "little"),
            int.from_bytes(raw[6:8], "little"),
            (ctypes.c_ubyte * 8)(*raw[8:16]),
        )


@dataclass(frozen=True)
class ShortcutInspection:
    exists: bool
    owned: bool
    filename: str


def sanitize_shortcut_filename(name: str, fallback: str = SOFTWARE_NAME) -> str:
    normalized = unicodedata.normalize("NFC", name or fallback)
    cleaned = "".join(
        character
        for character in normalized
        if unicodedata.category(character) not in {"Cc", "Cf"}
        and character not in INVALID_SHORTCUT_CHARS
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        cleaned = fallback
    if cleaned.casefold() in RESERVED_WINDOWS_NAMES:
        cleaned = f"_{cleaned}"
    cleaned = cleaned.rstrip(" .")[:72].rstrip(" .")
    return f"{cleaned or fallback}.lnk"


def notify_shell_association_changed() -> None:
    if sys.platform != "win32":
        return
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.SHChangeNotify(
            SHCNE_ASSOCCHANGED,
            SHCNF_IDLIST,
            None,
            None,
        )
    except OSError:
        pass


def _com_method(interface, index: int, *argument_types):
    vtable = ctypes.cast(
        interface,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
    ).contents
    prototype = ctypes.WINFUNCTYPE(
        HRESULT,
        ctypes.c_void_p,
        *argument_types,
    )
    return prototype(vtable[index])


def _release(interface) -> None:
    if interface:
        _com_method(interface, 2)(interface)


def _query_interface(interface, iid: uuid.UUID):
    result = ctypes.c_void_p()
    guid = GUID.from_uuid(iid)
    hr = _com_method(
        interface,
        0,
        ctypes.POINTER(GUID),
        ctypes.POINTER(ctypes.c_void_p),
    )(interface, ctypes.byref(guid), ctypes.byref(result))
    if hr != S_OK or not result.value:
        raise ShortcutError(f"无法获取快捷方式 COM 接口：0x{hr & 0xFFFFFFFF:08X}")
    return result


def _known_desktop_directory() -> Path:
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    path_pointer = ctypes.c_wchar_p()
    folder_id = GUID.from_uuid(FOLDERID_Desktop)
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(GUID),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    shell32.SHGetKnownFolderPath.restype = HRESULT
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    hr = shell32.SHGetKnownFolderPath(
        ctypes.byref(folder_id),
        0,
        None,
        ctypes.byref(path_pointer),
    )
    if hr != S_OK or not path_pointer.value:
        raise ShortcutError("无法获取系统桌面文件夹位置。")
    try:
        return Path(path_pointer.value)
    finally:
        ole32.CoTaskMemFree(
            ctypes.cast(path_pointer, ctypes.c_void_p)
        )


def _co_initialize(ole32) -> tuple[bool, int]:
    hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if hr in {S_OK, S_FALSE}:
        return True, hr
    if hr == RPC_E_CHANGED_MODE:
        return False, hr
    raise ShortcutError(f"无法初始化 Windows COM：0x{hr & 0xFFFFFFFF:08X}")


def _load_shell_link(path: Path):
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    initialized, init_result = _co_initialize(ole32)
    shell_link = ctypes.c_void_p()
    persist = None
    try:
        clsid = GUID.from_uuid(CLSID_ShellLink)
        iid = GUID.from_uuid(IID_IShellLinkW)
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid),
            None,
            CLSCTX_INPROC_SERVER,
            ctypes.byref(iid),
            ctypes.byref(shell_link),
        )
        if hr != S_OK:
            raise ShortcutError(
                f"无法创建快捷方式接口：0x{hr & 0xFFFFFFFF:08X}"
            )
        persist = _query_interface(shell_link, IID_IPersistFile)
        hr = _com_method(
            persist,
            5,
            wintypes.LPCWSTR,
            wintypes.BOOL,
        )(persist, str(path), False)
        if hr != S_OK:
            raise ShortcutError("无法读取已有快捷方式。")
        return shell_link, persist
    except Exception:
        if persist:
            _release(persist)
        if shell_link.value:
            _release(shell_link)
        if initialized:
            ole32.CoUninitialize()
        raise


def _get_description(interface) -> str:
    buffer = ctypes.create_unicode_buffer(1024)
    hr = _com_method(
        interface,
        6,
        wintypes.LPWSTR,
        ctypes.c_int,
    )(
        interface,
        buffer,
        len(buffer),
    )
    return buffer.value if hr == S_OK else ""


def _get_target(interface) -> str:
    buffer = ctypes.create_unicode_buffer(32768)
    find_data = wintypes.WIN32_FIND_DATAW()
    hr = _com_method(
        interface,
        3,
        wintypes.LPWSTR,
        ctypes.c_int,
        ctypes.POINTER(wintypes.WIN32_FIND_DATAW),
        wintypes.DWORD,
    )(
        interface,
        buffer,
        len(buffer),
        ctypes.byref(find_data),
        0,
    )
    return buffer.value if hr == S_OK else ""


def _get_working_directory(interface) -> str:
    buffer = ctypes.create_unicode_buffer(32768)
    hr = _com_method(
        interface,
        8,
        wintypes.LPWSTR,
        ctypes.c_int,
    )(interface, buffer, len(buffer))
    return buffer.value if hr == S_OK else ""


def _get_icon_location(interface) -> str:
    buffer = ctypes.create_unicode_buffer(32768)
    icon_index = ctypes.c_int()
    hr = _com_method(
        interface,
        16,
        wintypes.LPWSTR,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
    )(
        interface,
        buffer,
        len(buffer),
        ctypes.byref(icon_index),
    )
    return buffer.value if hr == S_OK else ""


def inspect_shortcut(path: Path) -> ShortcutInspection:
    if not path.is_file():
        return ShortcutInspection(False, False, path.name)
    shell_link = None
    persist = None
    try:
        shell_link, persist = _load_shell_link(path)
        description = _get_description(shell_link)
        return ShortcutInspection(
            True,
            description == OWNERSHIP_MARKER,
            path.name,
        )
    except ShortcutError:
        return ShortcutInspection(True, False, path.name)
    finally:
        if persist:
            _release(persist)
        if shell_link:
            _release(shell_link)


def shortcut_target(path: Path) -> str:
    shell_link = None
    persist = None
    try:
        shell_link, persist = _load_shell_link(path)
        return _get_target(shell_link)
    finally:
        if persist:
            _release(persist)
        if shell_link:
            _release(shell_link)


def shortcut_working_directory(path: Path) -> str:
    shell_link = None
    persist = None
    try:
        shell_link, persist = _load_shell_link(path)
        return _get_working_directory(shell_link)
    finally:
        if persist:
            _release(persist)
        if shell_link:
            _release(shell_link)


def shortcut_icon_location(path: Path) -> str:
    shell_link = None
    persist = None
    try:
        shell_link, persist = _load_shell_link(path)
        return _get_icon_location(shell_link)
    finally:
        if persist:
            _release(persist)
        if shell_link:
            _release(shell_link)


def _write_shortcut(
    path: Path,
    *,
    target: Path,
    working_directory: Path,
    icon_path: Path,
) -> None:
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    initialized, _init_result = _co_initialize(ole32)
    shell_link = ctypes.c_void_p()
    persist = None
    try:
        clsid = GUID.from_uuid(CLSID_ShellLink)
        iid = GUID.from_uuid(IID_IShellLinkW)
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid),
            None,
            CLSCTX_INPROC_SERVER,
            ctypes.byref(iid),
            ctypes.byref(shell_link),
        )
        if hr != S_OK:
            raise ShortcutError(
                f"无法创建快捷方式接口：0x{hr & 0xFFFFFFFF:08X}"
            )
        set_path = _com_method(
            shell_link,
            20,
            wintypes.LPCWSTR,
        )
        if set_path(shell_link, str(target)) != S_OK:
            raise ShortcutError("无法设置快捷方式目标。")
        set_working = _com_method(
            shell_link,
            9,
            wintypes.LPCWSTR,
        )
        if set_working(shell_link, str(working_directory)) != S_OK:
            raise ShortcutError("无法设置快捷方式起始位置。")
        set_description = _com_method(
            shell_link,
            7,
            wintypes.LPCWSTR,
        )
        if set_description(shell_link, OWNERSHIP_MARKER) != S_OK:
            raise ShortcutError("无法写入快捷方式所有权标记。")
        set_icon = _com_method(
            shell_link,
            17,
            wintypes.LPCWSTR,
            ctypes.c_int,
        )
        if set_icon(shell_link, str(icon_path), 0) != S_OK:
            raise ShortcutError("无法设置快捷方式图标。")

        persist = _query_interface(shell_link, IID_IPersistFile)
        path.parent.mkdir(parents=True, exist_ok=True)
        save = _com_method(
            persist,
            6,
            wintypes.LPCWSTR,
            wintypes.BOOL,
        )
        if save(persist, str(path), True) != S_OK:
            raise ShortcutError("无法保存快捷方式文件。")
    finally:
        if persist:
            _release(persist)
        if shell_link.value:
            _release(shell_link)
        if initialized:
            ole32.CoUninitialize()


def desktop_shortcut_path(software_name: str) -> Path:
    return _known_desktop_directory() / sanitize_shortcut_filename(
        software_name
    )


def create_desktop_shortcut(
    software_name: str,
    *,
    target: Path | None = None,
    icon_path: Path | None = None,
    overwrite_foreign: bool = False,
) -> Path:
    if sys.platform != "win32":
        raise ShortcutError("当前系统不支持 Windows 快捷方式。")
    shortcut = desktop_shortcut_path(software_name)
    inspection = inspect_shortcut(shortcut)
    if inspection.exists and not inspection.owned and not overwrite_foreign:
        raise ShortcutError(
            "桌面已有同名但不是本软件创建的快捷方式，未覆盖。"
        )
    executable = target or Path(sys.executable)
    icon = icon_path or executable
    _write_shortcut(
        shortcut,
        target=executable,
        working_directory=executable.parent,
        icon_path=icon,
    )
    if not inspect_shortcut(shortcut).owned:
        raise ShortcutError("快捷方式已保存，但所有权标记校验失败。")
    return shortcut


def delete_owned_desktop_shortcut(software_name: str) -> bool:
    shortcut = desktop_shortcut_path(software_name)
    inspection = inspect_shortcut(shortcut)
    if not inspection.exists:
        return False
    if not inspection.owned:
        raise ShortcutError("拒绝删除不是本软件创建的快捷方式。")
    shortcut.unlink()
    return True
