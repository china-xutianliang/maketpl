"""临时验证：把「每条边一个 Tk 图元」换成「一张覆盖图」能不能救卡顿。用完即删。"""
import time
import numpy as np
from PIL import Image, ImageTk
import customtkinter as ctk
from maketpl.app import MakeTplApp

root = ctk.CTk()
app = MakeTplApp(root)
root.update_idletasks(); root.update()


def outline_overlay(sel: np.ndarray, rgba_view: np.ndarray) -> np.ndarray:
    """选区高亮+描边全部烘焙进一张 RGB 图：图元数恒为 1。"""
    m = sel
    up = np.zeros_like(m); up[1:] = m[:-1]
    down = np.zeros_like(m); down[:-1] = m[1:]
    left = np.zeros_like(m); left[:, 1:] = m[:, :-1]
    right = np.zeros_like(m); right[:, :-1] = m[:, 1:]
    boundary = m & ~(up & down & left & right)
    out = rgba_view.copy()
    tint = np.array((63, 111, 82), np.float32)
    out[m] = (out[m].astype(np.float32) * 0.62 + tint * 0.38).astype(np.uint8)
    out[boundary] = (255, 255, 255)
    # 绿色虚线描边：边界上按 (x+y)%7<4 上色，模拟 marching ants
    ys, xs = np.nonzero(boundary)
    dash = ((xs + ys) % 7) < 4
    out[ys[dash], xs[dash]] = (63, 111, 82)
    return out


print("=" * 68)
print("方案对比：现方案(逐边 Tk 图元) vs 新方案(单张覆盖图)")
print("=" * 68)
rng = np.random.default_rng(5)
for (h, w) in [(200, 400), (400, 800), (600, 1000)]:
    base = rng.integers(0, 255, (h, w, 3), np.uint8)
    app._enter_edit(base, np.ones((h, w), bool))
    app.sel = np.zeros((h, w), bool)
    app.sel[::2, ::2] = True                 # 最坏的碎选区
    root.update_idletasks()

    t = time.perf_counter()
    app._render_edit()
    old_ms = (time.perf_counter() - t) * 1000
    old_items = len(app.prev.find_all())

    # 新方案：只算覆盖图 + 缩放 + 一个 PhotoImage
    t = time.perf_counter()
    view = app._checker((h, w))
    view[app.mask] = base[app.mask]
    ov = outline_overlay(app.sel, view)
    s = app._zoom_scale()
    dw, dh = max(1, int(w * s)), max(1, int(h * s))
    photo = ImageTk.PhotoImage(Image.fromarray(ov).resize((dw, dh), Image.NEAREST))
    new_ms = (time.perf_counter() - t) * 1000

    print(f"  {w}x{h} 碎选区({int(app.sel.sum())} px):")
    print(f"    现方案 {old_ms:8.1f} ms / {old_items:8d} 图元")
    print(f"    新方案 {new_ms:8.1f} ms /        1 图元   -> 快 {old_ms/new_ms:.0f}x")
    app.prev.delete("all")

print()
print("=" * 68)
print("真实场景模拟：游戏截图上魔术棒选文字（天然碎选区）")
print("=" * 68)
# 造一张像游戏画面的图：渐变底 + 抗锯齿文字边缘
h, w = 300, 600
yy, xx = np.mgrid[0:h, 0:w]
base = np.stack([ (40 + xx * 0.2).astype(np.uint8),
                  (60 + yy * 0.3).astype(np.uint8),
                  (90 + xx * 0.1).astype(np.uint8) ], axis=2)
base[100:140, 200:400] = (230, 225, 210)      # 文字块
noise = rng.integers(-12, 13, (h, w, 1))
base = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)
app._enter_edit(base, np.ones((h, w), bool))
app.tol_var.set(8)
cx, cy = app._to_cv(app.prev, 300, 120)
app._wand(cx, cy)
n_sel = int(app.sel.sum())
root.update_idletasks()
t = time.perf_counter()
app._render_edit()
ms = (time.perf_counter() - t) * 1000
print(f"  选中 {n_sel} 像素 -> _render_edit {ms:.1f} ms, 图元 {len(app.prev.find_all())}")
print(f"  这就是用户点一下魔术棒后界面卡住的原因")

root.destroy()