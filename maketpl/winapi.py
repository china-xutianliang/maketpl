"""Win32 薄封装（只用 ctypes，副机上的 game_share 也要用，所以不依赖第三方库）。"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Callable

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

HWND = wintypes.HWND

try:
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    dwmapi.DwmGetWindowAttribute.argtypes = [HWND, wintypes.DWORD,
                                           ctypes.c_void_p, wintypes.DWORD]
    dwmapi.DwmGetWindowAttribute.restype = wintypes.LONG
except OSError:
    dwmapi = None

DWMWA_CLOAKED = 14


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("ptMinPosition", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("rcNormalPosition", wintypes.RECT),
    ]


user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
user32.EnumChildWindows.argtypes = [HWND, ctypes.c_void_p, wintypes.LPARAM]
user32.GetClassNameW.argtypes = [HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [HWND]
user32.GetWindowThreadProcessId.argtypes = [HWND, ctypes.POINTER(wintypes.DWORD)]
user32.FindWindowExW.argtypes = [HWND, HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = HWND
user32.GetWindowRect.argtypes = [HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.argtypes = [HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [HWND, ctypes.POINTER(wintypes.POINT)]
user32.IsIconic.argtypes = [HWND]
user32.IsZoomed.argtypes = [HWND]
user32.GetWindowPlacement.argtypes = [HWND, ctypes.POINTER(WINDOWPLACEMENT)]
user32.SetWindowPlacement.argtypes = [HWND, ctypes.POINTER(WINDOWPLACEMENT)]
user32.IsWindow.argtypes = [HWND]
user32.IsWindowVisible.argtypes = [HWND]
user32.ShowWindow.argtypes = [HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SendMessageW.argtypes = [HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.GetParent.argtypes = [HWND]
user32.GetParent.restype = HWND
user32.GetForegroundWindow.restype = HWND
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = HWND
user32.GetWindowDisplayAffinity.argtypes = [HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowLongW.argtypes = [HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

SW_SHOWNOACTIVATE = 4
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 0x1, 0x2, 0x4, 0x10
SW_HIDE = 0
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
WDA_EXCLUDEFROMCAPTURE = 0x11   # 截图时被系统跳过的窗口（不算遮挡）
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x80, 0x40000
WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x80000, 0x20
BM_CLICK = 0x00F5
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, wintypes.LPARAM)


def hide_from_taskbar(h: int) -> bool:
    """改成工具窗口样式，任务栏不再显示它的图标；窗口本身照常存在、照常能截图。

    样式要在窗口隐藏状态下改，再重新显示，任务栏才会刷新。已经是工具窗口则什么都不做。
    """
    ex = user32.GetWindowLongW(h, GWL_EXSTYLE)
    if ex & WS_EX_TOOLWINDOW and not ex & WS_EX_APPWINDOW:
        return False
    was_visible = bool(user32.IsWindowVisible(h))
    if was_visible:
        user32.ShowWindow(h, SW_HIDE)
    user32.SetWindowLongW(h, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
    if was_visible:
        user32.ShowWindow(h, SW_SHOWNOACTIVATE)
    return True


def set_dpi_aware() -> None:
    """Per-Monitor V2。必须在创建任何窗口、读取任何窗口尺寸之前调用。"""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except OSError:
        pass


def window_dpi(h: int) -> int:
    """窗口自己的 DPI（96 = 100%）；取不到按 96。"""
    try:
        user32.GetDpiForWindow.argtypes = [HWND]
        user32.GetDpiForWindow.restype = wintypes.UINT
        return int(user32.GetDpiForWindow(h)) or 96
    except (OSError, AttributeError):
        return 96


def monitor_dpi(h: int) -> int:
    """窗口所在显示器的有效 DPI（96 = 100%）；取不到按 96。"""
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        user32.MonitorFromWindow.argtypes = [HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        shcore.GetDpiForMonitor.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                            ctypes.POINTER(wintypes.UINT),
                                            ctypes.POINTER(wintypes.UINT)]
        hmon = user32.MonitorFromWindow(h, 2)   # MONITOR_DEFAULTTONEAREST
        x, y = wintypes.UINT(0), wintypes.UINT(0)
        if shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(x), ctypes.byref(y)) != 0:
            return 96
        return int(x.value) or 96
    except (OSError, AttributeError):
        return 96


def is_admin() -> bool:
    try:
        return bool(shell32.IsUserAnAdmin())
    except OSError:
        return False


def enum_top_windows() -> list[int]:
    out: list[int] = []

    def cb(h, _l):
        out.append(h or 0)
        return True

    user32.EnumWindows(_WNDENUMPROC(cb), 0)
    return out


def enum_children(parent: int) -> list[int]:
    out: list[int] = []

    def cb(h, _l):
        out.append(h or 0)
        return True

    user32.EnumChildWindows(parent, _WNDENUMPROC(cb), 0)
    return out


def class_name(h: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, buf, 256)
    return buf.value


def title(h: int) -> str:
    n = user32.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(max(n + 1, 2))
    user32.GetWindowTextW(h, buf, n + 1)
    return buf.value


def pid_of(h: int) -> int:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


def image_path(pid: int) -> str:
    hp = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not hp:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(hp)


kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
INVALID_HANDLE = ctypes.c_void_p(-1).value


class _ProcEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


def process_paths(exe_name: str) -> list[str]:
    """按进程名（不区分大小写）找正在运行的进程，返回它们的完整路径（读不到路径的跳过）。"""
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == INVALID_HANDLE:
        return []
    out: list[str] = []
    try:
        pe = _ProcEntry()
        pe.dwSize = ctypes.sizeof(_ProcEntry)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            if pe.szExeFile.lower() == exe_name.lower():
                p = image_path(pe.th32ProcessID)
                if p and p not in out:
                    out.append(p)
            ok = kernel32.Process32NextW(snap, ctypes.byref(pe))
    finally:
        kernel32.CloseHandle(snap)
    return out


def find_child(parent: int, cls: str | None = None, text: str | None = None) -> int:
    return user32.FindWindowExW(parent, None, cls, text) or 0


def parent_of(h: int) -> int:
    return user32.GetParent(h) or 0


def is_window(h: int) -> bool:
    return bool(user32.IsWindow(h))


def is_visible(h: int) -> bool:
    return bool(user32.IsWindowVisible(h))


def is_iconic(h: int) -> bool:
    return bool(user32.IsIconic(h))


def is_cloaked(h: int) -> bool:
    """窗口被系统"披风"藏起来了：常见于另一个虚拟桌面或后台 UWP。"""
    if dwmapi is None:
        return False
    val = wintypes.DWORD(0)
    if dwmapi.DwmGetWindowAttribute(HWND(h), DWMWA_CLOAKED,
                                    ctypes.byref(val), ctypes.sizeof(val)) != 0:
        return False
    return val.value != 0


def display_affinity(h: int) -> int:
    """SetWindowDisplayAffinity 的值；0x11 = 截图时被系统跳过（BitBlt 直接看穿它）。"""
    v = wintypes.DWORD(0)
    if user32.GetWindowDisplayAffinity(h, ctypes.byref(v)):
        return v.value
    return 0


def virtual_screen() -> tuple[int, int, int, int]:
    """所有显示器合起来的虚拟屏幕矩形，可能有负坐标。"""
    x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return x, y, x + w, y + h


_cover_cache: dict = {}


def covered_ratio(h: int, client_rect: tuple[int, int, int, int] | None = None) -> float:
    """客户区（或其中一块 client_rect）被更高层窗口盖住的面积比例（矩形并集估算）。

    BitBlt 截的是屏幕，目标被别的窗口盖住时，截到的其实是盖它的那个窗口。
    """
    try:
        cw, ch = client_size(h)
        if cw <= 0 or ch <= 0:
            return 0.0
        ox, oy = client_origin_on_screen(h)
        if client_rect is None:
            rx1, ry1, rx2, ry2 = 0, 0, cw, ch
        else:
            rx1, ry1 = max(0, client_rect[0]), max(0, client_rect[1])
            rx2, ry2 = min(cw, client_rect[2]), min(ch, client_rect[3])
            if rx2 <= rx1 or ry2 <= ry1:
                return 0.0
        tx1, ty1, tx2, ty2 = ox + rx1, oy + ry1, ox + rx2, oy + ry2
        top = h
        p = parent_of(top)
        while p:
            top = p
            p = parent_of(top)
        # 枚举上层窗口+各自的矩形/属性每帧要几百个 API 调用，
        # 遮挡只是给个提醒，缓存 0.8s 完全够新
        ent = _cover_cache.get(top)
        now = time.monotonic()
        if ent is not None and ent[0] > now:
            above = ent[1]
        else:
            above = []
            for w in enum_top_windows():
                if w == top:
                    break   # EnumWindows 按 Z 序给，排在自己前面的才是盖它的
                if not is_visible(w) or is_iconic(w) or is_cloaked(w) \
                        or display_affinity(w) == WDA_EXCLUDEFROMCAPTURE:
                    continue
                above.append(window_rect(w))
            _cover_cache.clear()
            _cover_cache[top] = (now + 0.8, above)
        rects = []
        for l, t, r, b in above:
            ix1, iy1 = max(l, tx1), max(t, ty1)
            ix2, iy2 = min(r, tx2), min(b, ty2)
            if ix2 > ix1 and iy2 > iy1:
                rects.append((ix1, iy1, ix2, iy2))
        if not rects:
            return 0.0
        xs = sorted({r[0] for r in rects} | {r[2] for r in rects})
        area = 0
        for x1, x2 in zip(xs, xs[1:]):
            seg = None
            for a, b in sorted((r[1], r[3]) for r in rects
                               if r[0] <= x1 and r[2] >= x2):
                if seg is None:
                    seg = [a, b]
                elif a <= seg[1]:
                    seg[1] = max(seg[1], b)
                else:
                    area += (x2 - x1) * (seg[1] - seg[0])
                    seg = [a, b]
            if seg is not None:
                area += (x2 - x1) * (seg[1] - seg[0])
        return min(1.0, area / ((rx2 - rx1) * (ry2 - ry1)))
    except Exception:
        return 0.0


def is_zoomed(h: int) -> bool:
    return bool(user32.IsZoomed(h))


def restore_noactivate(h: int) -> bool:
    """把最大化窗口还原成普通窗口，尽量不激活、不抢前台。"""
    wp = WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(WINDOWPLACEMENT)
    if not user32.GetWindowPlacement(h, ctypes.byref(wp)):
        return False
    wp.showCmd = SW_SHOWNOACTIVATE
    return bool(user32.SetWindowPlacement(h, ctypes.byref(wp)))


def show_noactivate(h: int) -> None:
    user32.ShowWindow(h, SW_SHOWNOACTIVATE)


def window_rect(h: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def client_size(h: int) -> tuple[int, int]:
    r = wintypes.RECT()
    user32.GetClientRect(h, ctypes.byref(r))
    return r.right - r.left, r.bottom - r.top


def client_origin_on_screen(h: int) -> tuple[int, int]:
    p = wintypes.POINT(0, 0)
    user32.ClientToScreen(h, ctypes.byref(p))
    return p.x, p.y


def set_window_size(h: int, w: int, hgt: int, x: int | None = None, y: int | None = None) -> bool:
    """调整大小（可选移动），不激活、不改 Z 序。"""
    flags = SWP_NOZORDER | SWP_NOACTIVATE
    if x is None or y is None:
        flags |= SWP_NOMOVE
        x = y = 0
    return bool(user32.SetWindowPos(h, None, x, y, w, hgt, flags))


def foreground() -> int:
    return user32.GetForegroundWindow() or 0


def cursor_pos() -> tuple[int, int]:
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def window_from_point(x: int, y: int) -> int:
    """光标下面最里层的 hwnd。"""
    return user32.WindowFromPoint(wintypes.POINT(x, y)) or 0


def make_click_through(h: int) -> None:
    """让窗口对鼠标穿透：WindowFromPoint 会跳过它（给高亮框用）。"""
    ex = user32.GetWindowLongW(h, GWL_EXSTYLE)
    user32.SetWindowLongW(h, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT)


def click_button(h: int) -> None:
    user32.SendMessageW(h, BM_CLICK, 0, 0)


def find_top_windows(pred: Callable[[int], bool]) -> list[int]:
    return [h for h in enum_top_windows() if pred(h)]
