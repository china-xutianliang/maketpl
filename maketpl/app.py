"""透明模板制作工具（独立程序，放副机上跑）：绑窗口 → 截图框选/取色 →
连拍求稳或油漆桶抠图 → 手修 → 存透明 PNG → 测试匹配。

用法：python -m maketpl.app
"""
from __future__ import annotations

import glob
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
import numpy as np
from PIL import Image, ImageTk
from PIL.PngImagePlugin import PngInfo

from . import colors, core, fidelity, findimg, winapi, wincap

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

CELL = 8
BUILD = "v2026.11.11.1"
MATCH_TOL = 24     # 和 mhxy nav.match.find_all 的默认容差一致
MATCH_SCORE = 10   # 和 mhxy nav.match.find_all 的默认分数上限一致
WAND_TOL = 24      # 魔术棒默认容差：游戏截图有噪点，8 点一下只能选到 1 个像素
UNDO_LIMIT = 20
BG = "#f4f4f2"           # 页面底色
CARD = "#ffffff"         # 卡片
CARD_HOV = "#f6f6f4"     # 悬停
BORDER = "#e7e7e4"       # 边框
CANVAS = "#efefec"       # 画布底色
HEAD = "#f7f7f5"         # 顶栏/底栏
INK = "#2f2f2d"          # 主文字
SUB = "#8b8b88"          # 次要文字
FAINT = "#b3b3b0"        # 占位提示
ACCENT = "#3f6f52"       # 鼠尾草绿（选中/进度）
ACCENT_HOV = "#355e45"
ACCENT_SOFT = "#e9f1eb"  # 选中胶囊底
DARK = "#2e2e2c"         # 主按钮（墨色胶囊）
DARK_HOV = "#1f1f1d"
GREEN = "#3f8f5f"
GREEN_HOV = "#357a51"
RED = "#e5484d"
RED_HOV = "#d13a3f"


def flat_btn(parent, text, cmd, kind="ghost", height=32, **kw):
    """统一按钮：primary=墨色胶囊 / red=红 / ghost=白底细边框。"""
    if kind == "primary":
        kw.update(fg_color=DARK, hover_color=DARK_HOV, text_color="#ffffff")
    elif kind == "red":
        kw.update(fg_color=RED, hover_color=RED_HOV, text_color="#ffffff")
    else:
        kw.update(fg_color=CARD, hover_color=CARD_HOV, text_color=INK,
                  text_color_disabled="#8f8f89",
                  border_width=1, border_color=BORDER)
    kw.setdefault("corner_radius", 9)
    return ctk.CTkButton(parent, text=text, command=cmd, height=height, **kw)


def flat_switch(parent, text, var, cmd=None) -> ctk.CTkSwitch:
    return ctk.CTkSwitch(parent, text=text, variable=var, command=cmd,
                         progress_color=ACCENT, button_color="#ffffff",
                         button_hover_color="#ffffff",
                         fg_color="#e2e2df", text_color=INK,
                         font=("Microsoft YaHei UI", 10))


class ScrollFrame(ctk.CTkScrollableFrame):
    """滚动条加宽加深、滚轮提速、点槽翻页的 CTkScrollableFrame。

    原版：滚轮一格只滚 ~20px（Windows 习惯 ~60px）、滚动条 16px 宽颜色淡、
    点槽直接跳到点击点而不是翻一页，鼠标悬在滚动条上滚轮也只有 3px。
    """

    def _check_if_valid_scroll(self, widget):
        # 原版跳过 CTkSlider：滑块上滚轮既不滚面板又改值，两头都不好用。
        # 这里放行滑块（滑块自己的滚轮已 unbind，滚轮穿透给面板滚动）；
        # 滚动条和文本框仍自己处理。
        if widget == self._parent_canvas:
            return True
        if isinstance(widget, (ctk.CTkScrollbar, ctk.CTkTextbox)):
            return False
        if isinstance(widget, ctk.CTkScrollableFrame):
            return widget._parent_canvas == self._parent_canvas
        if widget.master is not None:
            return self._check_if_valid_scroll(widget.master)
        return False

    WHEEL_STEP = 60   # 滚轮一格滚动的像素

    def __init__(self, master, **kw):
        kw.setdefault("scrollbar_button_color", "#c2c2bd")
        kw.setdefault("scrollbar_button_hover_color", "#9d9d96")
        super().__init__(master, **kw)
        self._scrollbar.configure(width=18)
        cv = self._scrollbar._canvas
        # 点滚动条槽 = 翻一页（Windows 习惯），不再跳到点击点
        cv.tag_bind("border_parts", "<Button-1>", self._trough_click)
        cv.bind("<MouseWheel>", self._wheel)

    def _wheel(self, ev) -> str:
        self._parent_canvas.yview("scroll", self._wheel_units(ev), "units")
        return "break"

    def _wheel_units(self, ev) -> int:
        units = max(1, int(abs(ev.delta) * self.WHEEL_STEP / 120))
        return -units if ev.delta > 0 else units

    def _mouse_wheel_all(self, event) -> None:
        if self._check_if_valid_scroll(event.widget):
            cv = self._parent_canvas
            if self._shift_pressed:
                if cv.xview() != (0.0, 1.0):
                    cv.xview("scroll", self._wheel_units(event), "units")
            elif cv.yview() != (0.0, 1.0):
                cv.yview("scroll", self._wheel_units(event), "units")

    def _trough_click(self, ev) -> None:
        sb = self._scrollbar
        v = ev.y / max(1, sb._canvas.winfo_height())
        if v < sb._start_value:
            self._parent_canvas.yview("scroll", -1, "pages")
        elif v > sb._end_value:
            self._parent_canvas.yview("scroll", 1, "pages")

# 多帧一致下拉：文字 → min_count（None = N-1，推荐）
AGREE_OPTS = [("自动（推荐）", None), ("每张都要一样", "N"), ("宽松", "N-2"),
              ("非常宽松", "N-3")]


