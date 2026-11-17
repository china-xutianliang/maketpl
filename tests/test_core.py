import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maketpl import core  # noqa: E402


def _frame(fill=0):
    return np.full((20, 30, 3), fill, np.uint8)


def _frames(n=6, fill=0):
    return [_frame(fill) for _ in range(n)]


class StableMaskTest(unittest.TestCase):
    def test_all_identical_keeps_everything(self):
        mask = core.stable_mask(_frames())
        self.assertTrue(mask.all())

    def test_static_text_kept_noise_dropped(self):
        frames = _frames()
        for f in frames:
            f[5:10, 5:15] = (200, 120, 30)
        rng = np.random.default_rng(7)
        for f in frames:
            f[12:15, 20:25] = rng.integers(0, 255, (3, 5, 3), np.uint8)
        mask = core.stable_mask(frames)
        self.assertTrue(mask[5:10, 5:15].all())
        self.assertFalse(mask[12:15, 20:25].any())

    def test_minority_change_dropped(self):
        frames = _frames()
        for f in frames[:2]:
            f[3, 3] = 255
        mask = core.stable_mask(frames)
        self.assertFalse(mask[3, 3])
        mask = core.stable_mask(frames, min_count=4)
        self.assertTrue(mask[3, 3])

    def test_half_half_dropped(self):
        frames = _frames()
        for f in frames[3:]:
            f[3, 3] = (100, 100, 100)
        mask = core.stable_mask(frames, min_count=3)
        self.assertFalse(mask[3, 3])

    def test_tol(self):
        frames = _frames()
        for i, f in enumerate(frames):
            f[0, 0] = i * 3
        self.assertFalse(core.stable_mask(frames, tol=2)[0, 0])
        self.assertTrue(core.stable_mask(frames, tol=10)[0, 0])

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            core.stable_mask([_frame()])
        with self.assertRaises(ValueError):
            core.stable_mask([_frame(), _frame()], min_count=5)
        with self.assertRaises(ValueError):
            core.stable_mask([_frame(), _frame()[:, :10]])


class ComposeTest(unittest.TestCase):
    def test_compose_alpha_and_crop(self):
        frames = _frames()
        for f in frames:
            f[5:10, 5:15] = (200, 120, 30)
        rng = np.random.default_rng(1)
        for f in frames:
            f[:4] = rng.integers(0, 255, (4, 30, 3), np.uint8)
        rgba, mask, kept = core.build(frames)
        self.assertEqual(kept, int(mask.sum()))
        self.assertEqual(rgba.shape, (16, 30, 4))
        self.assertTrue((rgba[:, :, 3] == 255).all())
        hit = np.nonzero(np.all(rgba[:, :, :3] == (200, 120, 30), axis=2))
        self.assertEqual(len(hit[0]), 5 * 10)

    def test_crop_pad(self):
        frames = _frames()
        for f in frames:
            f[5:10, 5:15] = 99
        mask = np.zeros((20, 30), bool)
        mask[5:10, 5:15] = True
        rgba = core.compose_rgba(frames, mask)
        cropped = core.crop_to_content(rgba, pad=2)
        self.assertEqual(cropped.shape, (9, 14, 4))

    def test_all_noise_raises(self):
        rng = np.random.default_rng(3)
        frames = [rng.integers(0, 255, (20, 30, 3), np.uint8) for _ in range(6)]
        with self.assertRaises(ValueError):
            core.build(frames)


class FloodFillTest(unittest.TestCase):
    def _img(self):
        img = np.full((10, 12, 3), 200, np.uint8)  # 灰底
        img[3:6, 3:8] = (10, 20, 30)               # 中间一块深色"字"
        return img

    def test_fill_contiguous_background(self):
        mask = core.flood_fill(self._img(), (0, 0), tol=8)
        self.assertFalse(mask[4, 4])            # 字没被吃
        self.assertTrue(mask[9, 11])            # 远处同色底也被连到（绕过去）
        self.assertEqual(int(mask.sum()), 120 - 15)

    def test_fill_respects_tol(self):
        img = self._img()
        img[8, 8] = (190, 195, 200)             # 和底色差一点点，孤立
        img[8, 9] = 150
        mask = core.flood_fill(img, (0, 0), tol=4)
        self.assertFalse(mask[8, 8])
        self.assertTrue(core.flood_fill(img, (0, 0), tol=16)[8, 8])

    def test_fill_seed_on_object(self):
        mask = core.flood_fill(self._img(), (4, 5), tol=8)
        self.assertEqual(int(mask.sum()), 15)   # 只有字块
        self.assertTrue(mask[3:6, 3:8].all())

    def test_disc(self):
        m = core.disc((20, 20), (10, 10), 3)
        self.assertTrue(m[10, 10] and m[10, 13] and m[7, 10])
        self.assertFalse(m[10, 14] or m[6, 10])

    def test_color_region_not_contiguous(self):
        img = np.full((10, 12, 3), 200, np.uint8)
        img[3:6, 3:8] = (10, 20, 30)
        img[0, 0] = 200
        # 用另一个 200 色块当种子：全图同色把两块都收进来，无视连通
        img[9, 11] = 200
        region = core.color_region(img, (0, 0), tol=4)
        self.assertEqual(int(region.sum()), 120 - 15)
        self.assertTrue(region[9, 11])
        self.assertFalse(region[4, 4])

    def test_color_region_tol(self):
        img = np.full((6, 6, 3), 100, np.uint8)
        img[2, 2] = 110
        self.assertFalse(core.color_region(img, (0, 0), tol=4)[2, 2])
        self.assertTrue(core.color_region(img, (0, 0), tol=16)[2, 2])

    def test_remove_small(self):
        mask = np.zeros((12, 12), bool)
        mask[1:4, 1:4] = True   # 9 像素块
        mask[8, 8] = True       # 孤点
        mask[9, 10] = True      # 2 像素块
        out = core.remove_small(mask, 4)
        self.assertTrue(out[2, 2])
        self.assertFalse(out[8, 8] or out[9, 10])
        out = core.remove_small(mask, 10)
        self.assertFalse(out.any())
        # 斜着贴不算连通（4 连通）
        mask2 = np.zeros((4, 4), bool)
        mask2[0, 0] = mask2[1, 1] = True
        self.assertFalse(core.remove_small(mask2, 1).any())

    def test_split_phases(self):
        base = np.zeros((10, 10, 3), np.uint8)
        a, b = base.copy(), base.copy()
        a[2:8, 2:8] = (255, 0, 0)   # 大红块
        b[2:8, 2:8] = (0, 255, 0)   # 大绿块
        frames = [a, a, b, a, b, b, a]
        groups = core.split_phases(frames, tol=12)
        self.assertEqual(sorted(groups), [[0, 1, 3, 6], [2, 4, 5]])
        # 都差不多 → 一组
        same = [a, a.copy(), a.copy()]
        self.assertEqual(core.split_phases(same), [[0, 1, 2]])

    def test_compose_from_base(self):
        base = self._img()
        mask = ~core.flood_fill(base, (0, 0), tol=8)  # 留字挖底
        rgba = core.compose_from_base(base, mask)
        self.assertTrue((rgba[mask, 3] == 255).all() and (rgba[~mask, 3] == 0).all())
        self.assertTrue((rgba[4, 4, :3] == (10, 20, 30)).all())


if __name__ == "__main__":
    unittest.main()
