"""GUI 冒烟测试：把窗口真正建起来再销毁，抓 NameError 这类一跑就炸的问题。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk  # noqa: E402

from maketpl.app import MakeTplApp  # noqa: E402


class AppSmokeTest(unittest.TestCase):
    def test_build_and_idle(self):
        root = ctk.CTk()
        try:
            app = MakeTplApp(root)
            root.update_idletasks()
            root.update()
            self.assertFalse(app.editing)
            self.assertIsNone(app.hwnd)
        finally:
            root.destroy()

    def test_static_shot_without_window(self):
        """没绑窗口、只载入图片时，「静态截图」也应能进修图。"""
        import numpy as np

        root = ctk.CTk()
        try:
            app = MakeTplApp(root)
            app.frame = np.full((80, 100, 3), 180, np.uint8)
            app.box = (10, 10, 70, 60)
            app.static_shot()
            self.assertTrue(app.editing)
            self.assertEqual(app.base.shape, (50, 60, 3))
        finally:
            root.destroy()

    def test_edit_flow_headless(self):
        """不点真鼠标：塞一帧→框选→单帧新建→魔术棒+反选→裁剪→撤销。"""
        import numpy as np

        root = ctk.CTk()
        try:
            app = MakeTplApp(root)
            frame = np.full((100, 120, 3), 180, np.uint8)
            frame[40:60, 40:80] = (200, 120, 30)
            app.frame = frame
            app.box = (30, 30, 90, 70)
            app.single_frame()
            self.assertTrue(app.editing)
            self.assertTrue(app.mask.all())
            # 魔术棒点橙色块选中要保留的，反选透明后只剩字
            app.tol_var.set(8)
            cx, cy = app._to_cv(app.prev, 20, 20)
            app._wand(cx, cy)
            self.assertTrue(app.sel.any())
            app.invert()
            self.assertFalse(app.mask.all())
            # 文字块在基准图里的范围 x10-49 y10-29，该留着
            self.assertTrue(app.mask[12:28, 12:48].all())
            # 放大后 图像坐标 ↔ 画布坐标 仍要对得上
            app._zoom_by(4.0)
            self.assertGreater(app._zoom_scale(), 1.0)
            ax, ay = app._to_cv(app.prev, 20.5, 20.5)
            self.assertEqual(app._to_img(app.prev, ax, ay), (20, 20))
            app._zoom_fit()
            # 框选擦除（拖矩形去像素）、撤销能跑
            app._crop_to(5, 5, 35, 35)
            self.assertEqual(app.mask.shape, (40, 60))      # 尺寸不变
            self.assertFalse(app.mask[5:35, 5:35].any())    # 框内擦成透明
            app.undo_step()
            self.assertTrue(app.editing)
        finally:
            root.destroy()

    def test_wand_ps_behavior(self):
        """魔术棒按 PS 习惯：点选连通一片，Shift+点加选，Alt+点减选，透明区不选。"""
        import numpy as np

        root = ctk.CTk()
        try:
            app = MakeTplApp(root)
            img = np.full((40, 80, 3), 180, np.uint8)
            img[10:20, 10:20] = (200, 120, 30)   # 左橙块
            img[10:20, 60:70] = (200, 120, 30)   # 右橙块（同色不连通）
            app._enter_edit(img, np.ones((40, 80), bool))
            app.wand_tol_var.set(8)

            # 连通：点左块只选左块，右块不动
            cx, cy = app._to_cv(app.prev, 15, 15)
            app._wand(cx, cy)
            self.assertTrue(app.sel[10:20, 10:20].all())
            self.assertFalse(app.sel[10:20, 60:70].any())

            # Shift+点：右块加进来
            cx, cy = app._to_cv(app.prev, 65, 15)
            app._wand(cx, cy, add=True)
            self.assertTrue(app.sel[10:20, 60:70].all())

            # Alt+点：左块减出去
            cx, cy = app._to_cv(app.prev, 15, 15)
            app._wand(cx, cy, sub=True)
            self.assertFalse(app.sel[10:20, 10:20].any())
            self.assertTrue(app.sel[10:20, 60:70].all())

            # 已透明像素不参与选择
            app.mask[25:35, 25:35] = False
            cx, cy = app._to_cv(app.prev, 30, 30)
            app._wand(cx, cy)
            self.assertFalse((app.sel & ~app.mask).any())

            # 关掉「只选连通」：点一次全图同色都选
            app.contig_var.set(False)
            cx, cy = app._to_cv(app.prev, 15, 15)
            app._wand(cx, cy)
            self.assertTrue(app.sel[10:20, 10:20].all())
            self.assertTrue(app.sel[10:20, 60:70].all())
        finally:
            root.destroy()

    def test_brush_and_pan(self):
        """画笔补/橡皮擦、点选与拖动平移共存：点击=选区，拖>5px=平移。"""
        import numpy as np

        root = ctk.CTk()
        try:
            app = MakeTplApp(root)
            img = np.full((30, 30, 3), 180, np.uint8)
            app._enter_edit(img, np.ones((30, 30), bool))
            app.brush_var.set(3)

            # 画笔补回 / 橡皮擦除（一笔一个撤销点）
            app._brush_mode = "paint"
            cx, cy = app._to_cv(app.prev, 15, 15)
            app._brush_apply(cx, cy, keep=False, first=True)
            self.assertFalse(app.mask[15, 15])
            self.assertEqual(int(app.undo[-1][1].sum()), 900)
            app._brush_apply(cx, cy, keep=True, first=True)
            self.assertTrue(app.mask[15, 15])
            app._brush_mode = None

            # 模拟点击（按下+原地松开）→ 魔术棒选中
            class E:
                def __init__(self, x, y, state=0, num=1):
                    self.widget = app.prev
                    self.x, self.y, self.state, self.num = x, y, state, num
            x0, y0 = app._to_cv(app.prev, 15, 15)
            app._press(E(x0, y0, num=1))
            self.assertIsNotNone(app._wand_pending)
            app._release(E(x0, y0, num=1))
            self.assertTrue(app.sel.any())

            # 模拟拖动（按下+移动>5px）→ 平移而不是点选（放大后才有得平）
            app.sel[:] = False
            app.zoom = 40.0   # 保证 30px 的图放大后超出画布，平移才有空间
            vc0 = app._zoom_center()
            app._press(E(x0, y0, num=1))
            app._drag_move(E(x0 + 40, y0 + 10, num=1))
            self.assertIsNone(app._wand_pending)
            app._drag_move(E(x0 + 50, y0 + 12, num=1))
            app._release(E(x0 + 50, y0 + 12, num=1))
            self.assertFalse(app.sel.any())
            self.assertNotEqual(app._zoom_center(), vc0)
        finally:
            root.destroy()

    def test_dyn_monitor_ignores_live_switch(self):
        """动采监控视角：实时画面开关关掉也要播选区帧（定格框选→动采的常见姿势）。"""
        import numpy as np

        root = ctk.CTk()
        try:
            app = MakeTplApp(root)
            app.hwnd = 12345
            app.frame = np.zeros((200, 300, 3), np.uint8)
            app.box = (10, 10, 110, 60)
            app._dyn = True
            app._dyn_box = app.box
            app._live_show = False   # 用户为定格框选关掉了实时画面
            app._live_on = True

            self.assertEqual(len(app.src.find_withtag("img")), 0)
            f = np.random.randint(0, 255, (50, 100, 3), np.uint8)
            app._live_apply(f, f.copy(), app._dyn_box, 3, None)
            self.assertEqual(len(app.src.find_withtag("img")), 1)
            self.assertEqual(app._view_off, (10, 10))
            self.assertEqual(app._src_img.shape, (50, 100, 3))

            # 整窗帧（启动时在飞的旧帧）：开关关着就不该画到画布
            app.src.delete("img")
            full = np.zeros((200, 300, 3), np.uint8)
            app._live_apply(full, full.copy(), None, 0, None)
            self.assertEqual(len(app.src.find_withtag("img")), 0)
        finally:
            root.destroy()

    def test_bind_rejects_bad_hwnd(self):
        """无效句柄、自己进程的窗口都不能绑上。"""
        root = ctk.CTk()
        try:
            app = MakeTplApp(root)
            root.update_idletasks()
            app._bind_hwnd(0)
            self.assertIsNone(app.hwnd)
            app._bind_hwnd(root.winfo_id())
            self.assertIsNone(app.hwnd)
        finally:
            root.destroy()

    def test_unbind(self):
        """解绑：hwnd 清空、直播开关关掉、目标行还原。"""
        root = ctk.CTk()
        try:
            app = MakeTplApp(root)
            root.update_idletasks()
            app.hwnd = 12345
            app.live_var.set(True)
            app.unbind()
            self.assertIsNone(app.hwnd)
            self.assertFalse(app.live_var.get())
            self.assertEqual(app.unbind_btn.cget("state"), "disabled")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
