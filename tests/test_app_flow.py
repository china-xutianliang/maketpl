"""GUI 行为回归：真的建窗口，但不点真鼠标、不弹对话框。"""
import os
import queue
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from maketpl import app as appmod  # noqa: E402
from maketpl.app import MakeTplApp  # noqa: E402


def _pump(root, secs=0.3):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        root.update_idletasks()
        root.update()
        time.sleep(0.01)


def _settle(root, app, limit=6.0):
    """等布局真的稳定（连续几次读数不变且没有待执行的自适应任务），而不是睡固定时长。"""
    end = time.monotonic() + limit
    seen, stable = None, 0
    while time.monotonic() < end:
        _pump(root, 0.08)
        now = (root.winfo_width(), root.winfo_height(), app.src.winfo_height(),
               app.prev.winfo_height(), app._fit_job is None)
        stable = stable + 1 if now == seen else 0
        seen = now
        if stable >= 4 and now[-1]:
            return


def _scene():
    f = np.full((120, 160, 3), 90, np.uint8)
    f[40:80, 50:110] = (200, 120, 30)
    return f


class AppFlowTest(unittest.TestCase):
    def setUp(self):
        self.root = ctk.CTk()
        self.app = MakeTplApp(self.root)
        self.addCleanup(self.root.destroy)

    def test_static_shot_uses_the_frame_you_framed_even_when_window_bound(self):
        """绑了窗口也不重抓：暂停定格后画面变了，截的必须还是框选时看到的那一帧。"""
        app = self.app
        app.live_var.set(False)                # 不起直播线程
        app.hwnd = 12345                       # 假句柄：只要不被拿去抓图就行
        self.addCleanup(setattr, app, "hwnd", None)
        app.frame = _scene()
        app.box = (45, 35, 115, 85)
        with mock.patch.object(app, "_grab_frame",
                               side_effect=AssertionError("不该重抓")):
            app.static_shot()
        self.assertTrue(app.editing)
        self.assertTrue(np.array_equal(app.base, app.frame[35:85, 45:115]))
        self.assertEqual(app.base_origin, (45, 35))

    def test_static_shot_rejects_box_outside_a_resized_frame(self):
        app = self.app
        app.frame = _scene()
        app.box = (100, 60, 400, 300)
        with mock.patch.object(appmod.messagebox, "showwarning") as warn:
            app.single_frame()
        self.assertFalse(app.editing)
        self.assertTrue(warn.called)

    def test_loading_a_transparent_png_keeps_its_alpha_for_re_editing(self):
        app = self.app
        rgba = np.zeros((40, 60, 4), np.uint8)
        rgba[:, :, :3] = (10, 200, 10)
        rgba[10:30, 10:50, 3] = 255
        path = os.path.join(tempfile.mkdtemp(prefix="mt_"), "t.png")
        Image.fromarray(rgba).save(path)
        with mock.patch.object(appmod.filedialog, "askopenfilename", return_value=path):
            app.load_image()
        self.assertIsNotNone(app.frame_alpha)
        app.box = (0, 0, 60, 40)
        app.single_frame()
        self.assertTrue(app.editing)
        self.assertEqual(int(app.mask.sum()), 20 * 40)
        self.assertTrue(app.mask[10:30, 10:50].all())

    def test_loading_a_plain_image_has_no_alpha(self):
        app = self.app
        path = os.path.join(tempfile.mkdtemp(prefix="mt_"), "p.png")
        Image.fromarray(_scene()).save(path)
        with mock.patch.object(appmod.filedialog, "askopenfilename", return_value=path):
            app.load_image()
        self.assertIsNone(app.frame_alpha)
        self.assertTrue(app.frame_from_image)

    def test_save_writes_png_only_with_source_metadata(self):
        app = self.app
        app.frame = _scene()
        app.box = (30, 20, 130, 100)
        app.single_frame()
        cx, cy = app._to_cv(app.prev, 30, 30)    # base 里橙色块范围 20..80 x 20..60
        app._wand(cx, cy)
        app.invert()
        folder = tempfile.mkdtemp(prefix="mt_")
        target = os.path.join(folder, "npc")     # 故意不带扩展名
        with mock.patch.object(appmod.filedialog, "asksaveasfilename",
                               return_value=target) as ask:
            app.save()
        types = ask.call_args.kwargs["filetypes"]
        self.assertTrue(all("*.png" in t[1] for t in types), "不该再提供 BMP 选项")
        out = target + ".png"
        self.assertTrue(os.path.isfile(out))
        with Image.open(out) as im:
            self.assertEqual(im.mode, "RGBA")
            arr = np.array(im)
            self.assertEqual(im.text["mhxy.origin"], "50,40")
            self.assertEqual(im.text["mhxy.size"], f"{arr.shape[1]}x{arr.shape[0]}")
        self.assertEqual(arr.shape[:2], (40, 60))
        self.assertTrue(set(np.unique(arr[:, :, 3])) <= {0, 255}, "alpha 必须是二值")
        self.assertTrue((arr[:, :, 3] == 255).all())

    def test_test_match_keeps_edit_state(self):
        """测试匹配后还在修图态：不满意要接着改，退出会把手修的结果丢光。"""
        app = self.app
        app.frame = _scene()
        app.box = (45, 35, 115, 85)
        app.single_frame()
        cx, cy = app._to_cv(app.prev, 30, 30)
        app._wand(cx, cy)
        app.invert()
        mask_before = app.mask.copy()
        # 没有 mainloop 时工作线程不能直接 root.after：改成队列，由测试主线程派发
        posted = queue.Queue()
        app._post = lambda fn, *a: posted.put((fn, a))
        app.test_match()
        for _ in range(200):
            _pump(self.root, 0.02)
            while not posted.empty():
                fn, a = posted.get()
                fn(*a)
            if not app._test_running:
                break
        self.assertFalse(app._test_running)
        self.assertTrue(app.editing)
        self.assertTrue(np.array_equal(app.mask, mask_before))
        self.assertTrue(app.undo, "撤销栈不该被清空")
        self.assertTrue(app.src.find_withtag("hit"), "左侧该画出命中框")

    def test_labels_are_not_garbled(self):
        """界面文字写坏成 ?? 时单元测试以前发现不了（曾经出过一次）。"""
        app = self.app
        for name, text in (("static_btn", "静态截图"), ("dyn_btn", "动态截图"),
                           ("save_btn", "保存透明 PNG"), ("test_btn", "测试匹配"),
                           ("shrink_btn", "收边 1px"), ("main_btn", "只留最大块")):
            self.assertEqual(getattr(app, name).cget("text"), text, name)
        self.assertEqual(app.coord_var.get(), "相对：—")
        src = open(appmod.__file__, encoding="utf-8").read()
        self.assertNotIn("???", src, "app.py 里有被写成问号的中文")

    def test_wand_selects_noisy_sprite_with_default_tolerance(self):
        """游戏截图有噪点：默认容差下点一下要整片选中，不能只选到一两个像素（曾出现"点了没反应"）。"""
        app = self.app
        rng = np.random.default_rng(1)
        frame = np.full((120, 160, 3), (70, 120, 60), np.uint8)
        body = np.full((50, 60, 3), (235, 150, 60), np.int16)
        body = (body + rng.integers(-14, 15, body.shape)).clip(0, 255).astype(np.uint8)
        frame[30:80, 40:100] = body
        app.frame = frame
        app.box = (30, 20, 130, 100)
        app.single_frame()
        self.assertEqual(app.wand_tol_var.get(), appmod.WAND_TOL)
        cx, cy = app._to_cv(app.prev, 30, 25)      # base 里身体的中心附近
        app._wand(int(cx), int(cy))
        self.assertGreater(int(app.sel.sum()), 50 * 60 * 0.9)
        self.assertFalse(app.sel[:, :5].any(), "不该漏到绿色背景上")

    def test_test_match_defaults_equal_mhxy_defaults(self):
        self.assertEqual(self.app.mtol_var.get(), "24")
        self.assertEqual(self.app.score_var.get(), "10")

    def test_shrink_and_keep_main_are_undoable(self):
        app = self.app
        app.frame = _scene()
        app.box = (45, 35, 115, 85)
        app.single_frame()
        n0 = int(app.mask.sum())
        app.shrink_edge()
        self.assertLess(int(app.mask.sum()), n0)
        app.undo_step()
        self.assertEqual(int(app.mask.sum()), n0)
        app.mask[0:2, 0:2] = False
        app.mask[3, 3] = False          # 制造一个孤立点
        app.mask[:] = False
        app.mask[10:30, 10:50] = True
        app.mask[2, 2] = True
        app.keep_main()
        self.assertFalse(app.mask[2, 2])
        self.assertTrue(app.mask[10:30, 10:50].all())


