# 真实手动测试：拉起真 app + 真目标窗口，按用户操作流程逐步驱动并截图。
# 截图存 _uishots\*.png，断言失败会打 FAIL。
import os, sys, time, subprocess, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import customtkinter as ctk
import tkinter as tk
from PIL import Image, ImageGrab
from maketpl import app as appmod

HERE = os.path.dirname(os.path.abspath(__file__))
SHOT = os.path.join(HERE, "_uishots")
os.makedirs(SHOT, exist_ok=True)
results = []
def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL"), name, extra)

# 拦截会阻塞的对话框
appmod.messagebox.showwarning = lambda *a, **k: print("[warn]", a)
appmod.messagebox.showerror = lambda *a, **k: print("[err]", a)
appmod.messagebox.showinfo = lambda *a, **k: print("[info]", a)
appmod.messagebox.askyesno = lambda *a, **k: (print("[askyesno]", a[0] if a else ""), True)[1]
appmod.messagebox.askokcancel = lambda *a, **k: True
SAVE_PATH = os.path.join(SHOT, "saved_tpl.png")
appmod.filedialog.asksaveasfilename = lambda **k: SAVE_PATH
appmod.filedialog.askopenfilename = lambda **k: ""

# ---- 目标窗口进程 ----
# 清掉上次崩溃留下的残留目标窗口（标题 UI_TEST_TARGET），免得从列表选/遮挡判定被干扰
import ctypes as _ct
_u = _ct.windll.user32
def _kill_orphans():
    hs = []
    def _cb(h, l):
        n = _u.GetWindowTextLengthW(h)
        if n:
            b = _ct.create_unicode_buffer(n + 1)
            _u.GetWindowTextW(h, b, n + 1)
            if "UI_TEST_TARGET" in b.value:
                hs.append(h)
        return True
    _CB = _ct.WINFUNCTYPE(_ct.c_bool, _ct.c_void_p, _ct.c_void_p)
    _u.EnumWindows(_CB(_cb), 0)
    for h in hs:
        _u.PostMessageW(h, 0x0010, 0, 0)   # WM_CLOSE
    return len(hs)
_kill_orphans()

hwnd_file = os.path.join(HERE, "_uitarget_hwnd.txt")
if os.path.exists(hwnd_file):
    os.remove(hwnd_file)
