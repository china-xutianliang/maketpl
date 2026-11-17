"""透明模板制作工具入口。

正常：python main.py           （或打包后的 exe 直接双击）
自检：python main.py --selftest    核心算法，不弹界面
冒烟：python main.py --smoke       真开窗口跑一遍完整做图+匹配流程
"""
from __future__ import annotations

import sys


def selftest() -> int:
    import numpy as np

    from maketpl import core

    frames = [np.zeros((20, 30, 3), np.uint8) for _ in range(6)]
    for f in frames:
        f[5:10, 5:15] = (200, 120, 30)
    rng = np.random.default_rng(7)
    for f in frames:
        f[:4] = rng.integers(0, 255, (4, 30, 3), np.uint8)
    rgba, mask, kept = core.build(frames)
    assert rgba.shape == (16, 30, 4) and kept == int(mask.sum()), "求稳结果不对"
    assert (rgba[:, :, 3] == 255).all(), "裁出来的图里不该有透明像素"
    print("selftest OK")
    return 0


def smoke() -> int:
    """真开 GUI，把"造帧→框选→单帧→魔术棒+反选→保存→findimg 回找"跑一遍。"""
    import os
    import tempfile

    import customtkinter as ctk
    import numpy as np
    from PIL import Image

    from maketpl import findimg
    from maketpl.app import MakeTplApp

    root = ctk.CTk()
    try:
        app = MakeTplApp(root)
        frame = np.full((600, 800, 3), 180, np.uint8)
        frame[200:230, 300:360] = (200, 120, 30)   # 橙色块当"字"
        rng = np.random.default_rng(9)
        frame[100:120, 600:700] = rng.integers(0, 255, (20, 100, 3), np.uint8)  # 噪音区
        app.frame = frame
        app.box = (295, 195, 370, 235)
        app.single_frame()
        assert app.editing and app.base.shape == (40, 75, 3)

        cx, cy = app._to_cv(app.prev, 20, 20)
        app._wand(cx, cy)                          # 魔术棒选橙色块（要保留）
        app.invert()                               # 反选透明 → 其余透明
        assert app.mask[10:30, 10:60].all() and not app.mask[0, 0]

        tpl = app._current_rgba()
        assert tpl.shape[:2] == (30, 60) and (tpl[:, :, 3] == 255).all()

        path = os.path.join(tempfile.mkdtemp(prefix="maketpl_"), "t.png")
        Image.fromarray(tpl).save(path)
        back = np.array(Image.open(path))
        assert back.shape == tpl.shape and (back[:, :, 3] == tpl[:, :, 3]).all(), "PNG 往返不一致"

        hit = findimg.find_best(frame, tpl, tol=8, max_score=2.0)
        assert hit is not None, "回找没命中"
        assert abs(hit.x - 300) <= 2 and abs(hit.y - 200) <= 2, f"命中位置偏了 {hit}"
        root.update_idletasks()
        root.update()
        print("SMOKE OK")
        return 0
    finally:
        root.destroy()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    if "--smoke" in sys.argv:
        raise SystemExit(smoke())
    from maketpl.app import main
    raise SystemExit(main())
