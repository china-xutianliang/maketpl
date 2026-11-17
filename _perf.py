"""临时性能/线程探针。用完即删。"""
import time
import numpy as np
import customtkinter as ctk
from maketpl.app import MakeTplApp

root = ctk.CTk()
app = MakeTplApp(root)
root.update_idletasks()
root.update()

print("=" * 68)
print("性能：_render_edit 单次耗时（每次魔术棒/缩放/平移/撤销都要跑）")
print("=" * 68)
rng = np.random.default_rng(3)
for (h, w) in [(60, 120), (200, 400), (400, 800), (600, 1000)]:
    base = rng.integers(0, 255, (h, w, 3), np.uint8)
    app._enter_edit(base, np.ones((h, w), bool))
    root.update_idletasks()
    t = time.perf_counter()
    for _ in range(5):
        app._render_edit()
    dt = (time.perf_counter() - t) / 5 * 1000
    # 选中一半像素时的描边开销
    app.sel = np.zeros((h, w), bool)
    app.sel[::2, ::2] = True                 # 棋盘状选区 = 描边最坏情况
    t = time.perf_counter()
    app._render_edit()
    dt_sel = (time.perf_counter() - t) * 1000
    items = len(app.prev.find_all())
    print(f"  {w}x{h}: 无选区 {dt:7.1f} ms | 碎选区 {dt_sel:8.1f} ms | 画布图元 {items}")

print()
print("=" * 68)
print("性能：_draw_sel_outline 的 Python 逐行逐列循环")
print("=" * 68)
h, w = 400, 800
base = np.full((h, w, 3), 100, np.uint8)
app._enter_edit(base, np.ones((h, w), bool))
app.sel = np.zeros((h, w), bool)
app.sel[50:350, 100:700] = True              # 一整块矩形选区（正常用法）
root.update_idletasks()
t = time.perf_counter()
app._draw_sel_outline(1.0, 0.0, 0.0)
print(f"  矩形选区 600x300 描边: {(time.perf_counter()-t)*1000:.1f} ms, "
      f"图元 {len(app.prev.find_withtag('selout'))}")
app.prev.delete("selout")
app.sel[::2, ::2] = True                     # 碎选区
t = time.perf_counter()
app._draw_sel_outline(1.0, 0.0, 0.0)
print(f"  棋盘碎选区同尺寸描边: {(time.perf_counter()-t)*1000:.1f} ms, "
      f"图元 {len(app.prev.find_withtag('selout'))}")

print()
print("=" * 68)
print("线程安全：_post 直接在工作线程里调 root.after（tkinter 非线程安全）")
print("=" * 68)
import inspect
print(inspect.getsource(app._post))
print("  调用方 _live_loop 是 threading.Thread 的工作线程 -> 跨线程操作 Tk 解释器")
print("  复现脚本里已实际抛出: RuntimeError: main thread is not in main loop")

print()
print("=" * 68)
print("点击映射 vs 实际绘制位置（_render_edit 用 round，_to_img 用精确浮点）")
print("=" * 68)
big = np.zeros((400, 1200, 3), np.uint8)
app._enter_edit(big, np.ones((400, 1200), bool))
root.update_idletasks(); root.update()
s, cx, cy, ox, oy, ix0, iy0, ix1, iy1 = app._edit_geometry()
crop = app._view[iy0:iy1, ix0:ix1]
dw = max(1, int(round(crop.shape[1] * s)))
dh = max(1, int(round(crop.shape[0] * s)))
drawn_x = int(round(ox + ix0 * s))
print(f"  适应缩放 s={s:.6f}, 裁剪块 {crop.shape[1]}x{crop.shape[0]} -> 绘制 {dw}x{dh}")
print(f"  实际每图像像素占画布 {dw/crop.shape[1]:.6f}，但 _to_img 按 {s:.6f} 反算")
worst = 0
for ix in range(0, 1200, 37):
    real_canvas_x = drawn_x + (ix - ix0) * dw / crop.shape[1]
    back_ix, _ = app._to_img(app.prev, int(round(real_canvas_x)), 10)
    worst = max(worst, abs(back_ix - ix))
print(f"  >>> 往返最大偏差 {worst} 图像像素（偏差>0 就会点到隔壁颜色）")

root.destroy()