import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from maketpl import core, fidelity  # noqa: E402


class FidelityTest(unittest.TestCase):
    def test_native_800x600_is_ok(self):
        ok, text = fidelity.assess((800, 600), 96, 96)
        self.assertTrue(ok)
        self.assertIn("1:1", text)

    def test_scaled_window_is_rejected(self):
        ok, text = fidelity.assess((800, 600), 120, 120)
        self.assertFalse(ok)
        self.assertIn("125%", text)

    def test_unaware_game_on_scaled_monitor_is_caught_by_monitor_dpi(self):
        # 游戏进程不感知缩放时窗口 DPI 假报 96，只有显示器 DPI 露馅
        ok, text = fidelity.assess((800, 600), 96, 144)
        self.assertFalse(ok)
        self.assertIn("150%", text)

    def test_other_client_size_warns_but_names_the_expected_size(self):
        ok, text = fidelity.assess((1024, 768), 96, 96)
        self.assertFalse(ok)
        self.assertIn("800×600", text)
        self.assertIn("1024×768", text)

    def test_both_problems_reported_once_each(self):
        ok, text = fidelity.assess((1024, 768), 144, 144)
        self.assertFalse(ok)
        self.assertEqual(text.count("150%"), 1)
        self.assertIn("1024×768", text)


class MaskOpsTest(unittest.TestCase):
    def test_erode_shrinks_by_one(self):
        m = np.zeros((9, 9), bool)
        m[2:7, 2:7] = True
        e = core.erode(m, 1)
        self.assertEqual(int(e.sum()), 9)
        self.assertTrue(e[3:6, 3:6].all())

    def test_erode_treats_image_border_as_outside(self):
        e = core.erode(np.ones((5, 5), bool), 1)
        self.assertEqual(int(e.sum()), 9)

    def test_erode_does_not_mutate_input(self):
        m = np.ones((5, 5), bool)
        core.erode(m, 2)
        self.assertTrue(m.all())

    def test_erode_zero_is_identity(self):
        m = np.eye(4, dtype=bool)
        self.assertTrue(np.array_equal(core.erode(m, 0), m))

    def test_largest_component_drops_small_blocks(self):
        m = np.zeros((12, 12), bool)
        m[1:6, 1:6] = True        # 25
        m[8:10, 8:10] = True      # 4
        m[11, 0] = True           # 1
        out = core.largest_component(m)
        self.assertEqual(int(out.sum()), 25)
        self.assertFalse(out[8:10, 8:10].any())

    def test_largest_component_of_empty_mask(self):
        self.assertFalse(core.largest_component(np.zeros((4, 4), bool)).any())


if __name__ == "__main__":
    unittest.main()
