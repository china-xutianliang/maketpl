# 为视频抓真实工具界面截图：拉起假目标窗口 + 真 app，窗口置顶后逐步操作截图。
# 复用 _uitest.py 的驱动方式，区别是截图前强制置顶，避免抓到遮挡窗口。
import os, sys, time, subprocess, queue
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHOT = os.path.join(HERE, "assets", "ui")
os.makedirs(SHOT, exist_ok=True)

import customtkinter as ctk
import ctypes as _ct
from PIL import ImageGrab
from maketpl import app as appmod

appmod.messagebox.showwarning = lambda *a, **k: print("[warn]", a)
appmod.messagebox.showerror = lambda *a, **k: print("[err]", a)
appmod.messagebox.showinfo = lambda *a, **k: print("[info]", a)
appmod.messagebox.askyesno = lambda *a, **k: True
appmod.messagebox.askokcancel = lambda *a, **k: True

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
        _u.PostMessageW(h, 0x0010, 0, 0)
_kill_orphans()

hwnd_file = os.path.join(ROOT, "_uitarget_hwnd.txt")
if os.path.exists(hwnd_file):
    os.remove(hwnd_file)
subprocess.Popen([sys.executable, os.path.join(ROOT, "_uitarget.py")],
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(150):
    if os.path.exists(hwnd_file):
        break
    time.sleep(0.1)
THWND = int(open(hwnd_file).read())
print("target hwnd:", THWND)

root = ctk.CTk()
a = appmod.MakeTplApp(root)
root.geometry("880x700+60+20")
root.attributes("-topmost", True)

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
    pump(0.3)
    root.lift(); root.focus_force()
    pump(0.15)
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    ImageGrab.grab((x, y, x + w, y + h)).save(os.path.join(SHOT, name + ".png"))
    print("shot", name, w, h)

class E:
    def __init__(self, x, y, state=0, widget=None, delta=0, num=1):
        self.x, self.y, self.state = x, y, state
        self.widget, self.delta, self.num = widget, delta, num

def src_click_drag(ix1, iy1, ix2, iy2):
    c1 = a._to_cv(a.src, ix1, iy1); c2 = a._to_cv(a.src, ix2, iy2)
    a._press(E(*c1, widget=a.src))
    a._drag_move(E(*c2, widget=a.src))
    a._release(E(*c2, widget=a.src))

def prev_click(ix, iy, state=0):
    cx, cy = a._to_cv(a.prev, ix, iy)
    a._press(E(cx, cy, state, a.prev))
    a._release(E(cx, cy, state, a.prev))

import numpy as np

pump(1.2); shot("01_launch")

a._bind_hwnd(THWND)
pump(1.5)
shot("02_bound_live")

fh, fw = a.frame.shape[:2]
src_click_drag(int(fw * .04), int(fh * .04), int(fw * .5), int(fh * .5))
pump(0.2)
shot("03_boxed")

a.dyn_shot()
pump(1.6)
shot("04_dyn_monitoring")
a.dyn_shot()
pump(0.5)
shot("05_edit_mode")

bh, bw = a.base.shape[:2]
def seed(color):
    m = (np.abs(a.base.astype(int) - np.array(color)).sum(2) < 40) & a.mask
    ys, xs = np.where(m)
    return (int(xs[len(xs)//2]), int(ys[len(ys)//2])) if len(xs) else None

a._deselect()
seed_red = seed([220, 60, 60])
if seed_red:
    prev_click(*seed_red)
    pump(0.3)
shot("06_wand_selection")
a._deselect()

if seed_red:
    prev_click(*seed_red)
    a.invert()
    pump(0.3)
shot("09_inverted")

a.test_match()
pump(8)
shot("10_test_match")

_u.PostMessageW(THWND, 0x0010, 0, 0)
root.destroy()
print("done")
