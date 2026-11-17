"""按窗口句柄截图（ctypes + numpy，无 Win32 以外的系统依赖，副机也能用）。

只用 BitBlt / PrintWindow 读窗口自己的像素，不注入、不挂钩。
窗口在屏幕上时先试 BitBlt（读屏幕上该窗口的区域，就是用户看到的实时画面，
但窗口被遮挡时会带上遮挡物）；PrintWindow 对 DirectX/GPU 渲染的窗口常常给纯黑
或一张过期的离屏缓存帧，只在 BitBlt 不可信时退回它并在 note 里标明可能滞后。
最小化/别的虚拟桌面/屏幕外的窗口先直接报原因；BitBlt 截到但被挡住太多时标 covered。
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

import numpy as np

from . import winapi

user32 = winapi.user32
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
VP = ctypes.c_void_p

user32.GetDC.argtypes = [VP]
user32.GetDC.restype = VP
user32.ReleaseDC.argtypes = [VP, VP]
user32.PrintWindow.argtypes = [VP, VP, wintypes.UINT]
gdi32.CreateCompatibleDC.argtypes = [VP]
gdi32.CreateCompatibleDC.restype = VP
gdi32.CreateCompatibleBitmap.argtypes = [VP, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = VP
gdi32.SelectObject.argtypes = [VP, VP]
gdi32.SelectObject.restype = VP
gdi32.DeleteObject.argtypes = [VP]
gdi32.DeleteDC.argtypes = [VP]
gdi32.BitBlt.argtypes = [VP, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, VP,
                         ctypes.c_int, ctypes.c_int, wintypes.DWORD]
gdi32.GetDIBits.argtypes = [VP, VP, wintypes.UINT, wintypes.UINT, VP, VP, wintypes.UINT]
gdi32.StretchBlt.argtypes = [VP, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, VP,
                             ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
gdi32.SetStretchBltMode.argtypes = [VP, ctypes.c_int]
gdi32.SetBrushOrgEx.argtypes = [VP, ctypes.c_int, ctypes.c_int, VP]

SRCCOPY = 0x00CC0020
HALFTONE = 4
PW_CLIENTONLY = 0x1
PW_RENDERFULLCONTENT = 0x2
MAX_PIXELS = 12_000_000  # 防止误选超大窗口把内存吃光


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


def bgra_to_rgb(bgra, w: int, h: int) -> np.ndarray:
    """BGRA→RGB 去 alpha。ctypes 逐元素切片大窗口要 20ms+，numpy 大步长 ~2ms。"""
    a = np.frombuffer(bgra, np.uint8)[: w * h * 4]
    out = np.empty(w * h * 3, np.uint8)
    out[0::3] = a[2::4]
    out[1::3] = a[1::4]
    out[2::3] = a[0::4]
    return out


def is_blank(rgb, step_px: int = 211) -> bool:
    """抽样判断是不是纯色图（全黑/全白等）。向量化后跑全图也就一两毫秒。"""
    a = np.frombuffer(rgb, np.uint8).reshape(-1, 3)
    if len(a) == 0:
        return True
    return bool((a[step_px::step_px] == a[0]).all())


def to_ppm(rgb: bytes, w: int, h: int) -> bytes:
    """Tk 的 PhotoImage 能直接读 PPM(P6) 数据，不需要 Pillow。"""
    return b"P6 %d %d 255\n" % (w, h) + bytes(rgb)


_grab_lock = threading.Lock()
_grab_cache: dict = {"wh": None, "mem": None, "bmp": None}


def _drop_grab_cache() -> None:
    if _grab_cache["bmp"]:
        gdi32.DeleteObject(_grab_cache["bmp"])
    if _grab_cache["mem"]:
        gdi32.DeleteDC(_grab_cache["mem"])
    _grab_cache.update(wh=None, mem=None, bmp=None)


def _grab(hwnd: int, w: int, h: int, how: str, x: int = 0, y: int = 0):
    """抓客户区 (x,y) 起 w×h 一块；PrintWindow 不支持偏移，只整窗用。

    每帧新建 DC/位图太贵（大窗口位图十几 MB），缓存复用一套；返回 ctypes 缓冲，
    调用方直接切片，不再整份拷贝。锁着用，多线程抓图互不踩。
    """
    with _grab_lock:
        src = user32.GetDC(hwnd)
        if not src:
            return None
        try:
            if _grab_cache["wh"] == (w, h) and _grab_cache["mem"]:
                mem, bmp = _grab_cache["mem"], _grab_cache["bmp"]
            else:
                _drop_grab_cache()
                mem = gdi32.CreateCompatibleDC(src)
                bmp = gdi32.CreateCompatibleBitmap(src, w, h) if mem else None
                if mem and bmp:
                    _grab_cache.update(wh=(w, h), mem=mem, bmp=bmp)
            if not mem or not bmp:
                return None
            old = gdi32.SelectObject(mem, bmp)
            if how == "PrintWindow":
                ok = bool(user32.PrintWindow(hwnd, mem,
                                             PW_CLIENTONLY | PW_RENDERFULLCONTENT))
            else:
                ok = bool(gdi32.BitBlt(mem, 0, 0, w, h, src, x, y, SRCCOPY))
            gdi32.SelectObject(mem, old)
            if not ok:
                return None
            hdr = BITMAPINFOHEADER()
            hdr.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            hdr.biWidth, hdr.biHeight = w, -h  # 负数 = 自上而下
            hdr.biPlanes, hdr.biBitCount = 1, 32
            buf = ctypes.create_string_buffer(w * h * 4)
            if gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(hdr), 0) != h:
                return None
            return buf
        finally:
            user32.ReleaseDC(hwnd, src)


def why_invisible(hwnd: int) -> str | None:
    """窗口不在可见屏幕上的直接原因；正常显示返回 None。"""
    if not winapi.is_window(hwnd):
        return "窗口已经不存在（可能刚被关掉）"
    if winapi.is_iconic(hwnd):
        return "窗口最小化了，还原后再截"
    if not winapi.is_visible(hwnd):
        return "窗口被隐藏了"
    if winapi.is_cloaked(hwnd):
        return "窗口在另一个虚拟桌面上，切回来再截"
    l, t, r, b = winapi.window_rect(hwnd)
    vx1, vy1, vx2, vy2 = winapi.virtual_screen()
    if r <= vx1 or b <= vy1 or l >= vx2 or t >= vy2:
        return "窗口在屏幕外面（显示器关了或被拖出屏幕）"
    return None


def _crop_bgra(bgra: bytes, src_w: int, x: int, y: int, w: int, h: int) -> bytes:
    """从整图 BGRA 里裁出 (x,y) 起 w×h 一块。"""
    stride = src_w * 4
    off = y * stride + x * 4
    row = w * 4
    return b"".join(bgra[off + i * stride: off + i * stride + row]
                    for i in range(h))


def _res(method: str, w: int, h: int, rgb: bytes, blank: bool,
         covered: bool = False, note: list[str] | None = None) -> dict:
    return {"ok": True, "w": w, "h": h, "rgb": rgb, "method": method,
            "blank": blank, "covered": covered, "note": "；".join(note or [])}


def capture_rgb(hwnd: int, rect: tuple[int, int, int, int] | None = None,
                prefer: str = "bitblt") -> dict:
    """截取窗口客户区；rect=(x1,y1,x2,y2) 给定时只截客户区里那一块（监控选区用）。

    返回 dict：ok, w, h, rgb, method, blank, covered, note。
    窗口在屏幕上时先试 BitBlt：拿到的是屏幕上的真实画面，动画/滚动都跟着变。
    PrintWindow 对 GPU 渲染的窗口可能只给一张过期的离屏缓存帧（看着像真的但不变），
    所以只在 BitBlt 不可信（纯色/被挡住）时才退回 PrintWindow，并在 note 里注明可能滞后。
    prefer="printwindow" 时反过来先试 PrintWindow：窗口被别的窗口盖住也能拿到它
    自己的画面（测试匹配用，免得遮挡物混进图里）。拿不到再退回 BitBlt。
    """
    why = why_invisible(hwnd)
    if why:
        return {"ok": False, "w": 0, "h": 0, "note": why}
    cw, ch = winapi.client_size(hwnd)
    if cw <= 0 or ch <= 0:
        return {"ok": False, "w": cw, "h": ch, "note": f"客户区是 {cw}x{ch}，没有画面可截"}
    x1 = y1 = 0
    x2, y2 = cw, ch
    if rect is not None:
        x1, y1 = max(0, int(rect[0])), max(0, int(rect[1]))
        x2, y2 = min(cw, int(rect[2])), min(ch, int(rect[3]))
        if x2 <= x1 or y2 <= y1:
            return {"ok": False, "w": 0, "h": 0, "note": "选区跑出窗口客户区了"}
    w, h = x2 - x1, y2 - y1
    if w * h > MAX_PIXELS:
        return {"ok": False, "w": w, "h": h, "note": f"截图区域 {w}x{h} 太大，不截图"}
    notes = []
    bb_rgb = bb_blank = None

    if prefer == "printwindow":
        raw = _grab(hwnd, cw, ch, "PrintWindow")
        if raw is not None:
            rgb = bgra_to_rgb(_crop_bgra(raw, cw, x1, y1, w, h), w, h)
            if not is_blank(rgb):
                notes.append("窗体自身画面（被挡住也能取到，GPU 窗口可能是旧帧）")
                return _res("PrintWindow", w, h, rgb, blank=False, note=notes)
            notes.append("PrintWindow 是纯色")
        else:
            notes.append("PrintWindow 失败")

    raw = _grab(hwnd, w, h, "BitBlt", x1, y1)
    if raw is not None:
        bb_rgb = bgra_to_rgb(raw, w, h)
        bb_blank = is_blank(bb_rgb)
        if not bb_blank:
            cov = winapi.covered_ratio(hwnd, (x1, y1, x2, y2))
            if cov >= 0.3:
                notes.append(f"画面约 {cov * 100:.0f}% 被挡住，BitBlt 截的是屏幕，"
                             "画面里可能混着上层窗口的内容")
            return _res("BitBlt", w, h, bb_rgb, blank=False,
                        covered=cov >= 0.3, note=notes)
        notes.append("BitBlt 截到纯色，试 PrintWindow")
    else:
        notes.append("BitBlt 失败")

    raw = _grab(hwnd, cw, ch, "PrintWindow")
    if raw is not None:
        rgb = bgra_to_rgb(_crop_bgra(raw, cw, x1, y1, w, h), w, h)
        if not is_blank(rgb):
            notes.append("用了窗体离屏画面（GPU 窗口可能只是旧帧，画面会滞后）")
            return _res("PrintWindow", w, h, rgb, blank=False, note=notes)
        notes.append("PrintWindow 也是纯色")
    else:
        notes.append("PrintWindow 失败")

    if bb_rgb is not None:
        return _res("BitBlt", w, h, bb_rgb, blank=True, note=notes)
    return {"ok": False, "w": w, "h": h, "note": "；".join(notes) or "截图失败"}


def capture_scaled(hwnd: int, out_w: int, out_h: int) -> dict:
    """截取窗口客户区并直接在 GDI 里缩放到 out_w x out_h（缩略图用，比先截全图再缩快得多）。

    只用 PrintWindow，窗口被遮挡或在屏幕外也能取到。返回 dict：ok, w, h, rgb, blank, src_w, src_h, note。
    """
    why = why_invisible(hwnd)
    if why:
        return {"ok": False, "note": why}
    sw, sh = winapi.client_size(hwnd)
    if sw <= 0 or sh <= 0:
        return {"ok": False, "note": f"客户区是 {sw}x{sh}（窗口最小化或隐藏）"}
    if sw * sh > MAX_PIXELS or out_w <= 0 or out_h <= 0 or out_w * out_h > MAX_PIXELS:
        return {"ok": False, "note": "尺寸不合理"}
    src = user32.GetDC(hwnd)
    if not src:
        return {"ok": False, "note": "GetDC 失败"}
    mem = mem2 = bmp = bmp2 = None
    try:
        mem = gdi32.CreateCompatibleDC(src)
        bmp = gdi32.CreateCompatibleBitmap(src, sw, sh)
        if not mem or not bmp:
            return {"ok": False, "note": "创建位图失败"}
        old = gdi32.SelectObject(mem, bmp)
        ok = bool(user32.PrintWindow(hwnd, mem, PW_CLIENTONLY | PW_RENDERFULLCONTENT))
        if not ok:
            gdi32.SelectObject(mem, old)
            return {"ok": False, "note": "PrintWindow 失败"}
        if (out_w, out_h) == (sw, sh):
            final_bmp, final_dc, old_final = bmp, mem, old
        else:
            mem2 = gdi32.CreateCompatibleDC(src)
            bmp2 = gdi32.CreateCompatibleBitmap(src, out_w, out_h)
            if not mem2 or not bmp2:
                gdi32.SelectObject(mem, old)
                return {"ok": False, "note": "创建缩略位图失败"}
            old2 = gdi32.SelectObject(mem2, bmp2)
            gdi32.SetStretchBltMode(mem2, HALFTONE)
            gdi32.SetBrushOrgEx(mem2, 0, 0, None)
            gdi32.StretchBlt(mem2, 0, 0, out_w, out_h, mem, 0, 0, sw, sh, SRCCOPY)
            gdi32.SelectObject(mem, old)
            final_bmp, final_dc, old_final = bmp2, mem2, old2
        gdi32.SelectObject(final_dc, old_final)  # GetDIBits 要求位图不在任何 DC 里
        hdr = BITMAPINFOHEADER()
        hdr.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        hdr.biWidth, hdr.biHeight = out_w, -out_h
        hdr.biPlanes, hdr.biBitCount = 1, 32
        buf = ctypes.create_string_buffer(out_w * out_h * 4)
        if gdi32.GetDIBits(final_dc, final_bmp, 0, out_h, buf, ctypes.byref(hdr), 0) != out_h:
            return {"ok": False, "note": "GetDIBits 失败"}
        rgb = bgra_to_rgb(buf, out_w, out_h)
        return {"ok": True, "w": out_w, "h": out_h, "rgb": rgb, "blank": is_blank(rgb),
                "src_w": sw, "src_h": sh, "note": ""}
    finally:
        for b in (bmp, bmp2):
            if b:
                gdi32.DeleteObject(b)
        for d in (mem, mem2):
            if d:
                gdi32.DeleteDC(d)
        user32.ReleaseDC(hwnd, src)