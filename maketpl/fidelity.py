"""判断截到的画面是不是游戏的原始像素（1:1）。

识图模板必须来自 100% 缩放下的原始画面：窗口被系统缩放过，截到的像素和第三层
运行时看到的就对不上。这里只做纯判断，不碰 Win32，方便单测。
"""
from __future__ import annotations

# 第三层的坐标、ROI 都按这个客户区尺寸设计
EXPECT_CLIENT = (800, 600)
BASE_DPI = 96


def _pct(dpi: int) -> int:
    return round(dpi * 100 / BASE_DPI)


def assess(client: tuple[int, int], win_dpi: int = BASE_DPI, screen_dpi: int = BASE_DPI,
           expect: tuple[int, int] = EXPECT_CLIENT) -> tuple[bool, str]:
    """返回 (是否可放心做模板, 一行说明)。

    不是 100% 缩放是硬问题（像素被拉伸过）；客户区不是 800×600 是提醒
    （第三层按 800×600 设计，别的尺寸模板位置/大小可能对不上）。
    """
    w, h = client
    problems: list[str] = []
    # 窗口自己的 DPI 和它所在显示器的 DPI 都要看：游戏进程不感知缩放时，
    # 窗口 DPI 会假报 96，只有显示器 DPI 才露馅
    dpis = {d for d in (win_dpi, screen_dpi) if d and d != BASE_DPI}
    if dpis:
        shown = "/".join(f"{_pct(d)}%" for d in sorted(dpis))
        problems.append(f"显示缩放 {shown}，截到的不是原始像素，"
                        "请把副机显示缩放改成 100% 并重启游戏后再截")
    if (w, h) != tuple(expect):
        problems.append(f"客户区 {w}×{h}，第三层按 {expect[0]}×{expect[1]} 识图，"
                        "模板的位置和大小可能对不上")
    if problems:
        return False, "⚠ " + "；".join(problems)
    return True, f"✓ 原始像素 1:1 · 客户区 {w}×{h} · 缩放 100%"