def checkerboard(h: int, w: int) -> np.ndarray:
    y, x = np.indices((h, w))
    odd = ((y // CELL) + (x // CELL)) % 2
    out = np.empty((h, w, 3), np.uint8)
    out[odd == 0] = (250, 250, 248)
    out[odd == 1] = (231, 231, 228)
    return out


def save_dir() -> str:
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
        else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(base, "out")
    os.makedirs(out, exist_ok=True)
    return out


class Tip:
    """悬浮提示：鼠标停 0.5 秒显示。"""

    def __init__(self, widget, text: str):
        self.w, self.text, self.tip, self.after = widget, text, None, None
        widget.bind("<Enter>", self._in)
        widget.bind("<Leave>", self._out)
        widget.bind("<ButtonPress>", self._out)

    def _in(self, _e=None):
        self._out()
        self.after = self.w.after(500, self._show)

    def _out(self, _e=None):
        if self.after:
            self.w.after_cancel(self.after)
            self.after = None
        if self.tip:
            self.tip.destroy()
            self.tip = None

    def _show(self):
        self.after = None
        x = self.w.winfo_rootx() + self.w.winfo_width() // 2
        y = self.w.winfo_rooty() + self.w.winfo_height() + 4
        self.tip = tk.Toplevel(self.w)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        tk.Label(self.tip, text=self.text, bg="#2b2b29", fg="#f5f5f2",
                 font=("Microsoft YaHei UI", 10), padx=8, pady=4,
                 justify="left", highlightthickness=1,
                 highlightbackground="#3a3a38").pack()
        self.tip.geometry(f"+{x - self.tip.winfo_reqwidth() // 2}+{y}")


class MakeTplApp:
    def __init__(self, root: ctk.CTk):
        self.root = root
        root.title(f"透明模板制作 {BUILD}")
        ico = os.path.join(getattr(sys, "_MEIPASS",
                                   os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "icon.ico")
        if os.path.exists(ico):
            root.iconbitmap(ico)
        root.configure(fg_color=BG)
        scale = ctk.ScalingTracker.get_window_scaling(root) or 1.0
        sw = int(root.winfo_screenwidth() / scale)
        sh = int(root.winfo_screenheight() / scale)
        root.minsize(min(880, int(sw * 0.72)), min(620, int(sh * 0.80)))
        # 居中，并给任务栏留 48px：1366×768 之类的小屏上窗口也不会压到屏幕外
        gw, gh = min(1100, int(sw * 0.88)), min(860, max(1, sh - 48))
        root.geometry(f"{gw}x{gh}+{max(0, (sw - gw) // 2)}+{max(0, (sh - 48 - gh) // 2)}")
        self.hwnd: int | None = None
        self.frame: np.ndarray | None = None
        self.frames: list[np.ndarray] = []
        self.box: tuple[int, int, int, int] | None = None
        self.sscale = 1.0   # 源画布：画布像素 / 图像像素
        self.escale = 1.0   # 预览画布
        self._src_img: np.ndarray | None = None   # 源画布正在显示的底图
        self._view_off = (0, 0)   # 显示图坐标 → 客户区坐标的偏移（动采只显示选区时非零）
        self._checker_cache: dict = {}   # 棋盘格底图按尺寸缓存，_render_edit 每帧省一次分配
        self.zoom = 0.0     # 预览缩放倍数；0 = 适应窗口
        self.vcenter: tuple[float, float] | None = None
        self.szoom = 0.0    # 源画面缩放倍数；0 = 适应画布
        self.scenter: tuple[float, float] | None = None
        self._src_origin = (0.0, 0.0)   # 源图 (0,0) 对应的画布坐标
        self._pan_start = None
        self._pan_cv: tk.Canvas | None = None
        self._fit_job = None
        self.picked: tuple[int, int, np.ndarray] | None = None
        self.frame_alpha: np.ndarray | None = None   # 载入的 PNG 自带的透明度（重新修图用）
        self.base_origin: tuple[int, int] | None = None   # base 左上角在窗口客户区里的坐标
        self.src_fid: tuple[bool, str] | None = None      # 当前画面是否 1:1 原始像素
        self.frame_from_image = False   # 当前画面是载入的图片（不是绑定窗口的截图）
        self.base: np.ndarray | None = None
        self.mask: np.ndarray | None = None
        self.sel: np.ndarray | None = None   # 魔术棒选中的"要保留"区域
        self.undo: list[tuple[np.ndarray, np.ndarray, np.ndarray | None]] = []
        self._crop_armed = False
        self._brush_mode: str | None = None   # None / "paint" / "erase"
        self._wand_pending = None             # (x,y)：松手才算点选，动了算平移
        self._uic: dict[int, dict] = {}       # 按钮上次配置，没变就不重配防闪
        self._photos: dict[str, object] = {}
        self._drag_start = None
        self._aiming = False
        self._aim_hwnd = 0
        self._hl = None
        self._view: np.ndarray | None = None
        self._mags: dict[tk.Canvas, tk.Canvas] = {}
        self._resize_job = None
        self._dyn = False
        self._dyn_box = None
        self._dyn_paused = False
        self._dyn_next_compute = 0.0
        self._dyn_tol = 8
        self._dyn_agree = ""
        self._test_running = False
        self._live_on = False
        self._live_show = False
        self._live_gen = 0
        self._live_stop = threading.Event()
        self._live_stop.set()
        self._live_gap = 0.3
        self._src_disp_wh = (640, 400)
        self._cap_note = ""
        self.live_var = tk.BooleanVar(value=True)
        self.contig_var = tk.BooleanVar(value=True)   # 魔术棒「只选连通」开关
        self._saved = False
        self.count_var = tk.StringVar(value="8")   # 旧连拍接口保留用
        self.gap_var = tk.StringVar(value="250")
        self.agree_var = tk.StringVar(value=AGREE_OPTS[0][0])
        self._adv_win = None
        self._build()
        root.bind("<Control-z>", lambda _e: self.undo_step())
        root.bind("<Control-d>", lambda _e: self._deselect())
        root.bind("<Escape>", lambda _e: self._brush_off())

    @property
    def editing(self) -> bool:
        return self.base is not None and self.mask is not None

    def _px(self, v: int) -> int:
        """逻辑尺寸 → 物理像素（原生 tk 画布不会跟着 CTk 自动缩放）。"""
        try:
            return int(round(v * ctk.ScalingTracker.get_widget_scaling(self.root)))
        except Exception:
            return v

    # ================================================================ 界面
    def _group(self, parent, title: str) -> ctk.CTkFrame:
        f = ctk.CTkFrame(parent, corner_radius=14, fg_color=CARD,
                         border_width=1, border_color=BORDER)
        f.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=INK, anchor="w").pack(fill="x", padx=14,
                                                      pady=(13, 8))
        return f

    def _build(self) -> None:
        head = ctk.CTkFrame(self.root, fg_color=HEAD, corner_radius=0, height=48)
        head.pack(fill="x")
        head.pack_propagate(False)
        ctk.CTkLabel(head, text="透明模板制作",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=INK).pack(side="left", padx=(16, 8), pady=11)
        ctk.CTkLabel(head, text="识别图模板工具", font=ctk.CTkFont(size=11),
                     text_color=SUB).pack(side="left", pady=14)
        steps = ctk.CTkFrame(head, fg_color="transparent")
        steps.pack(side="right", padx=16, pady=12)
        self._STEP_NAMES = ["取画面", "框选", "修图", "保存"]
        self._step_labs = []
        for i, name in enumerate(self._STEP_NAMES):
            lab = ctk.CTkLabel(steps, text=f"{i + 1} {name}",
                               font=ctk.CTkFont(size=11), text_color=SUB,
                               corner_radius=9)
            lab.pack(side="left", ipadx=8, ipady=3)
            self._step_labs.append(lab)
            if i < len(self._STEP_NAMES) - 1:
                ctk.CTkLabel(steps, text="›", text_color=FAINT,
                             font=ctk.CTkFont(size=12)).pack(side="left", padx=4)
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        main = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        main.pack(fill="both", expand=True, padx=12, pady=(10, 6))
        main.grid_columnconfigure(0, weight=1, uniform="cols")
        main.grid_columnconfigure(1, weight=1, uniform="cols")
        main.grid_rowconfigure(0, weight=1)
        # 每栏 = 可滚动区（卡片）+ 固定底栏（最常点的按钮）。底栏永远可见，
        # 滚动区里的画布按剩余高度自动撑满，窗口多矮都不会把主按钮挤出去。
        lcol = ctk.CTkFrame(main, fg_color="transparent", corner_radius=0)
        lcol.grid(row=0, column=0, sticky="nsew")
        rcol = ctk.CTkFrame(main, fg_color="transparent", corner_radius=0)
        rcol.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        for col in (lcol, rcol):
            col.grid_rowconfigure(0, weight=1)
            col.grid_columnconfigure(0, weight=1)
        self.left = ScrollFrame(lcol, width=420, fg_color="transparent")
        self.left.grid(row=0, column=0, sticky="nsew")
        self.right = ScrollFrame(rcol, width=420, fg_color="transparent")
        self.right.grid(row=0, column=0, sticky="nsew")
        self.left_dock = ctk.CTkFrame(lcol, fg_color="transparent", corner_radius=0)
        self.left_dock.grid(row=1, column=0, sticky="ew", padx=(0, 24))
        self.right_dock = ctk.CTkFrame(rcol, fg_color="transparent", corner_radius=0)
        self.right_dock.grid(row=1, column=0, sticky="ew", padx=(0, 24))
        for sf in (self.left, self.right):
            sf._parent_canvas.bind("<Configure>", self._schedule_fit, add="+")
            sf.bind("<Configure>", self._schedule_fit, add="+")

        foot = ctk.CTkFrame(self.root, fg_color=HEAD, corner_radius=0)
        foot.pack(side="bottom", fill="x")
        tk.Frame(self.root, bg=BORDER, height=1).pack(side="bottom", fill="x")
        self.hover_var = tk.StringVar(value="")
        ctk.CTkLabel(foot, textvariable=self.hover_var, anchor="w",
                     text_color=SUB, font=ctk.CTkFont(size=11)
                     ).pack(side="left", padx=(12, 0), pady=4)
        self.status = tk.StringVar(value="先绑定窗口或载入图片")
        ctk.CTkLabel(foot, textvariable=self.status, anchor="e",
                     text_color=SUB, font=ctk.CTkFont(size=11)
                     ).pack(side="right", padx=(0, 12), pady=4)

        self._card_bind(self.left)
        self._card_src(self.left, self.left_dock)
        self._card_prev(self.right)
        self._card_edit(self.right)
        self._card_save(self.right_dock)
        self._refresh_ui()
        self._schedule_fit()

    def _schedule_fit(self, _ev=None) -> None:
        if self._fit_job is None:
            self._fit_job = self.root.after(40, self._fit_columns)

    def _fit_columns(self) -> None:
        """画布吃掉滚动区里剩下的高度：量实际内容高度，不靠写死的"窗口高-300"。

        内容放不下时画布缩到下限、出滚动条；放得下时画布变高，直到正好填满。
        调高度会再触发 Configure，但差值收敛到 0 就停，不会循环。"""
        self._fit_job = None
        for col, canvas, lo in ((self.left, self.src, self._px(200)),
                                (self.right, self.prev, self._px(150))):
            view_h = col._parent_canvas.winfo_height()
            if view_h < 50:
                continue
            cur = int(float(canvas.cget("height")))
            new = max(lo, min(self._px(2400), cur + view_h - col.winfo_reqheight() - 4))
            if abs(new - cur) >= 3:
                canvas.config(height=new)

    def _set_fid(self, fid: tuple[bool, str] | None) -> None:
        """显示/记录当前画面是不是 1:1 原始像素；None = 清空。"""
        self.src_fid = fid
        if fid is None:
            self.fid_var.set("")
            self.fid_lab.pack_forget()
            return
        ok, text = fid
        self.fid_var.set(text)
        self.fid_lab.configure(text_color=ACCENT if ok else RED)
        if not self.fid_lab.winfo_manager():
            self.fid_lab.pack(fill="x", pady=(3, 0))

    def _check_window_fid(self) -> None:
        """按绑定窗口的真实客户区尺寸和显示缩放，判断截到的是不是原始像素。"""
        if self.hwnd is None or self.frame_from_image:
            return
        try:
            size = winapi.client_size(self.hwnd)
            fid = fidelity.assess(size, winapi.window_dpi(self.hwnd),
                                  winapi.monitor_dpi(self.hwnd))
        except Exception:  # noqa: BLE001
            return
        self._set_fid(fid)

    def _wrap_to(self, label: ctk.CTkLabel, holder) -> None:
        """label 的换行宽度跟着容器走，窄窗口里文字换行而不是被截断。"""
        def on_cfg(ev) -> None:
            if ev.width < 40:
                return
            try:
                scale = ctk.ScalingTracker.get_widget_scaling(self.root) or 1.0
                label.configure(wraplength=max(100, int(ev.width / scale) - 8))
            except Exception:
                pass
        holder.bind("<Configure>", on_cfg, add="+")

    def _card_bind(self, parent) -> None:
        lf = self._group(parent, "绑定窗口")
        row = ctk.CTkFrame(lf, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(2, 13))
        p = self._px
        self.aim = tk.Canvas(row, width=p(46), height=p(46), bg="#fbfbfa",
                             highlightthickness=1, highlightbackground=BORDER)
        self.aim.pack(side="left")
        self.aim.create_oval(p(11), p(11), p(35), p(35), outline=RED, width=2)
        self.aim.create_line(p(23), p(5), p(23), p(15), fill=RED, width=2)
        self.aim.create_line(p(23), p(31), p(23), p(41), fill=RED, width=2)
        self.aim.create_line(p(5), p(23), p(15), p(23), fill=RED, width=2)
        self.aim.create_line(p(31), p(23), p(41), p(23), fill=RED, width=2)
        self.aim.create_oval(p(20), p(20), p(26), p(26), fill=RED, outline="")
        self.aim.bind("<ButtonPress-1>", self._aim_down)
        self.aim.bind("<ButtonRelease-1>", self._aim_up)
        Tip(self.aim, "按住准星，拖到游戏窗口上松手")
        btns = ctk.CTkFrame(row, fg_color="transparent")
        btns.pack(side="right", padx=(8, 0))
        flat_btn(btns, "从列表选", self.pick_from_list, width=76, height=28).pack()
        self.unbind_btn = flat_btn(btns, "解绑", self.unbind, width=76, height=28)
        self.unbind_btn.pack(pady=(6, 0))
        Tip(self.unbind_btn, "解除当前窗口绑定；画面定格在最后一帧")
        mid = ctk.CTkFrame(row, fg_color="transparent")
        mid.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.target_var = tk.StringVar(value="按住准星，拖到游戏窗口上松手")
        tl = ctk.CTkLabel(mid, textvariable=self.target_var, anchor="w",
                          text_color=INK, justify="left", wraplength=200)
        tl.pack(fill="x")
        self._wrap_to(tl, mid)
        self.fid_var = tk.StringVar(value="")
        self.fid_lab = ctk.CTkLabel(mid, textvariable=self.fid_var, anchor="w",
                                    justify="left", text_color=SUB, wraplength=200,
                                    font=ctk.CTkFont(size=11))
        self._wrap_to(self.fid_lab, mid)

    def _card_src(self, parent, dock) -> None:
        # 卡片 = 标题行（含两个开关）+ 画布；常点的按钮放进固定底栏 dock
        lf = ctk.CTkFrame(parent, corner_radius=14, fg_color=CARD,
                          border_width=1, border_color=BORDER)
        lf.pack(fill="x", pady=(0, 12))
        head = ctk.CTkFrame(lf, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(11, 6))
        ctk.CTkLabel(head, text="画面", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=INK, anchor="w").pack(side="left")
        self.live_sw = flat_switch(head, "实时画面", self.live_var,
                                   self._on_live_toggle)
        self.live_sw.pack(side="right")
        Tip(self.live_sw, "开 = 窗口画面实时刷新；关 = 暂停定格，方便慢慢框")
        self.rel_var = tk.BooleanVar(value=True)
        flat_switch(head, "相对坐标", self.rel_var,
                    self._update_coord).pack(side="right", padx=(0, 10))
        cwrap = tk.Frame(lf, bg=CANVAS)
        cwrap.pack(fill="x", padx=12, pady=(0, 10))
        # 请求宽度给小：真实宽度由 fill 决定，写大了窄窗口里整张卡会被撑出可视区
        self.src = tk.Canvas(cwrap, width=self._px(200), height=self._px(280),
                             bg=CANVAS, highlightthickness=1,
                             highlightbackground="#dededb", cursor="crosshair")
        self.src.pack(fill="both", expand=True)
        self._placeholder(self.src, "点「截取画面」或「载入图片」开始制作模板\n"
                                    "拖动框选 · Ctrl+滚轮缩放\n"
                                    "截 NPC 前先在游戏里 F9 / Alt+H 屏蔽周边玩家")
        for ev, fn in (("<ButtonPress-1>", self._press), ("<B1-Motion>", self._drag_move),
                       ("<ButtonRelease-1>", self._release), ("<Motion>", self._hover),
                       ("<ButtonPress-2>", self._pan_press), ("<B2-Motion>", self._pan_move),
                       ("<ButtonRelease-2>", self._pan_release),
                       ("<ButtonPress-3>", self._pan_press), ("<B3-Motion>", self._pan_move),
                       ("<ButtonRelease-3>", self._pan_release),
                       ("<MouseWheel>", self._swheel)):
            self.src.bind(ev, fn)
        self.src.bind("<Configure>", self._on_canvas_resize, add="+")
        self.src.bind("<Enter>", lambda _e: self.src.focus_set())
        self.src.bind("<Leave>", lambda _e: self._hide_mag())
        for key, d in (("<Left>", (-1, 0)), ("<Right>", (1, 0)),
                       ("<Up>", (0, -1)), ("<Down>", (0, 1))):
            self.src.bind(key, lambda e, d=d: self._nudge(d[0], d[1], e))
        mag = tk.Canvas(cwrap, width=self._px(128), height=self._px(148),
                        bg="#ffffff", highlightthickness=1,
                        highlightbackground="#dcdcd9")
        self._mags[self.src] = mag
        sc = ctk.CTkFrame(cwrap, fg_color=CARD, corner_radius=9,
                          border_width=1, border_color=BORDER)
        self.szoom_var = tk.StringVar(value="原图 —")
        ctk.CTkLabel(sc, textvariable=self.szoom_var, text_color=SUB,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(8, 2), pady=3)
        ctk.CTkLabel(sc, text="｜", text_color=BORDER).pack(side="left", pady=3)
        rb = ctk.CTkLabel(sc, text="还原", text_color=ACCENT, cursor="hand2",
                          font=ctk.CTkFont(size=11))
        rb.pack(side="left", padx=(2, 8), pady=3)
        rb.bind("<Button-1>", lambda _e: self._szoom_fit())
        Tip(rb, "恢复适应画布；Ctrl+滚轮缩放，右/中键拖动平移，"
                "放到 100% 看到的就是逐像素原图")
        self.src_chip = sc

        bar = ctk.CTkFrame(dock, corner_radius=14, fg_color=CARD,
                           border_width=1, border_color=BORDER)
        bar.pack(fill="x", pady=(0, 4))
        row = ctk.CTkFrame(bar, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(10, 4))
        self.coord_var = tk.StringVar(value="相对：—")
        ctk.CTkLabel(row, textvariable=self.coord_var, text_color=SUB,
                     anchor="w").pack(side="left")
        self.frames_var = tk.StringVar(value="")
        self.frames_lab = ctk.CTkLabel(row, textvariable=self.frames_var,
                                       text_color=SUB, anchor="e")
        self.frames_lab.pack(side="right")

        row = ctk.CTkFrame(bar, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 4))
        flat_btn(row, "截取画面", self.grab_once, width=84).pack(side="left")
        flat_btn(row, "载入图片", self.load_image, width=84).pack(side="left", padx=(6, 0))
        fb = flat_btn(row, "整帧截图", self.save_fullshot, width=84)
        fb.pack(side="left", padx=(6, 0))
        Tip(fb, "把整个画面按原始像素 1:1 存成 PNG：绑了窗口就现场抓一帧，"
                "载入的图片就原样存回；不裁不缩不抠图")
        self.adv_btn = ctk.CTkLabel(row, text="高级参数  ▸", text_color=SUB,
                                    cursor="hand2", anchor="e")
        self.adv_btn.pack(side="right")
        self.adv_btn.bind("<Button-1>", lambda _e: self._toggle_adv())

        row = ctk.CTkFrame(bar, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkLabel(row, text="框选后 →", text_color=SUB).pack(side="left")
        self.static_btn = flat_btn(row, "静态截图", self.static_shot, kind="primary",
                                   width=90)
        self.static_btn.pack(side="left", padx=(6, 0))
        Tip(self.static_btn, "把框选区域截下来直接进编辑（用的就是你框选时看到的那一帧）")
        self.dyn_btn = flat_btn(row, "动态截图", self.dyn_shot, width=90)
        self.dyn_btn.pack(side="left", padx=(6, 0))
        Tip(self.dyn_btn, "实时盯着框选区域：不动的像素留下、动的噪点自动去掉，满意了再点一次生成")
        self.dyn_pause_btn = flat_btn(row, "暂停", self.dyn_pause, width=64)

    def _card_prev(self, parent) -> None:
        lf = self._group(parent, "抠图预览（灰格 = 透明）")
        cwrap = tk.Frame(lf, bg=CANVAS)
        cwrap.pack(fill="x", padx=12, pady=(2, 6))
        self.prev = tk.Canvas(cwrap, width=self._px(200), height=self._px(230),
                              bg=CANVAS, highlightthickness=1,
                              highlightbackground="#dededb", cursor="crosshair")
        self.prev.pack(fill="both", expand=True)
        self._placeholder(self.prev, "框选左侧画面后\n这里实时预览")
        for ev, fn in (("<ButtonPress-1>", self._press), ("<B1-Motion>", self._drag_move),
                       ("<ButtonRelease-1>", self._release), ("<Motion>", self._hover),
                       ("<ButtonPress-2>", self._pan_press), ("<B2-Motion>", self._pan_move),
                       ("<ButtonRelease-2>", self._pan_release),
                       ("<ButtonPress-3>", self._pan_press), ("<B3-Motion>", self._pan_move),
                       ("<ButtonRelease-3>", self._pan_release),
                       ("<MouseWheel>", self._wheel_zoom)):
            self.prev.bind(ev, fn)
        self.prev.bind("<Configure>", self._on_canvas_resize, add="+")
        self.prev.bind("<Leave>", lambda _e: self._hide_mag())
        self.wand_var = tk.StringVar(value="✦ 魔术棒 · Shift加选 · Alt减选")
        wc = ctk.CTkFrame(cwrap, fg_color=CARD, corner_radius=9,
                          border_width=1, border_color=BORDER)
        ctk.CTkLabel(wc, textvariable=self.wand_var, text_color=ACCENT,
                     font=ctk.CTkFont(size=11)).pack(padx=9, pady=3)
        self.wand_chip = wc
        self.zoom_var = tk.StringVar(value="适应")
        bar = ctk.CTkFrame(cwrap, fg_color=CARD, corner_radius=9,
                           border_width=1, border_color=BORDER)
        minus = ctk.CTkLabel(bar, text="−", width=20, text_color=SUB,
                             cursor="hand2", font=ctk.CTkFont(size=13))
        minus.pack(side="left", padx=(7, 2), pady=2)
        minus.bind("<Button-1>", lambda _e: self._zoom_by(1 / 1.3))
        pct = ctk.CTkLabel(bar, textvariable=self.zoom_var, width=42,
                           text_color=INK, cursor="hand2",
                           font=ctk.CTkFont(size=11))
        pct.pack(side="left", padx=2, pady=2)
        pct.bind("<Button-1>", lambda _e: self._zoom_fit())
        Tip(pct, "点这里恢复适应窗口；也可以滚动滚轮缩放、按住右键拖动平移")
        plus = ctk.CTkLabel(bar, text="+", width=20, text_color=SUB,
                            cursor="hand2", font=ctk.CTkFont(size=13))
        plus.pack(side="left", padx=(2, 7), pady=2)
        plus.bind("<Button-1>", lambda _e: self._zoom_by(1.3))
        self.zoom_bar = bar
        mag = tk.Canvas(cwrap, width=self._px(128), height=self._px(148),
                        bg="#ffffff", highlightthickness=1,
                        highlightbackground="#dcdcd9")
        self._mags[self.prev] = mag
        self.info_var = tk.StringVar(value="还没有模板")
        il = ctk.CTkLabel(lf, textvariable=self.info_var, text_color=SUB, anchor="nw",
                          justify="left", wraplength=300, height=30)
        il.pack(fill="x", padx=12, pady=(0, 11))
        self._wrap_to(il, lf)

    def _card_edit(self, parent) -> None:
        lf = self._group(parent, "修图")
        tip = ctk.CTkFrame(lf, fg_color=ACCENT_SOFT, corner_radius=10)
        tip.pack(fill="x", padx=12, pady=(2, 8))
        trow = ctk.CTkFrame(tip, fg_color="transparent")
        trow.pack(fill="x", padx=8, pady=6)
        wand = ctk.CTkLabel(trow, text="✦ 魔术棒", fg_color=ACCENT,
                            text_color="#ffffff", corner_radius=7, height=20,
                            cursor="hand2",
                            font=ctk.CTkFont(size=10, weight="bold"))
        wand.pack(side="left")
        wand.bind("<Button-1>", lambda _e: self._wand_hint())
        ctk.CTkLabel(trow, text="点颜色选一片 · Shift加 Alt减 · 拖动平移",
                     text_color=ACCENT, font=ctk.CTkFont(size=10),
                     anchor="w").pack(side="left", padx=(8, 0))
        Tip(wand, "魔术棒已启用：在预览里点颜色就等于用它取色")

        self.tol_var = tk.IntVar(value=8)
        row = ctk.CTkFrame(lf, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=2)
        row.grid_columnconfigure(1, weight=1)
        lab = ctk.CTkLabel(row, text="容差", width=36, anchor="w")
        lab.grid(row=0, column=0)
        tol_sl = ctk.CTkSlider(row, from_=0, to=64, number_of_steps=64,
                               button_color="#3a3a38", button_hover_color="#1f1f1d",
                               progress_color=ACCENT, fg_color="#e6e6e3",
                               command=self._tol_cmd)
        tol_sl.set(8)
        tol_sl._canvas.unbind("<MouseWheel>")   # 别吃滚轮：留给面板滚动
        tol_sl.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        self.tol_lab = ctk.CTkLabel(row, text="8", width=22, anchor="e")
        self.tol_lab.grid(row=0, column=2)
        Tip(lab, "多帧求稳的容差：几帧间颜色差多少算同一个像素")

        self.wand_tol_var = tk.IntVar(value=WAND_TOL)
        wrow = ctk.CTkFrame(lf, fg_color="transparent")
        wrow.pack(fill="x", padx=12, pady=2)
        wrow.grid_columnconfigure(1, weight=1)
        wlab = ctk.CTkLabel(wrow, text="棒容差", width=36, anchor="w")
        wlab.grid(row=0, column=0)
        wsl = ctk.CTkSlider(wrow, from_=0, to=64, number_of_steps=64,
                            button_color="#3a3a38", button_hover_color="#1f1f1d",
                            progress_color=ACCENT, fg_color="#e6e6e3",
                            command=self._wtol_cmd)
        wsl.set(WAND_TOL)
        wsl._canvas.unbind("<MouseWheel>")
        wsl.grid(row=0, column=1, sticky="ew", padx=(2, 4))
        self.wtol_lab = ctk.CTkLabel(wrow, text=str(WAND_TOL), width=22, anchor="e")
        self.wtol_lab.grid(row=0, column=2)
        flat_switch(wrow, "只选连通", self.contig_var).grid(row=0, column=3,
                                                            padx=(8, 0))
        Tip(wlab, "魔术棒专用容差，和上面的「容差」分开调")

        row2 = ctk.CTkFrame(lf, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(6, 2))
        (self.invert_btn, self.despeckle_btn, self.crop_btn,
         self.undo_btn, self.exit_btn) = (
            flat_btn(row2, text, cmd, width=60, height=28, **kw) for text, cmd, kw in
            (("反选透明", self.invert, {"kind": "primary"}),
             ("去杂点", self.despeckle, {}),
             ("框选擦除", self.arm_crop, {}),
             ("撤销", self.undo_step, {}),
             ("退出", self.exit_edit, {})))
        for b in (self.invert_btn, self.despeckle_btn, self.crop_btn,
                  self.undo_btn, self.exit_btn):
            b.pack(side="left", fill="x", expand=True, padx=(0, 5))
        Tip(self.despeckle_btn, "清掉小于 4 像素的孤立碎块")

        row4 = ctk.CTkFrame(lf, fg_color="transparent")
        row4.pack(fill="x", padx=12, pady=(0, 2))
        self.shrink_btn = flat_btn(row4, "收边 1px", self.shrink_edge, height=28)
        self.main_btn = flat_btn(row4, "只留最大块", self.keep_main, height=28)
        self.shrink_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.main_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        Tip(self.shrink_btn, "保留区向内缩 1 像素。抗锯齿的外圈混着当时的背景色，"
                             "换个背景就对不上，抠 NPC 建议收一次")
        Tip(self.main_btn, "只留最大的一整块，阴影、飘字、旁边的小碎片都去掉")

        row3 = ctk.CTkFrame(lf, fg_color="transparent")
        row3.pack(fill="x", padx=12, pady=(0, 2))
        self.paint_btn = flat_btn(row3, "✎ 画笔",
                                  lambda: self.arm_brush("paint"),
                                  width=54, height=28)
        self.eraser_btn = flat_btn(row3, "⌫ 橡皮",
                                   lambda: self.arm_brush("erase"),
                                   width=54, height=28)
        self.paint_btn.pack(side="left", padx=(0, 5))
        self.eraser_btn.pack(side="left", padx=(0, 5))
        Tip(self.paint_btn, "左键拖动补回保留像素；右/中键拖动平移；再点或 Esc 退出")
        Tip(self.eraser_btn, "左键拖动擦掉保留像素；右/中键拖动平移；再点或 Esc 退出")
        blab = ctk.CTkLabel(row3, text="笔径", width=30, anchor="w")
        blab.pack(side="left")
        self.brush_var = tk.IntVar(value=4)
        bsl = ctk.CTkSlider(row3, from_=1, to=24, number_of_steps=23, width=62,
                            button_color="#3a3a38", button_hover_color="#1f1f1d",
                            progress_color=ACCENT, fg_color="#e6e6e3",
                            command=self._brush_cmd)
        bsl.set(4)
        bsl._canvas.unbind("<MouseWheel>")
        bsl.pack(side="left", padx=(2, 4))
        self.brush_lab = ctk.CTkLabel(row3, text="4", width=20, anchor="e")
        self.brush_lab.pack(side="left")

        ctk.CTkLabel(lf, text="滚轮缩放 · 按住拖动平移 · 框选擦除=拖矩形去像素",
                     text_color=FAINT, font=ctk.CTkFont(size=10),
                     anchor="w").pack(fill="x", padx=12, pady=(2, 5))

    def _wtol_cmd(self, v) -> None:
        self.wand_tol_var.set(int(v))
        self.wtol_lab.configure(text=str(int(v)))

    def _brush_cmd(self, v) -> None:
        self.brush_var.set(int(v))
        self.brush_lab.configure(text=str(int(v)))

    def _tol_cmd(self, v) -> None:
        self.tol_var.set(int(v))
        self._dyn_tol = int(v)
        self.tol_lab.configure(text=str(int(v)))

    def _card_save(self, dock) -> None:
        """固定底栏：保存和测试永远看得见，不用滚下去找。"""
        lf = ctk.CTkFrame(dock, corner_radius=14, fg_color=CARD,
                          border_width=1, border_color=BORDER)
        lf.pack(fill="x", pady=(0, 4))
        self.save_btn = flat_btn(lf, "保存透明 PNG", self.save, kind="primary",
                                 height=36)
        self.save_btn.pack(fill="x", padx=12, pady=(12, 6))
        row = ctk.CTkFrame(lf, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 12))
        self.test_btn = flat_btn(row, "测试匹配", self.test_match, height=30)
        self.test_btn.pack(side="left", fill="x", expand=True)
        self.score_var = tk.StringVar(value=str(MATCH_SCORE))
        ctk.CTkEntry(row, textvariable=self.score_var, width=44,
                     fg_color=CARD, border_color=BORDER,
                     text_color=INK).pack(side="right")
        lab = ctk.CTkLabel(row, text="分数≤", anchor="e")
        lab.pack(side="right", padx=(8, 4))
        Tip(lab, "和 mhxy 的判定一致：匹配分数 ≤ 这个值才算找到（默认 10）")
        self.mtol_var = tk.StringVar(value=str(MATCH_TOL))
        ctk.CTkEntry(row, textvariable=self.mtol_var, width=44,
                     fg_color=CARD, border_color=BORDER,
                     text_color=INK).pack(side="right")
        lab = ctk.CTkLabel(row, text="容差", anchor="e")
        lab.pack(side="right", padx=(8, 4))
        Tip(lab, "和 mhxy 的找图容差一致：关键点颜色每通道差 ≤ 这个值才算候选（默认 24）")

    def _post(self, fn, *args) -> None:
        self.root.after(0, lambda: fn(*args))

    def _toggle_adv(self) -> None:
        """悬浮小面板，不重排页面。"""
        if self._adv_win is not None and self._adv_win.winfo_exists():
            self._close_adv()
            return
        top = ctk.CTkToplevel(self.root)
        top.withdraw()
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(fg_color="#d8d8d5")
        card = ctk.CTkFrame(top, fg_color=CARD, corner_radius=14)
        card.pack(fill="both", expand=True, padx=1, pady=1)

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(14, 8))
        lab = ctk.CTkLabel(row, text="抓帧间隔", text_color=SUB)
        lab.pack(side="left")
        Tip(lab, "实时画面和动态截图的抓帧间隔，默认 250ms")
        ctk.CTkEntry(row, textvariable=self.gap_var, width=56,
                     fg_color=CARD, border_color=BORDER,
                     text_color=INK).pack(side="left", padx=(8, 4))
        ctk.CTkLabel(row, text="ms", text_color=SUB).pack(side="left")

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 8))
        lab = ctk.CTkLabel(row, text="多帧一致", text_color=SUB)
        lab.pack(side="left")
        Tip(lab, "几张里颜色一样才算稳定像素，拿不准就用自动")
        ctk.CTkOptionMenu(row, values=[t for t, _ in AGREE_OPTS],
                          variable=self.agree_var, width=128,
                          fg_color=CARD, text_color=INK,
                          button_color="#f1f1ee", button_hover_color="#e9e9e6",
                          dropdown_fg_color=CARD, dropdown_text_color=INK
                          ).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(card, text="间隔越小抓得越快；一致越严格，噪点越少但可能缺字",
                     text_color=FAINT, font=ctk.CTkFont(size=10),
                     anchor="w").pack(fill="x", padx=16, pady=(0, 10))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 14))
        flat_btn(row, "载入帧文件夹", self.load_folder, height=30).pack(side="left")
        flat_btn(row, "完成", self._close_adv, kind="primary", width=64,
                 height=30).pack(side="right")

        top.bind("<Escape>", lambda _e: self._close_adv())
        top.geometry("350x182")
        top.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        pw, ph = self._px(350), self._px(182)
        x = min(self.adv_btn.winfo_rootx(), sw - pw - 8)
        y = self.adv_btn.winfo_rooty() + self.adv_btn.winfo_height() + 4
        if y + ph > sh - 8:
            y = self.adv_btn.winfo_rooty() - ph - 4
        x, y = max(8, x), max(8, min(y, sh - ph - 8))
        top.geometry(f"+{x}+{y}")
        top.deiconify()
        top.lift()
        top.focus_force()
        self._adv_win = top

    def _close_adv(self) -> None:
        if self._adv_win is not None:
            try:
                self._adv_win.destroy()
            except Exception:
                pass
            self._adv_win = None

    # ================================================================ 状态感知 UI
    def _cfg(self, btn: ctk.CTkButton, **kw) -> None:
        """参数没变就不重配：_refresh_ui 每个渲染帧都跑，无脑 configure 会让按钮闪。
        按 key 记上次的值——同一按钮分几次配不同参数时也能正确跳过。"""
        last = self._uic.setdefault(id(btn), {})
        diff = {k: v for k, v in kw.items() if last.get(k) != v}
        if diff:
            last.update(kw)
            btn.configure(**diff)

    def _set_primary(self, btn: ctk.CTkButton, on: bool) -> None:
        """墨色主按钮：禁用时退成浅灰胶囊，避免黑底黑字看不清。"""
        if on:
            self._cfg(btn, state="normal", fg_color=DARK, hover_color=DARK_HOV,
                      text_color="#ffffff", text_color_disabled="#ffffff")
        else:
            self._cfg(btn, state="disabled", fg_color="#ececea",
                      hover_color="#ececea", text_color="#8f8f89",
                      text_color_disabled="#8f8f89")

    def _refresh_ui(self) -> None:
        """按当前状态启停按钮、刷新流程条，让不该点的按钮直接灰掉。"""
        can_shot = ((self.hwnd is not None or self.frame is not None)
                    and self.box is not None and not self.editing)
        self._set_primary(self.static_btn, can_shot and not self._dyn)
        if self._dyn:
            self._cfg(self.dyn_btn, state="normal", text="停止并生成",
                      fg_color=RED, hover_color=RED_HOV, border_width=0,
                      text_color="#ffffff")
            self._cfg(self.dyn_pause_btn,
                      text="继续" if self._dyn_paused else "暂停")
            self.dyn_pause_btn.pack(side="left", padx=(6, 0))
        else:
            self.dyn_pause_btn.pack_forget()
            self._cfg(self.dyn_btn, state="normal" if can_shot else "disabled",
                      text="动态截图", fg_color=CARD, hover_color=CARD_HOV,
                      border_width=1, border_color=BORDER, text_color=INK)
        ed = self.editing
        self._set_primary(self.save_btn, ed)
        self._set_primary(self.invert_btn, ed and self.sel is not None
                          and bool(self.sel.any()))
        for b in (self.test_btn, self.despeckle_btn, self.crop_btn, self.exit_btn,
                  self.shrink_btn, self.main_btn):
            self._cfg(b, state="normal" if ed else "disabled")
        if self._test_running:
            self._cfg(self.test_btn, state="disabled", text="匹配中…")
        else:
            self._cfg(self.test_btn, text="测试匹配")
        self._cfg(self.undo_btn,
                  state="normal" if (ed and self.undo) else "disabled")
        self._cfg(self.unbind_btn, state="normal" if self.hwnd is not None
                  else "disabled")
        if not self._dyn:
            # 修图中两个截图按钮是故意禁用的，给句提示免得以为是坏了
            self.frames_var.set("修图中…" if self.editing else "")
        self._refresh_steps()

    def _refresh_steps(self) -> None:
        states = (
            self.frame is not None or self.editing,
            self.box is not None or self.editing,
            self.editing,
            self._saved,
        )
        active = next((i for i, s in enumerate(states) if not s), None)
        for i, lab in enumerate(self._step_labs):
            if states[i]:
                lab.configure(text=f"✓ {self._STEP_NAMES[i]}",
                              text_color=ACCENT, fg_color=ACCENT_SOFT,
                              border_width=0,
                              font=ctk.CTkFont(size=11))
            elif i == active:
                lab.configure(text=f"{i + 1} {self._STEP_NAMES[i]}",
                              text_color=INK, fg_color=CARD,
                              border_width=1, border_color=BORDER,
                              font=ctk.CTkFont(size=11, weight="bold"))
            else:
                lab.configure(text=f"{i + 1} {self._STEP_NAMES[i]}",
                              text_color=FAINT, fg_color="transparent",
                              border_width=0,
                              font=ctk.CTkFont(size=11))

    def _placeholder(self, canvas: tk.Canvas, text: str) -> None:
        canvas.delete("ph")
        w, h = self._canvas_size(canvas)
        canvas.create_text(w // 2, h // 2, text=text, fill=FAINT,
                           font=("Microsoft YaHei UI", 11), tags="ph",
                           justify="center")

    def _reveal_preview(self) -> None:
        try:
            self.right._parent_canvas.yview_moveto(0)
        except Exception:
            pass

    # ================================================================ 放大镜/方向键
    def _hide_mag(self) -> None:
        for m in self._mags.values():
            m.place_forget()
        self.prev.delete("brushcur")

    def _draw_brush_ghost(self, cx: int, cy: int) -> None:
        """画笔光标圈：半径按笔径×缩放走，绿=补、红=擦，一眼分清画笔和魔术棒。"""
        self.prev.delete("brushcur")
        if not self.editing or self._brush_mode is None:
            return
        r = max(1.5, int(self.brush_var.get()) * self._zoom_scale())
        col = ACCENT if self._brush_mode == "paint" else RED
        self.prev.create_oval(cx - r, cy - r, cx + r, cy + r,
                              outline=col, width=2, tags="brushcur")
        self.prev.tag_raise("brushcur")

    def _show_mag(self, canvas: tk.Canvas, ev, ix: int, iy: int,
                  img: np.ndarray) -> None:
        mag = self._mags.get(canvas)
        if mag is None:
            return
        h, w = img.shape[:2]
        n, z = 16, self._px(8)   # 16×16 源像素放大 8 倍
        x0 = min(max(0, ix - n // 2), max(0, w - n))
        y0 = min(max(0, iy - n // 2), max(0, h - n))
        crop = img[y0:y0 + n, x0:x0 + n, :3]
        if crop.size == 0:
            mag.place_forget()
            return
        ph, pw = crop.shape[:2]
        im = Image.fromarray(crop).resize((pw * z, ph * z), Image.NEAREST)
        photo = ImageTk.PhotoImage(im)
        self._photos["mag"] = photo
        mag.delete("all")
        mag.create_image(0, 0, anchor="nw", image=photo)
        px, py = (ix - x0) * z, (iy - y0) * z
        mag.create_rectangle(px, py, px + z, py + z, outline=RED, width=1)
        mag.create_text(self._px(64), self._px(137), text=f"({ix},{iy})",
                        fill="#6b6b68", font=("Consolas", 9))
        mw, mh = canvas.winfo_width(), canvas.winfo_height()
        gap, mw_, mh_ = self._px(18), self._px(128), self._px(148)
        mx = ev.x + gap if ev.x + gap + mw_ < mw else ev.x - mw_ - gap
        my = ev.y + gap if ev.y + gap + mh_ < mh else ev.y - mh_ - gap
        mag.place(x=max(0, mx), y=max(0, my))
        tk.Misc.lift(mag)   # Canvas.lift 是 tag_raise，必须显式走控件层级

    def _nudge(self, dx: int, dy: int, ev) -> str:
        """方向键微移框选；Shift 加速。"""
        if self.box is None or self.frame is None:
            return "break"
        step = 10 if self._mods()[0] else 1
        x1, y1, x2, y2 = self.box
        w, h = x2 - x1, y2 - y1
        fh, fw = self.frame.shape[:2]
        nx1 = min(max(0, x1 + dx * step), fw - w)
        ny1 = min(max(0, y1 + dy * step), fh - h)
        self.box = (nx1, ny1, nx1 + w, ny1 + h)
        if self._dyn:
            self._dyn_box = self.box
            self.frames = []
        self._update_coord()
        self._redraw_box()
        self._preview_box()
        self._refresh_ui()
        return "break"

    # ================================================================ 瞄准绑定
    def _aim_down(self, _ev) -> None:
        try:
            self.aim.grab_set()
        except Exception:
            pass
        self._aiming = True
        self._aim_hwnd = 0
        try:
            self.aim.config(bg="#e9f1eb")
        except Exception:
            pass
        try:
            hl = tk.Toplevel(self.root)
            hl.overrideredirect(True)
            hl.attributes("-topmost", True)
            hl.attributes("-transparentcolor", "#ff00ff")
            # 先停到屏外：click-through 生效前若盖在光标下，
            # WindowFromPoint 会一直打中自己 → 永远 aim=0
            hl.geometry("1x1+-32000+-32000")
            cv = tk.Canvas(hl, bg="#ff00ff", highlightthickness=0)
            cv.pack(fill="both", expand=True)
            self._hl, self._hl_cv = hl, cv
            try:
                winapi.make_click_through(hl.winfo_id())
            except Exception:
                pass
        except Exception:
            self._hl = None
        self._track()

    @staticmethod
    def _capturable(h: int) -> bool:
        """这个句柄能不能截出画面：有真实客户区、窗口矩形不是一条缝。"""
        w, hh = winapi.client_size(h)
        if w <= 0 or hh <= 0:
            return False
        l, t, r, b = winapi.window_rect(h)
        return r - l > 4 and b - t > 4

    def _track(self) -> None:
        if not self._aiming:
            return
        try:
            x, y = winapi.cursor_pos()
            h = winapi.window_from_point(x, y)
            pid = os.getpid()
            seen = set()
            # Tk 控件全是真 HWND，自己进程的窗口按 pid 整体跳过；
            # 命中退化/辅助窗（客户区 0、一条缝）就沿父链爬到真正能截的那层
            while h and h not in seen and \
                    (winapi.pid_of(h) == pid or not self._capturable(h)):
                seen.add(h)
                h = winapi.parent_of(h)
            if h and h not in seen:
                self._aim_hwnd = h
                if self._hl is not None:
                    l, t, r, b = winapi.window_rect(h)
                    self._hl.geometry(f"{r - l}x{b - t}+{l}+{t}")
                    self._hl_cv.delete("all")
                    self._hl_cv.create_rectangle(2, 2, r - l - 2, b - t - 2,
                                                 outline=RED, width=4)
                w, hh = winapi.client_size(h)
                exe = os.path.basename(winapi.image_path(winapi.pid_of(h))) or "?"
                self.target_var.set(f"{winapi.title(h)[:20] or exe}   {w}×{hh}")
        except Exception as exc:  # noqa: BLE001
            self.status.set(f"瞄准出错：{exc}")
        self.root.after(40, self._track)

    def _aim_up(self, _ev) -> None:
        self._aiming = False
        try:
            self.aim.grab_release()
            self.aim.config(bg="#fbfbfa")
        except Exception:
            pass
        if self._hl is not None:
            try:
                self._hl.destroy()
            except Exception:
                pass
            self._hl = None
        if self._aim_hwnd:
            self._bind_hwnd(self._aim_hwnd)
        else:
            self.target_var.set("没指到窗口，再拖一次")

    def _bind_hwnd(self, h: int) -> None:
        if not h or winapi.pid_of(h) == os.getpid():
            return
        why = wincap.why_invisible(h)
        if why:
            self.status.set(f"绑定失败：{why}")
            return
        w, hh = winapi.client_size(h)
        if w <= 0 or hh <= 0:
            self.status.set("绑定失败：这个窗口没有可截的画面")
            return
        self.hwnd = h
        exe = os.path.basename(winapi.image_path(winapi.pid_of(h))) or "?"
        self.target_var.set(f"{winapi.title(h)[:20] or exe}   {w}×{hh}   hwnd={h}")
        self.status.set(f"已绑定 {exe}")
        self._check_window_fid()
        self.grab_once()
        self.live_var.set(True)
        self._live_sync()

    def unbind(self) -> None:
        """解除绑定：停直播/停动采，画面定格最后一帧，还能继续框选修图。"""
        if self.hwnd is None:
            return
        self._dyn_stop()
        self.live_var.set(False)
        self.hwnd = None
        self._aim_hwnd = 0
        self._live_sync()
        if self.frame is not None:
            # 动采监控视角会定格在选区小图上，解绑后恢复整窗视图方便重新框选
            self._show_src(self.frame)
        self.target_var.set("按住准星，拖到游戏窗口上松手")
        self.status.set("已解绑；画面定格在最后一帧")
        self._update_coord()
        self._refresh_ui()

    def pick_from_list(self) -> None:
        items = []
        pid = os.getpid()
        for h in winapi.enum_top_windows():
            if not (winapi.is_visible(h) and winapi.title(h)):
                continue
            if winapi.pid_of(h) == pid:
                continue
            w, hh = winapi.client_size(h)
            if w <= 0 or hh <= 0:
                continue
            exe = os.path.basename(winapi.image_path(winapi.pid_of(h))) or "?"
            items.append((h, f"{winapi.title(h)[:30]}  —  {exe}  {w}x{hh}"))
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("选窗口")
        dlg.geometry("520x420")
        dlg.transient(self.root)
        dlg.grab_set()
        scr = ScrollFrame(dlg)
        scr.pack(padx=10, pady=10, fill="both", expand=True)

        def choose(h: int) -> None:
            best = next((c for c in winapi.enum_children(h)
                         if winapi.client_size(c) == (800, 600)), h)
            dlg.destroy()
            self._bind_hwnd(best)

        for h, t in items:
            flat_btn(scr, t, lambda hh=h: choose(hh), anchor="w",
                     height=30).pack(fill="x", pady=1)

    # ================================================================ 截图/载入
    def _grab_frame(self, rect: tuple[int, int, int, int] | None = None,
                    prefer: str = "bitblt") -> np.ndarray:
        if self.hwnd is None:
            raise RuntimeError("先绑定窗口")
        cap = wincap.capture_rgb(self.hwnd, rect, prefer=prefer)
        if cap.get("covered") and prefer == "bitblt":
            # 窗口被上层窗口挡住：BitBlt 抓到的是遮挡物像素，改走 PrintWindow
            # 拿窗体自己的画面，免得遮挡物混进模板。
            cap = wincap.capture_rgb(self.hwnd, rect, prefer="printwindow")
        if not cap.get("ok") or cap.get("blank") or cap.get("covered"):
            raise RuntimeError(f"截不到画面：{cap.get('note') or '画面纯色'}")
        self._cap_note = cap.get("note") or ""
        # bytearray 直接 frombuffer：不再 bytes()+copy() 两遍 11.5MB 拷贝
        return np.frombuffer(cap["rgb"], np.uint8).reshape(cap["h"], cap["w"], 3)

    def grab_once(self) -> None:
        """抓一帧并停掉实时画面，定格在这一刻。"""
        self._dyn_stop()
        self.live_var.set(False)
        self._live_sync()
        try:
            self.frame = self._grab_frame()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("截图失败", str(exc))
            return
        self.frame_alpha = None
        self.frame_from_image = False
        self._check_window_fid()
        self._exit_edit(redraw=False)
        self._show_src(self.frame)
        if self._cap_note:
            self.status.set(self._cap_note)
        self._refresh_ui()

    def load_image(self) -> None:
        path = filedialog.askopenfilename(
            title="载入图片", filetypes=[("图片", "*.png;*.bmp"), ("全部", "*.*")])
        if not path:
            return
        self.live_var.set(False)
        self._live_sync()
        try:
            with Image.open(path) as im:
                has_alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
                rgba = np.array(im.convert("RGBA"), np.uint8)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("载入失败", str(exc))
            return
        self.frame = np.ascontiguousarray(rgba[:, :, :3])
        # 载入的是做好的透明模板：把它的透明度带进来，进修图后接着改而不是从头来
        self.frame_alpha = rgba[:, :, 3].copy() if has_alpha else None
        self.frame_from_image = True
        self.box = None
        self.coord_var.set("相对：—")
        self._set_fid((True, f"载入图片 {self.frame.shape[1]}×{self.frame.shape[0]}"
                             "（无法验证是否 100% 缩放，请确认它来自原始截图）"))
        self._exit_edit(redraw=False)
        self._show_src(self.frame)
        tail = "；自带透明度，框选后点「静态截图」接着修" if has_alpha else \
            "；框选后点「静态截图」进修图"
        self.status.set(f"已载入 {os.path.basename(path)}{tail}")
        self._refresh_ui()

    def save_fullshot(self) -> None:
        """整帧无损截图：把当前画面按原始像素 1:1 存成 PNG。
        绑了窗口就现场抓一帧（遮挡自动走 PrintWindow）；载入的图片就原样存回。"""
        if self.hwnd is not None and not self.frame_from_image:
            try:
                self.frame = self._grab_frame()
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("截图失败", str(exc))
                return
            self.frame_alpha = None
            self._check_window_fid()
            self._show_src(self.frame)
        if self.frame is None:
            messagebox.showwarning("没有画面", "先绑定窗口或载入图片。")
            return
        if (self.src_fid is not None and not self.src_fid[0]
                and not self.frame_from_image):
            if not messagebox.askyesno(
                    "画面可能不是原始像素",
                    f"{self.src_fid[1]}\n\n仍然保存吗？"):
                return
        path = filedialog.asksaveasfilename(
            title="保存整帧截图", defaultextension=".png",
            initialfile=f"cap_{time.strftime('%Y%m%d_%H%M%S')}.png",
            initialdir=save_dir(), filetypes=[("PNG", "*.png")])
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        f = self.frame
        meta = PngInfo()
        meta.add_text("mhxy.tool", f"maketpl {BUILD}")
        meta.add_text("mhxy.kind", "fullframe")
        meta.add_text("mhxy.size", f"{f.shape[1]}x{f.shape[0]}")
        if self.src_fid is not None:
            meta.add_text("mhxy.capture", self.src_fid[1])
        if self.hwnd is not None and not self.frame_from_image:
            w, h = winapi.client_size(self.hwnd)
            meta.add_text("mhxy.client", f"{w}x{h}")
            meta.add_text("mhxy.dpi", f"{winapi.window_dpi(self.hwnd)}/"
                                      f"{winapi.monitor_dpi(self.hwnd)}")
        Image.fromarray(f).save(path, pnginfo=meta, optimize=True)
        self.status.set(f"已存整帧 {os.path.basename(path)}"
                        f"（{f.shape[1]}×{f.shape[0]} 原尺寸）")
        self._refresh_ui()

    # ================================================================ 静态/动态截图
    def static_shot(self) -> None:
        """静态：框选后直接截这个区域一次，进修图；没绑窗口就用载入的图片。"""
        self._dyn_stop()
        if not self._need_box():
            return
        if self.frame is None:
            messagebox.showwarning("未绑定", "先绑定窗口或载入图片。")
            return
        # 所见即所得：用框选时看到的那一帧，不再重新抓一张。
        # 以前绑了窗口会重抓：暂停定格后 NPC 动了、玩家走进来，截下来的和框的不是一张图；
        # 载入了图片却还绑着窗口时，甚至会抓成窗口画面。
        self.single_frame()
        if self.editing and self._cap_note:
            self.status.set(self._cap_note)

    def dyn_shot(self) -> None:
        """动态：实时盯框选区域，稳定像素留下、噪点自动去掉；再点一次停止。"""
        if self._dyn:
            self._dyn_stop(finish=True)
            return
        if self.hwnd is None:
            messagebox.showwarning("未绑定", "先绑定窗口。")
            return
        if not self._need_box():
            return
        self._dyn = True
        self._dyn_paused = False
        self._dyn_box = self.box
        self._dyn_tol = self.tol_var.get()
        self._dyn_agree = self.agree_var.get()
        self._dyn_next_compute = 0.0
        self.frames = []
        self._live_sync()
        self.status.set("实时去噪中… 可「暂停」等画面，满意了再点一次生成")
        self._refresh_ui()

    def dyn_pause(self) -> None:
        """动态截图中途暂停/继续采帧；暂停时左侧画面照常直播。"""
        if not self._dyn:
            return
        self._dyn_paused = not self._dyn_paused
        self.frames_var.set(f"已暂停（{len(self.frames)} 帧）"
                            if self._dyn_paused else "")
        self._refresh_ui()
        self.status.set("已暂停采帧（画面还在直播），再点「继续」接着采"
                        if self._dyn_paused else "继续采帧中…")

    @staticmethod
    def _agree_count_rule(rule: str, n: int) -> int | None:
        """纯函数版 _agree_count，工作线程也能安全调（不碰 tk 变量）。"""
        val = dict(AGREE_OPTS).get(rule)
        if val is None:
            return None
        return n if val == "N" else n - int(val[2])

    def _dyn_stop(self, finish: bool = False) -> None:
        if not self._dyn:
            return
        self._dyn = False
        self._dyn_paused = False
        if finish:
            self.status.set("已生成，修一下或直接保存")
        self._live_sync()
        self._refresh_ui()

    # ================================================================ 实时画面
    def _on_live_toggle(self) -> None:
        on = self.live_var.get()
        if on and self.hwnd is None:
            self.live_var.set(False)
            self.status.set("先绑定窗口，实时画面才有东西播")
            return
        if on:
            self.frame_from_image = False   # 直播开了，画面换回窗口的
            self._check_window_fid()
        self._live_sync()
        if on:
            self.status.set("实时画面中，关掉「实时画面」开关即可暂停")
        else:
            self.status.set("已暂停：画面定格在最后一帧，可以慢慢框选")

    def _live_sync(self) -> None:
        """按当前状态决定要不要跑直播线程：显示要（开关开着）或动采要。"""
        self._live_show = bool(self.live_var.get())
        want = bool((self._live_show or self._dyn) and self.hwnd is not None)
        if want == self._live_on:
            return
        self._live_gen += 1
        self._live_on = want
        self._live_stop.set()
        if not want:
            return
        self._live_stop.clear()
        self._live_gap = self._int(self.gap_var, 50, 2000, 300) / 1000
        threading.Thread(target=self._live_loop, args=(self._live_gen,),
                         daemon=True).start()

    def _live_loop(self, gen: int) -> None:
        fails = 0
        while self._live_on and gen == self._live_gen and self.hwnd is not None:
            # 动采只盯选区：只截那块，省得每帧抓整个窗口
            rect = self._dyn_box if self._dyn else None
            try:
                f = self._grab_frame(rect)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                if fails >= 3:
                    self._post(self._live_fail, exc)
                    return
            else:
                fails = 0
                disp = (self._disp_view(f)
                        if self._live_show or self._dyn else None)
                # 动采的攒帧/中位数/掩码也在工作线程算，UI 只负责贴结果
                edit = None
                n = len(self.frames)
                if (self._dyn and not self._dyn_paused and rect is not None
                        and rect == tuple(self._dyn_box)):
                    ew, eh = rect[2] - rect[0], rect[3] - rect[1]
                    if f.shape[:2] != (eh, ew):
                        self._post(self._dyn_bad_size)
                        return
                    self.frames.append(f)
                    keep = max(8, min(60, 4_000_000
                                      // max(1, f.shape[0] * f.shape[1])))
                    if len(self.frames) > keep:
                        self.frames = self.frames[-keep:]
                    n = len(self.frames)
                    if n >= 2 and time.monotonic() >= self._dyn_next_compute:
                        # 掩码每 ~0.6s 刷一次就够，帧照样全收
                        self._dyn_next_compute = time.monotonic() + 0.6
                        mc = self._agree_count_rule(self._dyn_agree, n)
                        mc = max(1, n - 1 if mc is None else mc)
                        # 整数值上下界比较：|a-med|<=tol 等价 ceil(med-tol)<=a<=floor(med+tol)，
                        # 省掉 int64 差分+绝对值那几百 MB 的临时数组
                        arr = np.stack(self.frames)
                        med = np.median(arr, axis=0)
                        lo = np.ceil(med - self._dyn_tol)
                        hi = np.floor(med + self._dyn_tol)
                        mask = ((arr >= lo) & (arr <= hi)
                                ).all(axis=3).sum(axis=0) >= mc
                        edit = (med.astype(np.uint8), mask)
                self._post(self._live_apply, f, disp, rect, n, edit)
            if self._live_stop.wait(self._live_gap):
                return

    def _dyn_bad_size(self) -> None:
        self.status.set("窗口尺寸变了，动态截图已停")
        self._dyn_stop()

    def _disp_view(self, f: np.ndarray,
                   wh: tuple[int, int] | None = None) -> np.ndarray:
        """给画布用的抽稀小图：整步长取样，UI 端就不用每帧缩放大图了。"""
        aw, ah = wh or self._src_disp_wh
        h, w = f.shape[:2]
        s = max(1, int(max(h / ah, w / aw)))
        if s <= 1:
            return f
        return np.ascontiguousarray(f[::s, ::s])

    def _live_apply(self, f: np.ndarray, disp: np.ndarray | None,
                    rect: tuple | None = None, dyn_n: int = 0,
                    dyn_edit: tuple | None = None) -> None:
        self._live_gap = self._int(self.gap_var, 50, 2000, 300) / 1000
        aw, ah = self._canvas_size(self.src)
        self._src_disp_wh = (aw, ah)
        # 只认抓当前选区的帧：动采启动/拖框前后在飞的整窗帧、旧选区帧都按整帧显示/丢弃
        region = bool(self._dyn and self._dyn_box is not None
                      and rect is not None and rect == tuple(self._dyn_box))
        if disp is not None and self._drag_start is None:
            if region:
                # 动采监控视角：f 就是选区本身，铺满画布；
                # self.frame 保持整窗原图，框选/取色坐标不串位。
                # 动采监控必须动，「实时画面」开关只管整窗直播、管不到这里
                self._src_img = f
                self._view_off = (self._dyn_box[0], self._dyn_box[1])
                self._render_src(disp=disp)
                self.src.delete("hit")
                self.src.delete("ph")
                self._redraw_box()
            elif self._live_show:
                self.frame = f
                self.frame_alpha = None
                if self.box is not None:
                    fh, fw = f.shape[:2]
                    if self.box[2] > fw or self.box[3] > fh:
                        self.box = None
                        self._view = None
                        self.coord_var.set("相对：—")
                        self.prev.delete("img")
                        self._placeholder(self.prev, "窗口尺寸变了，重新框选")
                        self._refresh_ui()
                self._show_src(disp, (f.shape[1], f.shape[0]))
                if self.box is not None:
                    self._preview_box()
        if region:
            self.frames_var.set(f"实时 {dyn_n} 帧")
            if dyn_edit is not None:
                base, mask = dyn_edit
                if mask.any():
                    origin = (self._dyn_box[0], self._dyn_box[1])
                    if not self.editing or self.base.shape != base.shape:
                        self._enter_edit(base, mask, origin=origin)
                    else:
                        self.base, self.mask = base, mask
                        self.base_origin = origin
                        self.undo = []
                        self._render_edit()
        normal = "实时画面中，关掉「实时画面」开关即可暂停"
        if self._dyn:
            normal = "已暂停采帧（画面还在直播）" if self._dyn_paused \
                else "实时去噪中… 满意了再点「停止并生成」"
        elif not self._live_show:
            normal = "实时画面已暂停"
        self._cap_warn_status(normal)

    def _cap_warn_status(self, normal: str) -> None:
        """状态栏优先显示截图警告（被挡住等），警告没了就回到正常文案。"""
        self.status.set(self._cap_note or normal)

    def _live_fail(self, exc) -> None:
        self.live_var.set(False)
        self._live_sync()
        self.status.set(f"实时画面断了：{exc}（可重新打开开关）")

    def _canvas_size(self, canvas: tk.Canvas) -> tuple[int, int]:
        """画布可用尺寸；布局尚未完成时退回创建时配置的尺寸。"""
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 8 or h < 8:
            w, h = int(canvas.cget("width")), int(canvas.cget("height"))
        return max(w, 8), max(h, 8)

    def _put_image(self, canvas: tk.Canvas, key: str, arr: np.ndarray,
                   upscale: bool) -> float:
        """把图等比缩放后居中画进画布；画布尺寸固定，不随图片变化而改，避免布局跳动。"""
        h, w = arr.shape[:2]
        aw, ah = self._canvas_size(canvas)
        scale = min(aw / w, ah / h)
        scale = min(scale, 8.0) if upscale else min(scale, 1.0)
        dw, dh = max(1, int(w * scale)), max(1, int(h * scale))
        img = Image.fromarray(arr[:, :, :3])
        if (dw, dh) != (w, h):
            # 缩小用 LANCZOS（柔和不锯齿），放大用 NEAREST（逐像素不糊）
            res = Image.NEAREST if scale >= 1 else Image.LANCZOS
            img = img.resize((dw, dh), res)
        photo = ImageTk.PhotoImage(img)
        self._photos[key] = photo
        canvas.delete("img")
        canvas.create_image((aw - dw) // 2, (ah - dh) // 2,
                            anchor="nw", image=photo, tags="img")
        canvas.tag_lower("img")
        return scale

    def _on_canvas_resize(self, ev) -> None:
        if ev.width < 8 or ev.height < 8:
            return
        if self._resize_job is not None:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.root.after(80, self._redraw_canvases)

    def _redraw_canvases(self) -> None:
        self._resize_job = None
        if self.frame is not None:
            self._show_src(self.frame)
        elif self.src.find_withtag("img") == ():
            self._placeholder(self.src, "点「截取画面」或「载入图片」\n开始制作模板")
        if self.editing:
            self._render_edit()
        elif self.frame is not None and self.box is not None:
            self._preview_box()
        elif self.prev.find_withtag("img") == () and self.base is None:
            self._placeholder(self.prev, "框选左侧画面后\n这里实时预览")

    def _show_src(self, arr: np.ndarray,
                  full_wh: tuple[int, int] | None = None) -> None:
        """显示图；full_wh 传全分辨率 (w,h) 时 arr 是它的抽稀小图。"""
        # 整图显示：取色/放大镜的底图就是它，客户区坐标没有偏移
        self._src_img = self.frame if full_wh is not None else arr
        self._view_off = (0, 0)
        self.src.delete("hit")
        self.src.delete("ph")
        self._render_src(disp=arr if full_wh is not None else None)
        self._redraw_box()

    def _sfit_scale(self) -> float:
        """源画面适应画布的缩放（历来只缩不放大：小图就 1:1 显示）。"""
        if self._src_img is None:
            return 1.0
        aw, ah = self._canvas_size(self.src)
        h, w = self._src_img.shape[:2]
        return min(aw / w, ah / h, 1.0)

    def _szoom_scale(self) -> float:
        if self.szoom <= 0:
            return self._sfit_scale()
        return max(0.05, min(float(self.szoom), 64.0))

    def _szoom_center(self) -> tuple[float, float]:
        h, w = self._src_img.shape[:2]
        aw, ah = self._canvas_size(self.src)
        s = self._szoom_scale()
        cx, cy = self.scenter if self.scenter else (w / 2, h / 2)
        if w * s <= aw:
            cx = w / 2
        else:
            cx = min(max(cx, aw / (2 * s)), w - aw / (2 * s))
        if h * s <= ah:
            cy = h / 2
        else:
            cy = min(max(cy, ah / (2 * s)), h - ah / (2 * s))
        self.scenter = (cx, cy)
        return cx, cy

    def _render_src(self, disp: np.ndarray | None = None) -> None:
        """源画布渲染。

        适应模式：抽稀小图 + LANCZOS 收尾（不锯齿）。
        放大模式：原图视口裁剪 + NEAREST 放大，100% 即逐像素原图，≥4 倍画网格。
        """
        img = self._src_img
        if img is None:
            return
        aw, ah = self._canvas_size(self.src)
        h, w = img.shape[:2]
        if self.szoom <= 0:
            arr = disp if disp is not None else img
            s = self._put_image(self.src, "src", arr, upscale=False)
            self.sscale = s * arr.shape[1] / w
            dw, dh = arr.shape[1] * s, arr.shape[0] * s
            self._src_origin = (max(0.0, (aw - dw) / 2),
                                max(0.0, (ah - dh) / 2))
            self.src.delete("grid")
        else:
            s = self._szoom_scale()
            cx, cy = self._szoom_center()
            ox, oy = aw / 2 - cx * s, ah / 2 - cy * s
            ix0 = max(0, int(np.floor(-ox / s)))
            iy0 = max(0, int(np.floor(-oy / s)))
            ix1 = min(w, int(np.ceil((aw - ox) / s)))
            iy1 = min(h, int(np.ceil((ah - oy) / s)))
            crop = img[iy0:iy1, ix0:ix1]
            if crop.size == 0:
                return
            dw = max(1, int(round(crop.shape[1] * s)))
            dh = max(1, int(round(crop.shape[0] * s)))
            im = Image.fromarray(crop[:, :, :3])
            if (dw, dh) != (crop.shape[1], crop.shape[0]):
                im = im.resize((dw, dh),
                               Image.NEAREST if s >= 1 else Image.LANCZOS)
            photo = ImageTk.PhotoImage(im)
            self._photos["src"] = photo
            self.src.delete("img")
            self.src.create_image(int(round(ox + ix0 * s)),
                                  int(round(oy + iy0 * s)),
                                  anchor="nw", image=photo, tags="img")
            self.src.tag_lower("img")
            self.sscale = s
            self._src_origin = (ox, oy)
            self.src.delete("grid")
            if s >= 4:
                gy0 = max(0, int(round(oy)))
                gy1 = min(ah, int(round(oy + h * s)))
                gx0 = max(0, int(round(ox)))
                gx1 = min(aw, int(round(ox + w * s)))
                for gx in range(ix0, ix1 + 1):
                    X = int(round(ox + gx * s))
                    self.src.create_line(X, gy0, X, gy1,
                                         fill="#d9d9d6", tags="grid")
                for gy in range(iy0, iy1 + 1):
                    Y = int(round(oy + gy * s))
                    self.src.create_line(gx0, Y, gx1, Y,
                                         fill="#d9d9d6", tags="grid")
        pct = self.sscale * 100
        self.szoom_var.set(f"{w}×{h} · {pct:.0f}%" if self.szoom > 0
                           else f"{w}×{h} · 适应{pct:.0f}%")
        if not self.src_chip.winfo_manager():
            self.src_chip.place(relx=1.0, x=-8, y=8, anchor="ne")

    def _swheel(self, ev) -> str | None:
        """Ctrl+滚轮 = 缩放画面；不按 Ctrl 留给右栏面板滚动。"""
        if not self._mods()[1]:
            return None
        if self._src_img is not None:
            self._szoom_by(1.3 if ev.delta > 0 else 1 / 1.3, (ev.x, ev.y))
        return "break"

    def _szoom_by(self, factor: float,
                  anchor: tuple[float, float] | None = None) -> None:
        if self._src_img is None:
            return
        aw, ah = self._canvas_size(self.src)
        s0 = self._szoom_scale()
        cx, cy = self._szoom_center()
        ax, ay = anchor if anchor is not None else (aw / 2, ah / 2)
        ix = cx + (ax - aw / 2) / s0
        iy = cy + (ay - ah / 2) / s0
        s1 = max(0.05, min(s0 * factor, 64.0))
        if abs(s1 - s0) < 1e-6:
            return
        if s1 <= self._sfit_scale():
            # 缩到比适应还小没有内容可看了，直接回适应态
            self.szoom = 0.0
            self.scenter = None
        else:
            self.szoom = s1
            self.scenter = (ix - (ax - aw / 2) / s1,
                            iy - (ay - ah / 2) / s1)
        self._render_src()
        self._redraw_box()

    def _szoom_fit(self) -> None:
        self.szoom = 0.0
        self.scenter = None
        self._render_src()
        self._redraw_box()

    def _img_origin(self, canvas: tk.Canvas, img_wh: tuple[int, int]) -> tuple[float, float]:
        """图像原点对应的画布坐标；src 放大后可平移，直接用渲染时存下的原点。"""
        if canvas is self.src:
            return self._src_origin
        aw, ah = self._canvas_size(canvas)
        dw = min(img_wh[0] * self.escale, aw)
        dh = min(img_wh[1] * self.escale, ah)
        return max(0, (aw - dw) / 2), max(0, (ah - dh) / 2)

    def _to_img(self, canvas: tk.Canvas, x: float, y: float) -> tuple[int, int]:
        if canvas is self.prev and self.editing:
            aw, ah = self._canvas_size(canvas)
            s = self._zoom_scale()
            cx, cy = self._zoom_center()
            return int((x - aw / 2) / s + cx), int((y - ah / 2) / s + cy)
        s = self.escale if canvas is self.prev else self.sscale
        img = self.base if canvas is self.prev else self._src_img
        ox, oy = 0.0, 0.0
        if img is not None:
            ox, oy = self._img_origin(canvas, (img.shape[1], img.shape[0]))
        return int((x - ox) / s), int((y - oy) / s)

    def _to_cv(self, canvas: tk.Canvas, ix: float, iy: float) -> tuple[float, float]:
        """图像坐标 → 画布坐标（居中偏移 + 缩放），测试和定位用。"""
        if canvas is self.prev and self.editing:
            aw, ah = self._canvas_size(canvas)
            s = self._zoom_scale()
            cx, cy = self._zoom_center()
            return aw / 2 + (ix - cx) * s, ah / 2 + (iy - cy) * s
        s = self.escale if canvas is self.prev else self.sscale
        img = self.base if canvas is self.prev else self._src_img
        ox = oy = 0.0
        if img is not None:
            ox, oy = self._img_origin(canvas, (img.shape[1], img.shape[0]))
        if canvas is self.src:
            ix -= self._view_off[0]
            iy -= self._view_off[1]
        return ox + ix * s, oy + iy * s

    # ================================================================ 画布交互
    @staticmethod
    def _mods() -> tuple[bool, bool, bool]:
        """真实修饰键 (shift, ctrl, alt)。
        Windows 的 Tk 事件 state 会虚报 Mod1(0x0008)：普通单击都带这 bit，
        按 st & 0x0008 判 Alt 会把每次点击当成「Alt 减选」，魔术棒永远选空。
        只能问 OS 要真实键态。"""
        u = winapi.user32
        return (u.GetAsyncKeyState(0x10) < 0,    # VK_SHIFT
                u.GetAsyncKeyState(0x11) < 0,    # VK_CONTROL
                u.GetAsyncKeyState(0x12) < 0)    # VK_MENU (Alt)

    def _press(self, ev) -> None:
        if ev.widget is self.prev:
            if self.editing and not self._crop_armed:
                if self._brush_mode is not None:
                    self._brush_apply(ev.x, ev.y,
                                      keep=self._brush_mode == "paint",
                                      first=True)
                else:
                    # 先不选：松手才算点选，移动超阈值就改平移（放大后按住拖图）
                    self._wand_pending = (ev.x, ev.y)
                return
            if not self.editing:
                if self.frame is not None and self.box is not None:
                    if self.hwnd is not None:
                        self.static_shot()
                    else:
                        self.single_frame()
                else:
                    self.status.set("先框选左侧画面，再点这里开始修图")
                return
        self._drag_start = (ev.x, ev.y, ev.widget)
        ev.widget.delete("sel")

    def _drag_move(self, ev) -> None:
        if self.editing and ev.widget is self.prev:
            if self._brush_mode is not None:
                self._brush_apply(ev.x, ev.y, keep=self._brush_mode == "paint")
                return
            if self._wand_pending is not None:
                x0, y0 = self._wand_pending
                if abs(ev.x - x0) + abs(ev.y - y0) <= 5:
                    return
                self._wand_pending = None
                cx, cy = self._zoom_center()
                self._pan_start = (ev.x, ev.y, cx, cy)
                self._pan_cv = self.prev
                self.prev.config(cursor="fleur")
                self._pan_move(ev)   # 第一次移动就直接平移，别等下一个 motion
                return
            if self._pan_start is not None:
                self._pan_move(ev)
                return
        if self._drag_start is None or ev.widget is not self._drag_start[2]:
            return
        ev.widget.delete("sel")
        ev.widget.create_rectangle(self._drag_start[0], self._drag_start[1], ev.x, ev.y,
                                   outline="#e8a33d", width=2, tags="sel")

    def _release(self, ev) -> None:
        if self._wand_pending is not None:
            x, y = self._wand_pending
            self._wand_pending = None
            shift, _ctrl, alt = self._mods()
            self._wand(x, y, add=shift, sub=alt)
            return
        if self._pan_start is not None and self._pan_cv is self.prev:
            self._pan_release(ev)
            return
        if self._drag_start is None:
            return
        canvas = self._drag_start[2]
        x1, y1 = self._to_img(canvas, *self._drag_start[:2])
        x2, y2 = self._to_img(canvas, ev.x, ev.y)
        self._drag_start = None
        if self.editing and canvas is self.prev:
            if self._crop_armed:
                self._crop_armed = False
                self.prev.config(cursor="crosshair")
                self._crop_to(x1, y1, x2, y2)
            return
        if canvas is not self.src or self.frame is None:
            return
        # 显示图坐标 → 客户区坐标（动采只显示选区时有偏移）
        x1 += self._view_off[0]
        x2 += self._view_off[0]
        y1 += self._view_off[1]
        y2 += self._view_off[1]
        fh, fw = self.frame.shape[:2]
        x1, x2 = sorted((max(0, x1), min(fw, x2)))
        y1, y2 = sorted((max(0, y1), min(fh, y2)))
        if x2 - x1 < 4 or y2 - y1 < 4:
            self.src.delete("sel")
            if self.editing:
                # 编辑态点画面 = 魔术棒（点颜色选一片），和点右边预览一样
                shift, _ctrl, alt = self._mods()
                self._wand_at_client(x1, y1, add=shift, sub=alt)
            else:
                self._pick_color(min(fw - 1, max(0, x1)), min(fh - 1, max(0, y1)))
            return
        self.box = (x1, y1, x2, y2)
        if self._dyn:
            self._dyn_box = self.box
            self.frames = []
        self._update_coord()
        self._redraw_box()
        self._preview_box()
        self._refresh_ui()

    def _hover(self, ev) -> None:
        canvas = ev.widget
        if canvas is self.prev:
            self._draw_brush_ghost(ev.x, ev.y)
            img = self._view if self._view is not None else self.base
        else:
            img = self._src_img
        if img is None:
            return
        # 按住键拖动（框选/裁剪/平移/画笔涂抹）和画笔/裁剪模式下不弹放大镜：
        # 放大窗跟着光标跑，看着像"一操作就自动放大"，还挡画面。
        # 只有空着手 hover（取色/对准魔术棒）才出。
        if (ev.state & 0x0700) or self._brush_mode is not None \
                or (self._crop_armed and canvas is self.prev):
            self.hover_var.set("")
            self._show_mag_off(canvas)
            return
        ix, iy = self._to_img(canvas, ev.x, ev.y)
        h, w = img.shape[:2]
        if not (0 <= iy < h and 0 <= ix < w):
            self.hover_var.set("")
            self._show_mag_off(canvas)
            return
        r, g, b = (int(v) for v in img[iy, ix, :3])
        lx = ix + self._view_off[0] if canvas is self.src else ix
        ly = iy + self._view_off[1] if canvas is self.src else iy
        extra = f" {'保留' if self.mask[iy, ix] else '透明'}" \
            if canvas is self.prev and self.editing else ""
        self.hover_var.set(f"({lx},{ly})  RGB({r},{g},{b}){extra}")
        self._show_mag(canvas, ev, ix, iy, img)

    def _show_mag_off(self, canvas: tk.Canvas) -> None:
        m = self._mags.get(canvas)
        if m is not None:
            m.place_forget()

    def _update_coord(self) -> None:
        if self.box is None:
            self.coord_var.set("相对：—")
            return
        x1, y1, x2, y2 = self.box
        screen = not self.rel_var.get() and self.hwnd is not None
        if screen:
            ox, oy = winapi.client_origin_on_screen(self.hwnd)
            x1, x2, y1, y2 = x1 + ox, x2 + ox, y1 + oy, y2 + oy
        tag = "屏幕" if screen else "相对"
        self.coord_var.set(f"{tag}：{x1}, {y1}, {x2}, {y2} ({x2 - x1}, {y2 - y1})")

    def _redraw_box(self) -> None:
        self.src.delete("sel")
        if self.box is not None and self._src_img is not None:
            x1, y1 = self._to_cv(self.src, self.box[0], self.box[1])
            x2, y2 = self._to_cv(self.src, self.box[2], self.box[3])
            self.src.create_rectangle(x1, y1, x2, y2,
                                      outline="#e8a33d", width=2, tags="sel")

    # ================================================================ 取色
    def _pick_color(self, x: int, y: int) -> None:
        """x,y 是客户区坐标；显示图是选区时先换算回显示图坐标再读像素。"""
        img = self._src_img if self._src_img is not None else self.frame
        vx, vy = x - self._view_off[0], y - self._view_off[1]
        if img is not None and 0 <= vy < img.shape[0] and 0 <= vx < img.shape[1]:
            rgb = img[vy, vx, :3].copy()
        else:
            rgb = self.frame[y, x, :3].copy()
        self.picked = (x, y, rgb)
        self.status.set(f"取色 ({x},{y}) = {colors.format_desc(rgb)}"
                        f"  RGB({int(rgb[0])},{int(rgb[1])},{int(rgb[2])})")

    def _preview_box(self) -> None:
        """框选后立刻把所选区域显示到预览画布（还不是模板，只确认范围）。"""
        if self.editing or self.frame is None or self.box is None:
            return
        x1, y1, x2, y2 = self.box
        view = self.frame[y1:y2, x1:x2]
        self._view = view   # 悬停取色要用原图，_view 保持全分辨率
        self.prev.delete("ph")
        # 大选区别把整张原图喂给 PIL：先抽稀到画布量级，escale 换算回原图坐标
        disp = self._disp_view(view, self._canvas_size(self.prev))
        s = self._put_image(self.prev, "box", disp, upscale=True)
        self.escale = s * disp.shape[1] / view.shape[1]
        self.prev.config(cursor="hand2")
        self.info_var.set(f"已框选 {x2 - x1}×{y2 - y1}，点这里或「静态截图」进修图")

    # ================================================================ 采帧
    def _need_box(self) -> bool:
        if self.box is None:
            messagebox.showwarning("先框选", "先在左边画面上框选要抠的区域。")
            return False
        return True

    def _agree_count(self, n: int) -> int | None:
        return self._agree_count_rule(self.agree_var.get(), n)

    def _int(self, var: tk.StringVar, lo: int, hi: int, default: int) -> int:
        try:
            return max(lo, min(hi, int(var.get())))
        except (TypeError, ValueError):
            return default

    def _burst_run(self, vary: bool) -> None:
        self._dyn_stop()
        if self.hwnd is None:
            messagebox.showwarning("未绑定", "先绑定窗口。")
            return
        if not self._need_box():
            return
        n = self._int(self.count_var, 2, 60, 8)
        gap = self._int(self.gap_var, 50, 2000, 250) / 1000.0
        x1, y1, x2, y2 = self.box
        self.status.set(f"连拍中… 0/{n}")

        def runner():
            got = []
            try:
                for i in range(n):
                    f = self._grab_frame()
                    if f.shape[0] < y2 or f.shape[1] < x2:
                        raise RuntimeError("窗口尺寸变了，连拍作废")
                    got.append(f[y1:y2, x1:x2].copy())
                    self._post(self.status.set, f"连拍中… {i + 1}/{n}")
                    if i + 1 < n:
                        threading.Event().wait(gap)
            except Exception as exc:  # noqa: BLE001
                self._post(self._burst_failed, exc)
            else:
                self._post(self._burst_done, got, vary)

        threading.Thread(target=runner, daemon=True).start()

    def burst(self) -> None:
        self._burst_run(vary=False)

    def burst_vary(self) -> None:
        self._burst_run(vary=True)

    def _burst_failed(self, exc) -> None:
        self.status.set("连拍失败")
        messagebox.showerror("连拍失败", str(exc))

    def _burst_done(self, got: list[np.ndarray], vary: bool) -> None:
        self.frames = got
        self.status.set("连拍完成")
        self.frames_var.set(f"已采 {len(got)} 帧（{got[0].shape[1]}×{got[0].shape[0]}）")
        try:
            fn = core.vary_mask if vary else core.stable_mask
            mask = fn(got, tol=self.tol_var.get(), min_count=self._agree_count(len(got)))
            base = np.median(np.stack(got), axis=0).astype(np.uint8)
            if not mask.any():
                raise ValueError("一个像素都没留下（画面完全没变？把『多帧一致』放宽一点）")
        except ValueError as exc:
            messagebox.showwarning("求稳失败", str(exc))
            return
        self._enter_edit(base, mask)
        self.status.set("已生成：点预览里的颜色选中保留区（魔术棒），Shift+点加选")

    def load_folder(self) -> None:
        folder = filedialog.askdirectory(title="选帧文件夹（按文件名排序取全部 png/bmp）")
        if not folder:
            return
        files = sorted(glob.glob(os.path.join(folder, "*.png"))
                       + glob.glob(os.path.join(folder, "*.bmp")))
        if len(files) < 2:
            messagebox.showwarning("帧太少", f"{folder} 里只有 {len(files)} 张图，至少 2 张。")
            return
        got = []
        for p in files:
            arr = np.array(Image.open(p).convert("RGB"), np.uint8)
            if self.box is not None and self.frame is not None \
                    and arr.shape[:2] == self.frame.shape[:2]:
                x1, y1, x2, y2 = self.box
                arr = arr[y1:y2, x1:x2]
            got.append(arr)
        try:
            mask = core.stable_mask(got, tol=self.tol_var.get(),
                                    min_count=self._agree_count(len(got)))
            base = np.median(np.stack(got), axis=0).astype(np.uint8)
            if not mask.any():
                raise ValueError("一个像素都没留下")
        except ValueError as exc:
            messagebox.showwarning("求稳失败", str(exc))
            return
        self.frames = got
        self.frames_var.set(f"已载入 {len(got)} 帧（{got[0].shape[1]}×{got[0].shape[0]}）")
        self._enter_edit(base, mask)
        self.status.set("已载入帧：点预览里的颜色选中保留区（魔术棒），Shift+点加选")

    def single_frame(self) -> None:
        self._dyn_stop()
        if self.frame is None:
            messagebox.showwarning("没有画面", "先截一张或载入图片。")
            return
        if not self._need_box():
            return
        x1, y1, x2, y2 = self.box
        fh, fw = self.frame.shape[:2]
        if x2 > fw or y2 > fh:
            messagebox.showwarning("框选超出画面", "窗口尺寸变了，请重新框选。")
            return
        base = self.frame[y1:y2, x1:x2].copy()
        mask = np.ones(base.shape[:2], bool)
        if self.frame_alpha is not None and self.frame_alpha.shape == self.frame.shape[:2]:
            kept = self.frame_alpha[y1:y2, x1:x2] >= 128
            if kept.any():
                mask = kept
        self.frames = [base]
        self._enter_edit(base, mask, origin=(x1, y1))
        self.status.set("已进修图：点预览里的颜色选中保留区（魔术棒），Shift+点加选")

    # ================================================================ 编辑态
    def _enter_edit(self, base: np.ndarray, mask: np.ndarray,
                    origin: tuple[int, int] | None = None) -> None:
        self._live_sync()
        self.base, self.mask = base, mask
        self.base_origin = origin
        self.sel = np.zeros_like(mask)
        self.undo = []
        self._brush_off()
        self.zoom = 0.0
        self.vcenter = None
        self.zoom_bar.place(relx=1.0, x=-10, y=10, anchor="ne")
        self.prev.config(cursor="tcross")
        self._render_edit()
        self._reveal_preview()
        # 所有进修图入口（静态/动态/载入）都要解锁修图按钮，不能只靠调用方刷新
        self._refresh_ui()

    def _exit_edit(self, redraw: bool = True) -> None:
        self.base = self.mask = self.sel = None
        self._view = None
        self.undo = []
        self._crop_armed = False
        self._brush_off()
        self.zoom = 0.0
        self.vcenter = None
        self.zoom_bar.place_forget()
        self.wand_chip.place_forget()
        self.prev.config(cursor="crosshair")
        self.prev.delete("img")
        self.prev.delete("grid")
        self.prev.delete("selout")
        if redraw and self.frame is not None:
            self._show_src(self.frame)
        if self.frame is not None and self.box is not None:
            self._preview_box()
        else:
            self.prev.delete("img")
            self._placeholder(self.prev, "框选左侧画面后\n这里实时预览")
        self._live_sync()
        self._refresh_ui()

    def exit_edit(self) -> None:
        self._exit_edit()

    # ---------------------------------------------------------------- 缩放/平移
    def _fit_scale(self) -> float:
        aw, ah = self._canvas_size(self.prev)
        h, w = self.mask.shape
        return min(aw / w, ah / h)

    def _zoom_scale(self) -> float:
        fit = self._fit_scale()
        if self.zoom <= 0:
            return fit
        return max(0.05, min(float(self.zoom), 64.0))

    def _zoom_center(self) -> tuple[float, float]:
        h, w = self.mask.shape
        aw, ah = self._canvas_size(self.prev)
        s = self._zoom_scale()
        cx, cy = self.vcenter if self.vcenter else (w / 2, h / 2)
        if w * s <= aw:
            cx = w / 2
        else:
            cx = min(max(cx, aw / (2 * s)), w - aw / (2 * s))
        if h * s <= ah:
            cy = h / 2
        else:
            cy = min(max(cy, ah / (2 * s)), h - ah / (2 * s))
        self.vcenter = (cx, cy)
        return cx, cy

    def _edit_geometry(self) -> tuple[float, float, float, float, float,
                                      int, int, int, int]:
        """返回 (scale, cx, cy, ox, oy, ix0, iy0, ix1, iy1)；ox/oy 是图 (0,0) 的画布坐标。"""
        aw, ah = self._canvas_size(self.prev)
        h, w = self.mask.shape
        s = self._zoom_scale()
        cx, cy = self._zoom_center()
        ox, oy = aw / 2 - cx * s, ah / 2 - cy * s
        ix0 = max(0, int(np.floor(-ox / s)))
        iy0 = max(0, int(np.floor(-oy / s)))
        ix1 = min(w, int(np.ceil((aw - ox) / s)))
        iy1 = min(h, int(np.ceil((ah - oy) / s)))
        return s, cx, cy, ox, oy, ix0, iy0, ix1, iy1

    def _zoom_by(self, factor: float, anchor: tuple[float, float] | None = None) -> None:
        if not self.editing:
            return
        aw, ah = self._canvas_size(self.prev)
        s0 = self._zoom_scale()
        cx, cy = self._zoom_center()
        ax, ay = anchor if anchor is not None else (aw / 2, ah / 2)
        ix = cx + (ax - aw / 2) / s0
        iy = cy + (ay - ah / 2) / s0
        s1 = max(0.05, min(s0 * factor, 64.0))
        if abs(s1 - s0) < 1e-6:
            return
        self.zoom = s1
        self.vcenter = (ix - (ax - aw / 2) / s1, iy - (ay - ah / 2) / s1)
        self._render_edit()

    def _zoom_fit(self) -> None:
        if not self.editing:
            return
        self.zoom = 0.0
        self.vcenter = None
        self._render_edit()

    def _wheel_zoom(self, ev) -> str:
        if self.editing:
            self._zoom_by(1.3 if ev.delta > 0 else 1 / 1.3, (ev.x, ev.y))
        return "break"

    def _pan_press(self, ev) -> None:
        if ev.widget is self.prev:
            if not self.editing:
                return
            cx, cy = self._zoom_center()
        elif ev.widget is self.src:
            if self._src_img is None:
                return
            cx, cy = self._szoom_center()
        else:
            return
        self._pan_start = (ev.x, ev.y, cx, cy)
        self._pan_cv = ev.widget
        ev.widget.config(cursor="fleur")

    def _pan_move(self, ev) -> None:
        if self._pan_start is None:
            return
        x0, y0, cx, cy = self._pan_start
        if self._pan_cv is self.prev:
            if not self.editing:
                return
            s = self._zoom_scale()
            self.vcenter = (cx - (ev.x - x0) / s, cy - (ev.y - y0) / s)
            self._render_edit()
        elif self._pan_cv is self.src:
            if self._src_img is None:
                return
            s = self._szoom_scale()
            self.scenter = (cx - (ev.x - x0) / s, cy - (ev.y - y0) / s)
            self._render_src()
            self._redraw_box()

    def _edit_cursor(self) -> str:
        if self._brush_mode == "paint":
            return "pencil"
        if self._brush_mode == "erase":
            return "dotbox"
        return "tcross" if self._crop_armed else "crosshair"

    def _pan_release(self, _ev) -> None:
        self._pan_start = None
        cv, self._pan_cv = self._pan_cv, None
        if cv is self.prev and self.editing:
            cv.config(cursor=self._edit_cursor())
        elif cv is self.src:
            cv.config(cursor="crosshair")

    # ---------------------------------------------------------------- 渲染
    def _checker(self, shape: tuple[int, int]) -> np.ndarray:
        """棋盘格底图按尺寸缓存（要返回副本，view 会被 mask 染色改掉）。"""
        a = self._checker_cache.get(shape)
        if a is None:
            a = checkerboard(*shape)
            self._checker_cache.clear()
            self._checker_cache[shape] = a
        return a.copy()

    def _render_edit(self) -> None:
        view = self._checker(self.mask.shape)
        view[self.mask] = self.base[self.mask]
        self._view = view
        self.prev.delete("ph")

        s, cx, cy, ox, oy, ix0, iy0, ix1, iy1 = self._edit_geometry()
        aw, ah = self._canvas_size(self.prev)
        self.escale = s
        crop = view[iy0:iy1, ix0:ix1]
        self.prev.delete("img")
        self.prev.delete("grid")
        self.prev.delete("selout")
        if crop.size:
            dh = max(1, int(round(crop.shape[0] * s)))
            dw = max(1, int(round(crop.shape[1] * s)))
            img = Image.fromarray(crop).resize((dw, dh), Image.NEAREST)
            photo = ImageTk.PhotoImage(img)
            self._photos["edit"] = photo
            self.prev.create_image(int(round(ox + ix0 * s)), int(round(oy + iy0 * s)),
                                   anchor="nw", image=photo, tags="img")
        if s >= 4:
            gy0 = max(0, int(round(oy)))
            gy1 = min(ah, int(round(oy + self.mask.shape[0] * s)))
            gx0 = max(0, int(round(ox)))
            gx1 = min(aw, int(round(ox + self.mask.shape[1] * s)))
            for gx in range(ix0, ix1 + 1):
                X = int(round(ox + gx * s))
                self.prev.create_line(X, gy0, X, gy1, fill="#d9d9d6", tags="grid")
            for gy in range(iy0, iy1 + 1):
                Y = int(round(oy + gy * s))
                self.prev.create_line(gx0, Y, gx1, Y, fill="#d9d9d6", tags="grid")
        self._draw_sel_outline(s, ox, oy)

        fit = self._fit_scale()
        self.zoom_var.set("适应" if self.zoom <= 0 else f"{s / fit * 100:.0f}%")
        if self.sel is not None and self.sel.any():
            self.wand_chip.place_forget()
        else:
            self.wand_chip.place(x=10, y=10)
        if self.sel is not None and self.sel.any():
            n = int(self.sel.sum())
            self.info_var.set(f"已选 {n} 像素（{n * 100 // max(self.sel.size, 1)}%）")
        else:
            kept, total = int(self.mask.sum()), self.mask.size
            # 只为显示"裁好后"尺寸就直接取 mask 的非零 bbox，不用真合成 RGBA
            if kept:
                mys, mxs = np.nonzero(self.mask)
                size = f"{mxs.max() - mxs.min() + 1}×{mys.max() - mys.min() + 1}"
            else:
                size = "空"
            self.info_var.set(f"保留 {kept}/{total} 像素"
                              f"（{kept * 100 // max(total, 1)}%），裁好后 {size}")
        self._refresh_ui()

    @staticmethod
    def _runs(col: np.ndarray) -> list[tuple[int, int]]:
        idx = np.flatnonzero(np.diff(np.concatenate(([False], col, [False]))))
        return list(zip(idx[0::2].tolist(), idx[1::2].tolist()))

    def _draw_sel_outline(self, s: float, ox: float, oy: float) -> None:
        """选区虚线描边（白底 + 绿色虚线），任何底色上都看得见。"""
        if self.sel is None or not self.sel.any():
            return
        m = self.sel
        h, w = m.shape
        up = np.zeros_like(m)
        up[1:] = m[:-1]
        down = np.zeros_like(m)
        down[:-1] = m[1:]
        left = np.zeros_like(m)
        left[:, 1:] = m[:, :-1]
        right = np.zeros_like(m)
        right[:, :-1] = m[:, 1:]
        aw, ah = self._canvas_size(self.prev)
        segs: list[tuple[float, float, float, float]] = []
        for y in range(h):
            for a, b in self._runs(m[y] & ~up[y]):
                segs.append((ox + a * s, oy + y * s, ox + b * s, oy + y * s))
            for a, b in self._runs(m[y] & ~down[y]):
                segs.append((ox + a * s, oy + (y + 1) * s,
                             ox + b * s, oy + (y + 1) * s))
        for x in range(w):
            for a, b in self._runs(m[:, x] & ~left[:, x]):
                segs.append((ox + x * s, oy + a * s, ox + x * s, oy + b * s))
            for a, b in self._runs(m[:, x] & ~right[:, x]):
                segs.append((ox + (x + 1) * s, oy + a * s,
                             ox + (x + 1) * s, oy + b * s))
        vis = [(x1, y1, x2, y2) for x1, y1, x2, y2 in segs
               if max(x1, x2) >= 0 and min(x1, x2) <= aw
               and max(y1, y2) >= 0 and min(y1, y2) <= ah]
        for x1, y1, x2, y2 in vis:
            self.prev.create_line(x1, y1, x2, y2, fill="#ffffff", width=3,
                                  tags="selout")
        for x1, y1, x2, y2 in vis:
            self.prev.create_line(x1, y1, x2, y2, fill=ACCENT, width=2,
                                  dash=(4, 3), tags="selout")

    def _wand_hint(self) -> None:
        if not self.editing:
            self.status.set("框选后点「静态截图」或直接点预览，进修图就能用魔术棒")
            return
        self.status.set("魔术棒：点画面里的颜色选一片，Shift+点加选，"
                        "Alt+点减选，按住拖=平移")
        self.prev.config(cursor="tcross")

    def _wand(self, cx: int, cy: int, add: bool = False,
              sub: bool = False) -> None:
        ix, iy = self._to_img(self.prev, cx, cy)
        self._wand_img(ix, iy, add, sub)

    def _wand_at_client(self, cx: int, cy: int,
                        add: bool, sub: bool) -> None:
        """编辑态点左边画面 = 魔术棒：客户区坐标 → base 坐标（base 是框选裁出来的）。"""
        off = self.base_origin
        if off is None and self.box is not None and self.base is not None:
            x1, y1, x2, y2 = self.box
            if self.base.shape[0] == y2 - y1 and self.base.shape[1] == x2 - x1:
                off = (x1, y1)
        if off is None:
            self.status.set("这张图对不上窗口位置，去右边预览里点魔术棒")
            return
        self._wand_img(cx - off[0], cy - off[1], add, sub)

    def _wand_img(self, ix: int, iy: int, add: bool = False,
                  sub: bool = False) -> None:
        """魔术棒（PS 习惯）：点一下选一片，Shift+点加选，Alt+点减选。
        「只选连通」开 = 只拿点击处连通的一片；关 = 全图同色都选。
        已变透明的像素不参与，免得反选后又被「选回来」。"""
        if not self.editing:
            return
        h, w = self.mask.shape
        if not (0 <= iy < h and 0 <= ix < w):
            self.status.set("点在修图范围外，点框选区域里的颜色")
            return
        fn = core.flood_fill if self.contig_var.get() else core.color_region
        region = fn(self.base, (iy, ix),
                    tol=self.wand_tol_var.get()) & self.mask
        if not region.any():
            self.status.set("这一点选不到东西（透明或孤立像素），换个地方点")
            return
        self._push_undo()
        if sub and self.sel is not None:
            self.sel = self.sel & ~region
        elif add and self.sel is not None:
            self.sel = self.sel | region
        else:
            self.sel = region
        self._render_edit()
        n = int(region.sum())
        if n < 16 and not add and not sub:
            # 噪点多时容差太小会只选到几个像素，看起来就像"没反应"
            self.status.set(f"只选到 {n} 个像素，颜色有噪点，把「棒容差」调大再点")
            return
        self.status.set("描边圈住的就是选中的；Shift+点加选，Alt+点减选，"
                        "按住拖=平移，Ctrl+D 取消，「反选透明」只留选中的")

    def _deselect(self) -> None:
        """Ctrl+D：取消当前选区。"""
        if not self.editing or self.sel is None or not self.sel.any():
            return
        self._push_undo()
        self.sel = np.zeros_like(self.mask)
        self._render_edit()
        self.status.set("已取消选区")

    def _push_undo(self) -> None:
        # 录制中一动修图（魔术棒/画笔/擦除/反选/撤销）就自动暂停：
        # 不然下一帧中位数结果会把手改的盖掉。用户不用知道要先点「暂停」。
        if self._dyn and not self._dyn_paused:
            self.dyn_pause()
            self.status.set("已自动暂停采帧，放心修图；要继续采帧点「继续」")
        self.undo.append((self.base, self.mask.copy(),
                          None if self.sel is None else self.sel.copy()))
        self.undo = self.undo[-UNDO_LIMIT:]

    def arm_crop(self) -> None:
        if not self.editing:
            messagebox.showwarning("不在编辑态", "先截一张进编辑态再做。")
            return
        self._brush_off()
        self._crop_armed = True
        self.prev.config(cursor="tcross")
        self.status.set("在预览上拖出要擦掉的矩形（松手即变透明）")

    def _crop_to(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """框选擦除：拖出的矩形直接变透明，跟橡皮一样去掉，只是方形大笔。"""
        h, w = self.mask.shape
        x1, x2 = sorted((max(0, x1), min(w, x2)))
        y1, y2 = sorted((max(0, y1), min(h, y2)))
        if x2 - x1 < 4 or y2 - y1 < 4:
            self.prev.delete("sel")
            self.status.set("框的太小，没擦")
            return
        self._push_undo()
        self.mask[y1:y2, x1:x2] = False
        if self.sel is not None:
            self.sel[y1:y2, x1:x2] = False   # 擦掉的像素也别留在选区里
        self.prev.delete("sel")
        self._render_edit()
        self.status.set(f"已擦掉 {x2 - x1}×{y2 - y1} 区域（撤销可还原）")

    def despeckle(self) -> None:
        if not self.editing:
            messagebox.showwarning("不在编辑态", "先截一张进编辑态再做。")
            return
        self._push_undo()
        self.mask = core.remove_small(self.mask, 4)
        self._render_edit()

    def shrink_edge(self) -> None:
        if not self.editing:
            return
        before = int(self.mask.sum())
        shrunk = core.erode(self.mask, 1)
        if not shrunk.any():
            self.status.set("再收就没有像素了，没收")
            return
        self._push_undo()
        self.mask = shrunk
        self._render_edit()
        self.status.set(f"已向内收 1 像素：{before} → {int(shrunk.sum())}（撤销可还原）")

    def keep_main(self) -> None:
        if not self.editing:
            return
        main = core.largest_component(self.mask)
        dropped = int(self.mask.sum()) - int(main.sum())
        if dropped <= 0:
            self.status.set("已经是一整块了")
            return
        self._push_undo()
        self.mask = main
        self._render_edit()
        self.status.set(f"只留最大块，去掉了 {dropped} 个零散像素（撤销可还原）")

    def invert(self) -> None:
        if not self.editing:
            messagebox.showwarning("不在编辑态", "先截一张进编辑态再做。")
            return
        if self.sel is None or not self.sel.any():
            self.status.set("先在预览里点颜色选中要保留的部分")
            return
        self._push_undo()
        self.mask = self.mask & self.sel
        self.sel = np.zeros_like(self.mask)
        self._render_edit()
        self.status.set("没选中的都变透明了（撤销可还原）")

    def undo_step(self) -> None:
        if self.undo:
            self.base, self.mask, self.sel = self.undo.pop()
            self._render_edit()

    # ---------------------------------------------------------------- 画笔/橡皮
    def arm_brush(self, mode: str = "paint") -> None:
        if not self.editing:
            messagebox.showwarning("不在编辑态", "先截一张进编辑态再用画笔。")
            return
        if self._crop_armed:
            self.status.set("先把框选拖完，再开画笔")
            return
        if self._brush_mode == mode:
            self._brush_off()
            return
        self._brush_off()
        self._brush_mode = mode
        paint = mode == "paint"
        btn = self.paint_btn if paint else self.eraser_btn
        btn.configure(text="✎ 画笔中" if paint else "⌫ 擦除中",
                      fg_color=ACCENT_SOFT, border_color=ACCENT)
        self.prev.config(cursor="pencil" if paint else "dotbox")
        self.status.set(("画笔：左键拖=补回像素，右/中键拖=平移，Esc 退出" if paint
                        else "橡皮：左键拖=擦掉像素，右/中键拖=平移，Esc 退出"))

    def _brush_off(self) -> None:
        had = self._brush_mode is not None
        self._brush_mode = None
        for b, t in ((getattr(self, "paint_btn", None), "✎ 画笔"),
                     (getattr(self, "eraser_btn", None), "⌫ 橡皮")):
            if b is not None:
                b.configure(text=t, fg_color=CARD, border_color=BORDER)
        self.prev.delete("brushcur")
        if had and self.editing:
            self.prev.config(cursor=self._edit_cursor())
            self.status.set("已退出画笔")

    def _brush_apply(self, cx: int, cy: int, keep: bool,
                     first: bool = False) -> None:
        """在画布点 (cx,cy) 画一笔：keep=True 补回保留区，False 擦除。
        first=True（落笔）先存撤销点，拖动中不再存。"""
        ix, iy = self._to_img(self.prev, cx, cy)
        h, w = self.mask.shape
        if not (0 <= iy < h and 0 <= ix < w):
            return
        if first:
            self._push_undo()
        r = max(1, int(self.brush_var.get()))
        y0, y1 = max(0, iy - r), min(h, iy + r + 1)
        x0, x1 = max(0, ix - r), min(w, ix + r + 1)
        yy, xx = np.ogrid[y0:y1, x0:x1]
        d = (yy - iy) ** 2 + (xx - ix) ** 2 <= r * r
        if keep:
            self.mask[y0:y1, x0:x1] |= d
        else:
            self.mask[y0:y1, x0:x1] &= ~d
        self._render_edit()

    # ================================================================ 保存/测试
    def _current_rgba(self) -> np.ndarray:
        return core.crop_to_content(core.compose_from_base(self.base, self.mask))

    def _template_origin(self) -> tuple[int, int] | None:
        """裁边后的模板左上角在窗口客户区里的坐标；不知道来源位置时返回 None。"""
        if self.base_origin is None or self.mask is None or not self.mask.any():
            return None
        ys, xs = np.nonzero(self.mask)
        return self.base_origin[0] + int(xs.min()), self.base_origin[1] + int(ys.min())

    def _png_meta(self, rgba: np.ndarray) -> PngInfo:
        """把来源写进 PNG 文字块：以后查"这张模板是在什么条件下截的"有据可查。
        文字块不影响读图和匹配（像素、alpha 通道都不变）。"""
        meta = PngInfo()
        meta.add_text("mhxy.tool", f"maketpl {BUILD}")
        meta.add_text("mhxy.size", f"{rgba.shape[1]}x{rgba.shape[0]}")
        origin = self._template_origin()
        if origin is not None:
            meta.add_text("mhxy.origin", f"{origin[0]},{origin[1]}")
        if self.src_fid is not None:
            meta.add_text("mhxy.capture", self.src_fid[1])
        if self.hwnd is not None and not self.frame_from_image:
            w, h = winapi.client_size(self.hwnd)
            meta.add_text("mhxy.client", f"{w}x{h}")
            meta.add_text("mhxy.dpi", f"{winapi.window_dpi(self.hwnd)}/"
                                      f"{winapi.monitor_dpi(self.hwnd)}")
        return meta

    def save(self) -> None:
        if not self.editing:
            messagebox.showwarning("还没生成", "先截一张进编辑态再做。")
            return
        try:
            result = self._current_rgba()
        except ValueError as exc:
            messagebox.showwarning("没有有效像素", str(exc))
            return
        kept = int((result[:, :, 3] >= 128).sum())
        if kept < 4:
            messagebox.showwarning("有效像素太少", f"只剩 {kept} 个有效像素，匹配器要至少 4 个。")
            return
        if self.hwnd is not None and not self.frame_from_image:
            self._check_window_fid()   # 以画面现在的真实状态为准，不是绑定那一刻的
        if (self.src_fid is not None and not self.src_fid[0]
                and not self.frame_from_image):
            if not messagebox.askyesno(
                    "画面可能不是原始像素",
                    f"{self.src_fid[1]}\n\n用它做的模板拿到真机 100% 缩放下大概率匹配不上。"
                    "\n仍然保存吗？"):
                return
        path = filedialog.asksaveasfilename(
            title="保存透明模板", defaultextension=".png",
            initialdir=save_dir(), filetypes=[("PNG（带透明通道）", "*.png")])
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"   # 只存 PNG：BMP 没有透明通道，存了等于把抠图结果丢了
        Image.fromarray(result).save(path, pnginfo=self._png_meta(result), optimize=True)
        self._saved = True
        self.status.set(f"已存 {os.path.basename(path)}")
        self.info_var.set(self.info_var.get() + f"\n已存到 {path}")
        self._refresh_ui()

    def test_match(self) -> None:
        """后台线程跑匹配：大模板在大图上要几秒，不能卡死 UI。"""
        if not self.editing:
            messagebox.showwarning("还没生成", "先截一张进编辑态再做。")
            return
        if self._test_running:
            return
        try:
            tpl = self._current_rgba()
        except ValueError as exc:
            messagebox.showwarning("没有有效像素", str(exc))
            return
        self._test_running = True
        self._refresh_ui()
        self.status.set("测试匹配中…")
        # 容差/分数默认和 mhxy 的 find_all 一致；以前这里借用了"求稳容差"（默认 8），
        # 比第三层实际用的 24 严得多，测试通过不代表真机能找到
        tol = self._int(self.mtol_var, 0, 80, MATCH_TOL)
        limit = self._int(self.score_var, 1, 60, MATCH_SCORE)
        frame0 = self.frame

        def runner():
            frame = frame0
            note = ""
            try:
                if self.hwnd is not None:
                    # 测试要整窗：先试 PrintWindow，被别的窗口（包括本工具）盖住也能抓
                    frame = self._grab_frame(prefer="printwindow")
            except Exception:  # noqa: BLE001
                if frame is None:
                    self._post(self._test_done, None, frame,
                               RuntimeError("截不到整窗画面"))
                    return
                note = "没抓到实时整窗，用的是上一帧画面测"
            try:
                hits = findimg.find_all(frame, tpl, tol=tol, max_score=limit)
            except Exception as exc:  # noqa: BLE001
                self._post(self._test_done, None, frame, exc)
                return
            self._post(self._test_done, hits, frame, None, note)

        threading.Thread(target=runner, daemon=True).start()

    def _test_done(self, hits, frame, exc, note: str = "") -> None:
        self._test_running = False
        self._refresh_ui()
        if exc is not None:
            if isinstance(exc, ValueError):
                messagebox.showwarning("匹配失败", str(exc))
            else:
                messagebox.showerror("截图失败", str(exc))
            return
        if frame is None:
            messagebox.showwarning("没有画面", "先绑窗口截图或载入图片。")
            return
        # 不退出修图态：测完不满意还要接着改、再测，退出会把手修的结果全丢掉
        self.frame = frame
        self.frame_alpha = None
        if self.hwnd is not None and not note:
            self.frame_from_image = False   # 这张就是刚从窗口抓的
        self.live_var.set(False)
        self._live_sync()
        self.szoom = 0.0   # 测试匹配要看整窗：丢掉放大状态
        self.scenter = None
        self._show_src(frame)
        ox, oy = self._img_origin(self.src, (frame.shape[1], frame.shape[0]))
        limit = self._int(self.score_var, 1, 60, MATCH_SCORE)
        for i, hit in enumerate(hits):
            x1, y1 = ox + hit.x * self.sscale, oy + hit.y * self.sscale
            x2, y2 = ox + (hit.x + hit.w) * self.sscale, oy + (hit.y + hit.h) * self.sscale
            col = GREEN if i == 0 else "#e8a33d"
            self.src.create_rectangle(x1, y1, x2, y2, outline=col, width=2, tags="hit")
            self.src.create_text(x1, y1 - 8, text=f"{hit.score:.2f}", fill=col,
                                 anchor="w", tags="hit")
        if hits:
            best = hits[0]
            self.status.set(f"{note}命中 {len(hits)} 处，最佳 ({best.x},{best.y})"
                            f" 分数 {best.score:.2f}（≤{limit} 才算中）")
        else:
            self.status.set(f"{note}没命中：分数都超过 {limit}，"
                            "或关键点容差内没有候选")


def main() -> int:
    winapi.set_dpi_aware()
    root = ctk.CTk()
    MakeTplApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
