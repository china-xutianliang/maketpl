"""临时复现脚本：把用户报告的两个问题的真实数据打出来。用完即删。"""
import numpy as np
import customtkinter as ctk
from maketpl.app import MakeTplApp

root = ctk.CTk()
app = MakeTplApp(root)
root.update_idletasks()

print("=" * 70)
print("BUG 2 复现：动态截图还在跑时，手修结果被自动覆盖")
print("=" * 70)
# 造一个 40x60 的选区：左边橙色块(要保留)，右边灰色背景(要挖掉)
base = np.full((40, 60, 3), 180, np.uint8)
base[10:30, 10:40] = (200, 120, 30)
auto_mask = np.ones((40, 60), bool)          # 动采算出来的掩码：全保留
app._dyn = True
app._dyn_box = (0, 0, 60, 40)
app.hwnd = 1234
rect = (0, 0, 60, 40)

app._live_apply(base, None, rect, 8, (base, auto_mask))
print(f"[1] 动采第一帧自动进修图: editing={app.editing}, 保留={int(app.mask.sum())}/{app.mask.size}")
print(f"    此时 _dyn 仍为 {app._dyn}（用户没点「停止并生成」）")

cx, cy = app._to_cv(app.prev, 20, 20)        # 点橙色块
app._wand(cx, cy)
print(f"[2] 魔术棒点橙色: 选中={int(app.sel.sum())} 像素")
app.invert()
kept_after_invert = int(app.mask.sum())
print(f"[3] 反选透明后: 保留={kept_after_invert} 像素, undo 深度={len(app.undo)}")
print(f"    背景像素(0,0) 保留? {bool(app.mask[0, 0])}  <- 应为 False")

# 0.6 秒后动采又算了一次，贴上来
app._live_apply(base, None, rect, 9, (base, auto_mask))
kept_now = int(app.mask.sum())
print(f"[4] 下一帧动采结果贴上来: 保留={kept_now} 像素, undo 深度={len(app.undo)}")
print(f"    背景像素(0,0) 保留? {bool(app.mask[0, 0])}  <- 变回 True 了")
print(f">>> 结论: 用户的 {kept_after_invert} 像素被覆盖回 {kept_now} 像素，"
      f"撤销栈也被清空({len(app.undo)})，Ctrl+Z 救不回来。BUG 确认 = {kept_now != kept_after_invert}")

print()
print("=" * 70)
print("BUG 1 复现：魔术棒把不该选的颜色也选进来")
print("=" * 70)
app._dyn = False
# 一张图里有 5 种明显不同的颜色
img = np.zeros((20, 100, 3), np.uint8)
palette = [(200, 120, 30), (205, 126, 36), (190, 110, 20), (60, 60, 60), (250, 250, 250)]
for i, c in enumerate(palette):
    img[:, i * 20:(i + 1) * 20] = c
app._enter_edit(img, np.ones((20, 100), bool))

for tol in (8, 20, 32, 64):
    app.tol_var.set(tol)
    cx, cy = app._to_cv(app.prev, 10, 10)     # 点第 1 种颜色 (200,120,30)
    app._wand(cx, cy)
    cols = [i for i in range(5) if app.sel[:, i * 20 + 5].any()]
    print(f"  容差={tol:2d} -> 选中 {int(app.sel.sum()):4d} 像素，"
          f"命中调色板区块 {cols}（只想要 [0]）  多选={len(cols) > 1}")

print()
print("  说明：容差滑块是「多帧求稳」和「魔术棒」共用的同一个 tol_var。")
print("  用户为了去噪把容差调大，魔术棒就跟着变成大范围选色。")

print()
print("--- BUG 1b：魔术棒在已经挖透明的像素上照样选 ---")
app.tol_var.set(8)
m = np.ones((20, 100), bool)
m[:, 60:80] = False                          # 第 4 块(60,60,60)已被挖成透明
app.mask = m
app._render_edit()
cx, cy = app._to_cv(app.prev, 70, 10)        # 点已经透明的深灰块
app._wand(cx, cy)
print(f"  点透明区后选中={int(app.sel.sum())} 像素，"
      f"其中已透明的={int((app.sel & ~app.mask).sum())} 像素")
print(f"  >>> 反选透明会把这块透明区又「选回来」当保留区: "
      f"{bool((app.sel & ~app.mask).any())}")

print()
print("--- BUG 1c：缩小显示时点击坐标取到隔壁像素 ---")
big = np.zeros((400, 1200, 3), np.uint8)
big[:, :] = (10, 10, 10)
big[200, 600] = (255, 0, 0)                  # 只有一个红点
app._enter_edit(big, np.ones((400, 1200), bool))
root.update_idletasks()
root.update()
cx, cy = app._to_cv(app.prev, 600, 200)
ix, iy = app._to_img(app.prev, int(cx), int(cy))
print(f"  画布尺寸={app._canvas_size(app.prev)}, 适应缩放={app._zoom_scale():.4f}")
print(f"  红点(600,200) -> 画布({cx:.1f},{cy:.1f}) -> 取整点击 -> 图像({ix},{iy})")
print(f"  >>> 取到的颜色={tuple(big[iy, ix])}，是不是红点 {(ix, iy) == (600, 200)}")

root.destroy()