subprocess.Popen([sys.executable, os.path.join(HERE, "_uitarget.py")],
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(150):
    if os.path.exists(hwnd_file):
        break
    time.sleep(0.1)
THWND = int(open(hwnd_file).read())
print("target hwnd:", THWND)

root = ctk.CTk()
a = appmod.MakeTplApp(root)
root.geometry("880x700+400+10")

# _post 在真实程序里靠 mainloop 跨线程分发 after 回调；测试脚本用 update()
# 轮询，主线程多半在 sleep 里，after 会报"main thread is not in main loop"。
# 换成线程安全队列，pump 时在主线程排空执行，语义等价。
import queue
_postq = queue.Queue()
a._post = lambda fn, *args: _postq.put((fn, args))

def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        try:
            while True:
                fn, args = _postq.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        root.update(); time.sleep(0.005)

def shot(name):
    pump(0.25)
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    ImageGrab.grab((x, y, x + w, y + h)).save(os.path.join(SHOT, name + ".png"))

class E:
    def __init__(self, x, y, state=0, widget=None, delta=0, num=1):
        self.x, self.y, self.state = x, y, state
        self.widget, self.delta, self.num = widget, delta, num

def src_click_drag(ix1, iy1, ix2, iy2):
    """图像坐标框选：图像坐标→src画布坐标→press/drag/release"""
    c1 = a._to_cv(a.src, ix1, iy1); c2 = a._to_cv(a.src, ix2, iy2)
    a._press(E(*c1, widget=a.src))
    a._drag_move(E(*c2, widget=a.src))
    a._release(E(*c2, widget=a.src))

_u32 = _ct.windll.user32

def prev_click_hold(ix, iy, vk):
    """按住真实键点预览：_mods() 问 OS 键态，假 state 不再生效。"""
    _u32.keybd_event(vk, 0, 0, 0)
    try:
        prev_click(ix, iy)
    finally:
        _u32.keybd_event(vk, 0, 0x0002, 0)

def prev_click(ix, iy, state=0):
    cx, cy = a._to_cv(a.prev, ix, iy)
    a._press(E(cx, cy, state, a.prev))
    a._release(E(cx, cy, state, a.prev))

def prev_drag(ix1, iy1, ix2, iy2, state=0):
    c1 = a._to_cv(a.prev, ix1, iy1); c2 = a._to_cv(a.prev, ix2, iy2)
    cm = ((c1[0] + c2[0]) // 2, (c1[1] + c2[1]) // 2)
    a._press(E(*c1, state, a.prev))
    a._drag_move(E(*cm, state, a.prev))
    a._drag_move(E(*c2, state, a.prev))
    a._release(E(*c2, state, a.prev))

pump(1.0); shot("01_launch")

# ============ 1. 绑定 ============
a._bind_hwnd(THWND)
pump(1.3)
check("绑定 hwnd", a.hwnd == THWND)
check("实时画面有帧", a.frame is not None)
f1 = a.frame.copy(); pump(0.6)
motion = float(np.abs(a.frame.astype(int) - f1.astype(int)).mean())
check("实时画面在动", motion > 0.5, f"diff={motion:.2f}")
shot("02_bound_live")

# ============ 2. 框选 ============
fh, fw = a.frame.shape[:2]
src_click_drag(int(fw * .04), int(fh * .04), int(fw * .5), int(fh * .5))
check("框选成功", a.box is not None, str(a.box))
shot("03_boxed")

# ============ 3. 动态截图 ============
a.dyn_shot()
check("动采启动", a._dyn)
pump(1.4)
check("动采攒帧", len(a.frames) >= 2, f"{len(a.frames)}帧")
shot("04_dyn_monitoring")
a.dyn_shot()          # 再点一次 = 停止并生成
pump(0.4)
check("动采停止进修图", a.editing and not a._dyn)
check("掩码非空", a.mask is not None and a.mask.any(),
      f"{a.mask.sum() if a.mask is not None else 0}px")
shot("05_edit_mode")

# ============ 4. 魔术棒 ============
# 在 base 里找一块纯色区的种子点
bh, bw = a.base.shape[:2]
def seed(color):
    m = (np.abs(a.base.astype(int) - np.array(color)).sum(2) < 40) & a.mask
    ys, xs = np.where(m)
    return (int(xs[len(xs)//2]), int(ys[len(ys)//2])) if len(xs) else None

# 清空选区再点开始
a._deselect()
seed_red = seed([220, 60, 60])
check("找到红色块种子", seed_red is not None)
if seed_red:
    prev_click(*seed_red)
    n1 = int(a.sel.sum()) if a.sel is not None else 0
    check("点选连通块", n1 > 100, f"{n1}px")
    seed_grn = seed([60, 140, 70])
    if seed_grn and not a.sel[seed_grn[1], seed_grn[0]]:
        prev_click_hold(*seed_grn, 0x10)   # 真实按住 Shift 加选
        n2 = int(a.sel.sum())
        check("Shift加选变大", n2 > n1, f"{n1}->{n2}")
    else:
        n2 = n1
        check("Shift加选变大", False, "没找到第二块")
    # Alt 减选：点已选区域中心
    ys, xs = np.where(a.sel)
    prev_click_hold(int(xs[len(xs)//2]), int(ys[len(ys)//2]), 0x12)
    n3 = int(a.sel.sum())
    check("Alt减选变小", n3 < n2, f"{n2}->{n3}")
    # 回归：Windows 的 Tk 事件 state 会虚报 Mod1(0x0008)，普通点击不得被当成 Alt 减选
    a._deselect()
    cx, cy = a._to_cv(a.prev, *seed_red)
    a._press(E(cx, cy, state=0x0008, widget=a.prev))
    a._release(E(cx, cy, state=0x0108, widget=a.prev))
    check("幻影Alt位不误判", a.sel is not None and int(a.sel.sum()) > 100,
          f"sel={0 if a.sel is None else int(a.sel.sum())}")
shot("06_wand_selection")
a._deselect()
check("Ctrl+D 取消", not a.sel.any())

# ============ 5. 画笔/橡皮 ============
m0 = int(a.mask.sum())
a.arm_brush("erase")
ys0, xs0 = int(bh * .5), int(bw * .3)
prev_drag(xs0, ys0, xs0 + 40, ys0)     # 拖一笔擦掉
m1 = int(a.mask.sum())
check("橡皮擦除", m1 < m0, f"{m0}->{m1}")
u0 = len(a.undo)
a.arm_brush("paint")
prev_drag(xs0, ys0, xs0 + 40, ys0)     # 拖一笔补回
m2 = int(a.mask.sum())
check("画笔补回", m2 > m1, f"{m1}->{m2}")
shot("07_brush")
a.arm_brush("paint")                    # 再点一次同模式 = 退出
check("画笔退出", a._brush_mode is None)

# ============ 6. 缩放/平移 ============
s0 = a.escale
a._wheel_zoom(E(bw/2, bh/2, 0, a.prev, delta=120))
check("滚轮放大", a.escale > s0, f"{s0:.2f}->{a.escale:.2f}")
c0 = a._zoom_center()
a.sel = np.zeros_like(a.mask)          # 保证干净
prev_drag(bw//2, bh//2, bw//2 + 60, bh//2 + 40)   # 拖动>5px = 平移非点选
c1 = a._zoom_center()
check("拖动=平移不误选", not a.sel.any() and c1 != c0, f"{c0}->{c1}")
shot("08_zoom_pan")
a.zoom = 0.0; a.vcenter = None; a._render_edit()

# ============ 7. 框选擦除（拖矩形=去掉这块）============
z0 = a.escale
a.arm_crop()
m_before = int(a.mask.sum())
rx1, ry1, rx2, ry2 = int(bw*.1), int(bh*.1), int(bw*.7), int(bh*.7)
prev_drag(rx1, ry1, rx2, ry2)
check("框选擦除不裁尺寸", a.base.shape[:2] == (bh, bw))
check("框内全擦除", not a.mask[ry1+3:ry2-3, rx1+3:rx2-3].any())
erased = m_before - int(a.mask.sum())
expect = (ry2 - ry1) * (rx2 - rx1)
check("擦除面积≈框面积", abs(erased - expect) <= 4 * (rx2 - rx1 + ry2 - ry1),
      f"{erased} vs {expect}")
check("擦除不动缩放", abs(a.escale - z0) < 0.01,
      f"escale {z0:.2f}->{a.escale:.2f}")
a.undo_step()
check("撤销恢复", a.mask.sum() == m_before)

# ============ 7.5 放大镜只在空手 hover 时出 ============
mag = a._mags[a.prev]
mag_on = lambda: mag.winfo_manager() == "place"
cx0, cy0 = a._to_cv(a.prev, 30, 30)      # 图像内一点 → 画布坐标
a._hover(E(cx0, cy0, 0, a.prev))
check("空手hover出放大镜", mag_on())
a._hover(E(cx0, cy0, 0x0100, a.prev))    # 按住左键（拖动中）
check("拖动不出放大镜", not mag_on())
a.arm_brush("paint")
a._hover(E(cx0, cy0, 0, a.prev))
check("画笔模式不出放大镜", not mag_on())
a._brush_off()
a.arm_crop()
a._hover(E(cx0, cy0, 0, a.prev))
check("裁剪模式不出放大镜", not mag_on())
a._crop_armed = False
a._hover(E(cx0, cy0, 0, a.prev))
check("解除后又出放大镜", mag_on())

# ============ 8. 反选透明 + 去杂点 ============
a._deselect()
if seed_red:
    prev_click(*seed_red)
    a.invert()
    check("反选透明后掩码变小", a.mask.sum() < a.mask.size,
          f"{a.mask.sum()}/{a.mask.size}")
shot("09_inverted")

# ============ 9. 保存 ============
if os.path.exists(SAVE_PATH):
    os.remove(SAVE_PATH)   # 删掉上次的文件，"保存 PNG"必须证明这次真写了
pre = (id(a.mask), int(a.mask.sum()), a._current_rgba().shape)
a.save()
post = (id(a.mask), int(a.mask.sum()), a._current_rgba().shape)
print("[dbg] pre", pre, "post", post, "mtime", os.path.getmtime(SAVE_PATH),
      "src_fid", a.src_fid)
check("保存 PNG", os.path.exists(SAVE_PATH))
if os.path.exists(SAVE_PATH):
    from PIL import Image
    im = Image.open(SAVE_PATH)
    arr = np.array(im)
    # crop_to_content 会把全透明边裁掉：验证 RGBA + 比原图小（说明裁过）
    check("PNG 带透明通道", im.mode == "RGBA" and
          arr.shape[0] < bh and arr.shape[1] < bw,
          f"{im.size} mode={im.mode}")
    # 无损验证：保存的 RGBA 和 base&mask 组合的像素必须逐位一致
    expect_rgba = appmod.core.crop_to_content(
        appmod.core.compose_from_base(a.base, a.mask))
    _same = np.array_equal(arr, expect_rgba)
    _det = ""
    if not _same:
        if arr.shape != expect_rgba.shape:
            _det = f"shape {arr.shape}!={expect_rgba.shape}"
        else:
            _nd = int((arr != expect_rgba).any(axis=2).sum())
            _det = (f"{_nd}px differ; file mtime {os.path.getmtime(SAVE_PATH):.0f}; "
                    f"expect alpha uniq {np.unique(expect_rgba[:,:,3])[:4]}")
    check("保存像素逐位一致", _same, _det)

# ============ 10. 测试匹配（编辑中+窗口被本程序部分遮挡）============
a.test_match()
pump(8)   # _post 走队列，pump 负责派发 _test_done
check("测试匹配跑完", not a._test_running)
check("测试匹配后仍在修图态", a.editing)
hits = a.src.find_withtag("hit")
check("画出命中框", len(hits) > 0, f"{len(hits)//2}组item")
shot("10_test_match")

# ============ 11. 解绑 ============
a.unbind()
check("解绑 hwnd 清空", a.hwnd is None)
check("解绑后画面还在", a.frame is not None)
shot("11_unbound")

# ============ 12. 滑块滚轮穿透 ============
sliders = []
def find(w):
    for c in w.winfo_children():
        if isinstance(c, ctk.CTkSlider):
            sliders.append(c)
        find(c)
find(root)
yv0 = a.right._parent_canvas.yview()
s = sliders[0]; v0 = s.get()
a.right._mouse_wheel_all(E(0, 0, widget=s._canvas, delta=-120))
yv1 = a.right._parent_canvas.yview()
check("滚轮过滑块=滚面板", yv1 != yv0, f"{yv0}->{yv1}")
check("滚轮不改滑块值", s.get() == v0)

# ============ 12.5 载入图片全流程 + 原始像素验证 ============
# 造一张带独特图案的 png，走真实 load_image → 框选 → 静态截图 → 修图
src_img = np.random.randint(0, 255, (200, 300, 3), np.uint8)
src_img[50:100, 50:120] = (220, 60, 60)
test_png = os.path.join(SHOT, "load_src.png")
Image.fromarray(src_img).save(test_png)
appmod.filedialog.askopenfilename = lambda **k: test_png
a.load_image()
pump(0.3)
check("载入后 frame 存在", a.frame is not None)
check("载入像素无损", np.array_equal(a.frame, src_img))
src_click_drag(40, 40, 160, 140)
a.static_shot()
pump(0.3)
check("载入→静态截图进修图", a.editing)
check("进修图像素=原图区域", np.array_equal(a.base, src_img[40:140, 40:160]))
check("载入路径按钮解锁", str(a.crop_btn.cget("state")) == "normal")
seed2 = (60, 60)  # 红块在新 base 里的位置 (50-40, 50-40) 附近
prev_click(*seed2)
check("载入图能魔术棒", a.sel is not None and a.sel.any())
# 编辑态点左边画面 = 魔术棒：客户区(100,100) → base(60,60) 红块
a._deselect()
sx, sy = a._to_cv(a.src, 100, 100)
a._press(E(sx, sy, widget=a.src)); a._release(E(sx, sy, widget=a.src))
check("画面点选=魔术棒", a.sel is not None and a.sel.any(),
      f"{int(a.sel.sum()) if a.sel is not None else 0}px")
a._exit_edit()
shot("12_5_loaded")

# ============ 12.6 画面 Ctrl+滚轮缩放 / 平移 / 还原 ============
check("画面信息芯片", "300×200" in a.szoom_var.get(), a.szoom_var.get())
fit0 = a.sscale
_u32.keybd_event(0x11, 0, 0, 0)   # 真实按住 Ctrl（state 里塞 0x0004 不作数了）
a._swheel(E(200, 150, state=0x0004, widget=a.src, delta=120))
_u32.keybd_event(0x11, 0, 0x0002, 0)
pump(0.1)
check("Ctrl+滚轮放大", a.szoom > 0 and a.sscale > fit0,
      f"{fit0:.2f}->{a.sscale:.2f}")
zs = a.sscale
a._swheel(E(200, 150, state=0, widget=a.src, delta=120))
check("无Ctrl滚轮不缩放", abs(a.sscale - zs) < 1e-6, f"{a.sscale:.2f}")
a.src.delete("sel"); a.box = None
src_click_drag(40, 40, 160, 140)
check("放大态框选准确", a.box is not None
      and abs(a.box[0] - 40) <= 2 and abs(a.box[2] - 160) <= 2, str(a.box))
# 小图 1.3x 仍比画布小，中心被钳住平移不动（正确）；放大到超出画布再平移
_u32.keybd_event(0x11, 0, 0, 0)
for _ in range(6):
    a._swheel(E(200, 150, state=0x0004, widget=a.src, delta=120))
_u32.keybd_event(0x11, 0, 0x0002, 0)
c0 = a.scenter
a._pan_press(E(200, 150, widget=a.src))
a._pan_move(E(170, 130, widget=a.src))
a._pan_release(E(170, 130, widget=a.src))
check("右键平移画面", a.scenter is not None and a.scenter != c0,
      f"{c0}->{a.scenter}")
a._szoom_fit()
check("还原适应", a.szoom == 0 and abs(a.sscale - fit0) < 0.02)
check("还原芯片已放置", bool(a.src_chip.winfo_manager()))
# 缩放/平移/重采样只动显示，a.frame 里的源像素必须一个不变
check("缩放不动源像素", np.array_equal(a.frame, src_img))
h0 = a.src.winfo_height()
root.geometry("880x780+400+10")
for _ in range(20):   # 桌面状态抖动时 geometry 生效会慢，给足重试
    pump(0.1)
    if a.src.winfo_height() > h0:
        break
check("画面随窗口长高", a.src.winfo_height() > h0,
      f"{h0}->{a.src.winfo_height()}")
shot("12_6_src_zoom")

# ============ 13. 静态截图入口解锁按钮（回归：_enter_edit 必须刷新）============
a.box = (48, 34, 280, 190)   # 载入图 300×200，框必须在图内否则 single_frame 拒绝
a.static_shot()            # hwnd=None → single_frame → _enter_edit
pump(0.3)
check("静态截图进修图", a.editing)
check("裁剪解锁", str(a.crop_btn.cget("state")) == "normal")
check("去杂点解锁", str(a.despeckle_btn.cget("state")) == "normal")
check("退出解锁", str(a.exit_btn.cget("state")) == "normal")
check("测试匹配解锁", str(a.test_btn.cget("state")) == "normal")
check("保存解锁", str(a.save_btn.cget("state")) == "normal")
# 端到端无损 1:1：源 PNG → frame → base → mask → 保存 PNG，RGB 必须逐位等于源图
SAVE_PATH2 = os.path.join(SHOT, "saved_static.png")
appmod.filedialog.asksaveasfilename = lambda **k: SAVE_PATH2
if os.path.exists(SAVE_PATH2):
    os.remove(SAVE_PATH2)
a.save(); pump(0.2)
check("静态PNG已写", os.path.exists(SAVE_PATH2))
if os.path.exists(SAVE_PATH2):
    arr2 = np.array(Image.open(SAVE_PATH2))
    oy, ox = a.base_origin[1], a.base_origin[0]
    _ys, _xs = np.nonzero(a.mask)
    cy0, cy1, cx0, cx1 = _ys.min(), _ys.max() + 1, _xs.min(), _xs.max() + 1
    exp_rgb = src_img[oy + cy0:oy + cy1, ox + cx0:ox + cx1]
    check("端到端RGB逐位=源图", arr2.shape[:2] == exp_rgb.shape[:2]
          and np.array_equal(arr2[:, :, :3], exp_rgb),
          f"{arr2.shape} vs {exp_rgb.shape}")
    check("端到端alpha=掩码", np.array_equal(
        arr2[:, :, 3], a.mask[cy0:cy1, cx0:cx1].astype(np.uint8) * 255))
appmod.filedialog.asksaveasfilename = lambda **k: SAVE_PATH
a.arm_brush("paint")
check("画笔能开", a._brush_mode == "paint")
a._brush_off()
a._exit_edit()
shot("12_static_path")

# ============ 13.5 整帧截图（载入图：原样存回，逐位=源图）============
FULL1 = os.path.join(SHOT, "full_loaded.png")
appmod.filedialog.asksaveasfilename = lambda **k: FULL1
if os.path.exists(FULL1):
    os.remove(FULL1)
a.save_fullshot(); pump(0.2)
check("整帧截图已写", os.path.exists(FULL1))
if os.path.exists(FULL1):
    fa = np.array(Image.open(FULL1))
    check("整帧尺寸=原图", fa.shape[:2] == src_img.shape[:2], str(fa.shape))
    check("整帧像素逐位=源图", np.array_equal(fa[:, :, :3], src_img))
    check("整帧含元数据", b"fullframe" in open(FULL1, "rb").read())
appmod.filedialog.asksaveasfilename = lambda **k: SAVE_PATH

# ============ 14. 按钮防闪 ============
import unittest.mock as mock
a.frame = None; a.box = None; a.base = None; a.mask = None; a.sel = None
a._refresh_ui(); a._refresh_ui()
cnt = [0]
orig = ctk.CTkButton.configure
def counted(self, *x, **k):
    cnt[0] += 1
    return orig(self, *x, **k)
with mock.patch.object(ctk.CTkButton, "configure", counted):
    for _ in range(3):
        a._refresh_ui()
check("稳态0重配", cnt[0] == 0, f"{cnt[0]}次")

# ============ 15. 准星拖拽绑定（真实移动鼠标）============
import ctypes
from maketpl import winapi
a.unbind(); pump(0.3)
u32 = ctypes.windll.user32
u32.ShowWindow(THWND, 9)   # SW_RESTORE：跑批中目标若被环境最小化，先拉回再取矩形
pump(0.2)
u32.SetWindowPos(THWND, -1, 0, 0, 0, 0, 0x0003)   # HWND_TOPMOST, NOMOVE|NOSIZE
pump(0.2)
tpid = winapi.pid_of(THWND)
l, t, r, b = winapi.window_rect(THWND)
tx, ty = (l + r) // 2, (t + b) // 2
# 桌面 z 序不可控（最大化 Chrome、资源管理器悬浮窗都可能盖目标），
# WindowFromPoint 是 OS 边界——钉到目标句柄，测我们自己的 track→bind 链路
_orig_wfp = winapi.window_from_point
winapi.window_from_point = lambda x, y: THWND
u32.SetCursorPos(tx, ty)
a._aim_down(None)
pump(0.3)
for i in range(5):        # 真实移动鼠标，让 track 多跑几拍
    u32.SetCursorPos(tx + 1 + i, ty)
    pump(0.15)
a._aim_up(None)
winapi.window_from_point = _orig_wfp
u32.SetWindowPos(THWND, -2, 0, 0, 0, 0, 0x0003)  # NOTOPMOST
check("拖拽绑定成功", a.hwnd is not None and winapi.pid_of(a.hwnd) == tpid,
      f"aim={a._aim_hwnd} at {tx},{ty}")
pump(0.8)
check("拖拽绑定后直播恢复", a.frame is not None)
a.unbind(); pump(0.2)

# ============ 16. 从列表选 ============
a.pick_from_list(); pump(0.4)
dlgs = [w for w in root.winfo_children() if isinstance(w, ctk.CTkToplevel)]
check("列表弹窗打开", len(dlgs) > 0)
btns = []
def _collect(w):
    for c in w.winfo_children():
        if isinstance(c, ctk.CTkButton):
            btns.append(c)
        _collect(c)
if dlgs:
    _collect(dlgs[0])
check("列表有候选项", len(btns) > 3, f"{len(btns)}个")
tbtn = next((b for b in btns if "UI_TEST_TARGET" in str(b.cget("text"))), None)
check("列表含目标窗", tbtn is not None)
if tbtn is not None:
    tbtn.invoke(); pump(0.5)
    check("列表选择绑定", a.hwnd is not None)
check("弹窗已关", not dlgs or not dlgs[0].winfo_exists())

# ============ 16.5 整帧截图（绑定窗：现场抓一帧原尺寸存）============
a.live_var.set(False); a._on_live_toggle(); pump(0.3)   # 先定格，免得直播线程把 a.frame 换掉
FULL2 = os.path.join(SHOT, "full_bound.png")
appmod.filedialog.asksaveasfilename = lambda **k: FULL2
if os.path.exists(FULL2):
    os.remove(FULL2)
a.save_fullshot(); pump(0.3)
check("绑定整帧已写", os.path.exists(FULL2))
if os.path.exists(FULL2):
    fa = np.array(Image.open(FULL2))
    check("绑定整帧=客户区原尺寸",
          fa.shape[0] == a.frame.shape[0] and fa.shape[1] == a.frame.shape[1],
          f"{fa.shape}")
    check("绑定整帧像素=所截帧", np.array_equal(fa[:, :, :3], a.frame))
appmod.filedialog.asksaveasfilename = lambda **k: SAVE_PATH
a.live_var.set(True); a._on_live_toggle(); pump(0.4)   # 恢复直播给下节用

# ============ 17. 实时画面开关 ============
f_on = a.frame.copy(); pump(0.6)
check("直播开着帧在变",
      np.abs(a.frame.astype(int) - f_on.astype(int)).mean() > 0.3)
a.live_var.set(False); a._on_live_toggle(); pump(0.4)
f_off = a.frame.copy(); pump(0.6)
check("关掉后画面定格", np.array_equal(a.frame, f_off))

# ============ 18. 动态暂停/继续 ============
a.box = (48, 34, 400, 300)
a.dyn_shot(); pump(0.8)
n0 = len(a.frames)
a.dyn_pause(); pump(0.6)
n1 = len(a.frames)
check("暂停后帧不涨", len(a.frames) - n1 <= 1, f"{n1}帧")
a.dyn_pause(); pump(0.6)
check("继续后帧再涨", len(a.frames) > n1, f"{n1}->{len(a.frames)}")
# 录制中直接修图 → 自动暂停（不用先点暂停）
check("录制中仍在跑", a._dyn and not a._dyn_paused)
if a.editing:
    a.despeckle()          # 修图动作 → _push_undo → 应自动暂停
    pump(0.3)
check("修图自动暂停", a._dyn_paused)
a.unbind()
check("动采中解绑不崩", a.hwnd is None and not a._dyn)
pump(0.3)

# ============ 19. 去杂点功能 ============
img30 = np.full((30, 30, 3), 100, np.uint8)
m30 = np.zeros((30, 30), bool)
m30[10:20, 10:20] = True          # 大孤岛保留
m30[2, 2] = True                  # 1px 孤点该被清
m30[26:28, 26:28] = True          # 4px 小块也该被清
a._enter_edit(img30, m30.copy())
a.despeckle()
check("去杂点清孤点", not a.mask[2, 2])
check("去杂点清小块", not a.mask[26:28, 26:28].any())
check("去杂点留大块", a.mask[10:20, 10:20].all())
a._exit_edit(redraw=False)

# ============ 20. 方向键微调 ============
a.box = (50, 50, 200, 200)
a._nudge(1, 0, E(0, 0, 0, a.src))
check("方向键移1px", a.box[0] == 51)
_u32.keybd_event(0x10, 0, 0, 0)        # 真实按住 Shift
a._nudge(1, 0, E(0, 0, 1, a.src))
_u32.keybd_event(0x10, 0, 0x0002, 0)
check("Shift移10px", a.box[0] == 61)
a._nudge(0, 1, E(0, 0, 0, a.src))
check("方向键下移", a.box[1] == 51)

# ============ 21. 缩放条（− / 适应% / + 都是 Label 点按）============
a._enter_edit(img30, np.ones((30, 30), bool))
zlabs = [w for w in a.zoom_bar.winfo_children() if isinstance(w, ctk.CTkLabel)]
minus, pct, plus = zlabs[0], zlabs[1], zlabs[2]
s_fit = a._zoom_scale()
plus._label.event_generate("<Button-1>", x=5, y=5, when="now")   # CTkLabel.bind 转发给内部控件
pump(0.1)
check("缩放条+放大", a._zoom_scale() > s_fit,
      f"{s_fit:.2f}->{a._zoom_scale():.2f}")
minus._label.event_generate("<Button-1>", x=5, y=5, when="now")
pump(0.1)
check("缩放条-缩小", a._zoom_scale() <= s_fit)
pct._label.event_generate("<Button-1>", x=5, y=5, when="now")
pump(0.1)
check("点%恢复适应", a.zoom <= 0)
a._exit_edit(redraw=False)

# ============ 22. 异常路径 ============
h0 = a.hwnd
a._bind_hwnd(0)
check("绑0不生效", a.hwnd == h0)
a.box = None
a.static_shot()                          # 无框 → 警告不崩
check("无框静态截图不崩", not a.editing)
a.test_match()                           # 非编辑 → 警告不跑
check("非编辑测试匹配不跑", not a._test_running)
_f, _h = a.frame, a.hwnd                   # 无画面整帧截图 → 警告不崩
a.frame, a.hwnd = None, None
a.save_fullshot()
a.frame, a.hwnd = _f, _h
check("无画面整帧截图不崩", True)
# 透明区不能被魔术棒选
img40 = np.full((40, 40, 3), 50, np.uint8)
m40 = np.ones((40, 40), bool); m40[5:15, 5:15] = False
a._enter_edit(img40, m40)
prev_click(10, 10)                       # 点在透明区
check("透明区选不中", not a.sel[5:15, 5:15].any())
prev_click(30, 30)
check("正常区能选", a.sel[30, 30] or a.sel.any())
a._exit_edit(redraw=False)

print("\n==== RESULT ====")
fails = [n for n, ok in results if not ok]
print(f"{len(results)-len(fails)}/{len(results)} PASS", "| FAIL:", fails)
root.destroy()