class LayoutTest(unittest.TestCase):
    """窗口再矮，主按钮也必须在可视区内；窄窗口里控件不能越界。"""

    def _boot(self, w, h):
        root = ctk.CTk()
        self.addCleanup(root.destroy)
        app = MakeTplApp(root)
        app.frame = _scene()
        app._show_src(app.frame)
        root.geometry(f"{w}x{h}+0+0")
        _settle(root, app)
        return root, app

    def _inside(self, root, widget):
        r = root
        return (widget.winfo_rooty() >= r.winfo_rooty()
                and widget.winfo_rooty() + widget.winfo_height()
                <= r.winfo_rooty() + r.winfo_height()
                and widget.winfo_rootx() >= r.winfo_rootx()
                and widget.winfo_rootx() + widget.winfo_width()
                <= r.winfo_rootx() + r.winfo_width())

    def test_primary_buttons_visible_at_min_size(self):
        root, app = self._boot(880, 620)
        for name in ("static_btn", "dyn_btn", "save_btn", "test_btn"):
            self.assertTrue(self._inside(root, getattr(app, name)), name)

    def test_primary_buttons_visible_at_large_size(self):
        root, app = self._boot(1280, 900)
        for name in ("static_btn", "dyn_btn", "save_btn", "test_btn"):
            self.assertTrue(self._inside(root, getattr(app, name)), name)

    def test_canvas_grows_with_window(self):
        root, app = self._boot(900, 640)
        small = app.src.winfo_height()
        root.geometry("900x860+0+0")
        _settle(root, app)
        self.assertGreater(app.src.winfo_height(), small + 40)

    def test_bound_row_never_overflows_left_column(self):
        root, app = self._boot(880, 620)
        app.target_var.set("python.exe   1200×860   hwnd=1234567")
        app._set_fid((False, "⚠ 显示缩放 125%，截到的不是原始像素，请把副机显示缩放改成 100% 并重启游戏后再截"))
        _settle(root, app)
        vp = app.left._parent_canvas
        limit = vp.winfo_rootx() + vp.winfo_width()
        self.assertLessEqual(app.unbind_btn.winfo_rootx() + app.unbind_btn.winfo_width(),
                             limit + 1)
        self.assertLessEqual(app.fid_lab.winfo_rootx() + app.fid_lab.winfo_width(),
                             limit + 1)


if __name__ == "__main__":
    unittest.main()
