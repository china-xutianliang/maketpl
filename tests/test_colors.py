import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maketpl import colors  # noqa: E402


class DescTest(unittest.TestCase):
    def test_roundtrip(self):
        rgb, diff = colors.parse_desc("a0b0c0-101520")
        self.assertTrue((rgb == (0xA0, 0xB0, 0xC0)).all())
        self.assertTrue((diff == (0x10, 0x15, 0x20)).all())
        self.assertEqual(colors.format_desc(rgb, diff), "a0b0c0-101520")

    def test_no_diff(self):
        rgb, diff = colors.parse_desc("ffffff")
        self.assertTrue((diff == 0).all())

    def test_bad(self):
        for bad in ("xyz", "fff-101010", "ffffff-1010"):
            with self.assertRaises(ValueError):
                colors.parse_desc(bad)


class FindColorTest(unittest.TestCase):
    def setUp(self):
        self.img = np.full((40, 50, 3), 100, np.uint8)
        self.img[10, 20] = (250, 100, 50)
        self.img[30, 40] = (255, 105, 55)

    def test_exact(self):
        hits = colors.find_color(self.img, (250, 100, 50), (0, 0, 0))
        self.assertEqual(hits, [(20, 10)])

    def test_tol(self):
        hits = colors.find_color(self.img, (250, 100, 50), (10, 10, 10))
        self.assertEqual(sorted(hits), [(20, 10), (40, 30)])

    def test_region(self):
        hits = colors.find_color(self.img, (250, 100, 50), (10, 10, 10),
                                 region=(0, 0, 30, 20))
        self.assertEqual(hits, [(20, 10)])


class MultiTest(unittest.TestCase):
    def test_roundtrip_and_find(self):
        img = np.full((40, 50, 3), 0, np.uint8)
        img[10, 20] = (255, 255, 255)
        img[12, 23] = (160, 176, 192)  # 相对锚点 (3,2)
        pts = colors.parse_multi("0|0|ffffff-000000,3|2|a0b0c0-000000")
        self.assertEqual(colors.find_multi(img, pts), [(20, 10)])
        text = colors.format_multi(pts)
        self.assertEqual(colors.find_multi(img, colors.parse_multi(text)), [(20, 10)])

    def test_partial_match_rejected(self):
        img = np.full((40, 50, 3), 0, np.uint8)
        img[10, 20] = (255, 255, 255)  # 只有锚点，没有第二点
        pts = colors.parse_multi("0|0|ffffff-000000,3|2|a0b0c0-000000")
        self.assertEqual(colors.find_multi(img, pts), [])


if __name__ == "__main__":
    unittest.main()
