import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maketpl import core, findimg  # noqa: E402


def _tpl_rgba():
    tpl = np.zeros((10, 14, 4), np.uint8)
    tpl[:, :, 3] = 255
    tpl[2:7, 3:10, :3] = (200, 120, 30)  # 字块
    tpl[:2, :, 3] = tpl[7:, :, 3] = 0    # 上下两边透明
    tpl[:, :3, 3] = tpl[:, 10:, 3] = 0   # 左右两边透明
    return tpl


class FindImgTest(unittest.TestCase):
    def setUp(self):
        self.frame = np.full((200, 300, 3), 90, np.uint8)
        self.frame[50:60, 100:114] = (120, 40, 200)   # 模板位置（透明区的颜色无所谓）

    def test_hit_with_alpha(self):
        tpl = _tpl_rgba()
        # 有效区颜色填到画面里
        self.frame[52:57, 103:110] = (200, 120, 30)
        hit = findimg.find_best(self.frame, tpl, tol=8, max_score=2.0)
        self.assertIsNotNone(hit)
        self.assertEqual((hit.x, hit.y), (100, 50))
        self.assertLess(hit.score, 1.0)

    def test_transparent_pixels_ignored(self):
        """把模板透明区底下的画面换成另一种颜色，照样命中——证明透明像素不参与。"""
        tpl = _tpl_rgba()
        self.frame[50:60, 100:114] = (10, 200, 60)   # 透明区底下随便什么颜色
        self.frame[52:57, 103:110] = (200, 120, 30)  # 有效区对
        hit = findimg.find_best(self.frame, tpl, tol=8, max_score=2.0)
        self.assertIsNotNone(hit)

    def test_miss_when_pixels_wrong(self):
        tpl = _tpl_rgba()
        hit = findimg.find_best(self.frame, tpl, tol=8, max_score=2.0)
        self.assertIsNone(hit)  # 有效区颜色不对

    def test_too_few_pixels(self):
        tpl = np.zeros((8, 8, 4), np.uint8)
        tpl[0, 0, 3] = tpl[0, 1, 3] = tpl[1, 0, 3] = 255  # 只有 3 个有效像素
        with self.assertRaises(ValueError):
            findimg.find_all(self.frame, tpl)


class VaryMaskTest(unittest.TestCase):
    def test_keep_only_changed(self):
        frames = [np.zeros((10, 10, 3), np.uint8) for _ in range(6)]
        for f in frames:
            f[2:5, 2:5] = (200, 120, 30)      # 不动的字
        for i, f in enumerate(frames):
            f[7, 7] = i * 40                   # 动的点
        mask = core.vary_mask(frames, tol=8)
        self.assertTrue(mask[7, 7])
        self.assertFalse(mask[3, 3] or mask[0, 0])


if __name__ == "__main__":
    unittest.main()
