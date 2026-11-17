"""找色描述与匹配。

颜色描述 "rrggbb-dddddd"：主色 + 每通道允许偏差。
多点描述 "0|0|ffffff-101010,3|2|a0b0c0-151515"：第一点为基准，其余是相对偏移。
匹配规则和找图一致：每通道 |实际-期望| <= 偏差。
"""
from __future__ import annotations

import numpy as np


def parse_desc(text: str) -> tuple[np.ndarray, np.ndarray]:
    """"rrggbb-dddddd" 或 "rrggbb" → (rgb, diff)。diff 省略时全 0。"""
    t = text.strip().lower().lstrip("#")
    parts = t.split("-")
    if len(parts[0]) != 6:
        raise ValueError(f"颜色描述格式不对：{text!r}（要 rrggbb[-dddddd]）")
    rgb = np.array([int(parts[0][i:i + 2], 16) for i in (0, 2, 4)], np.uint8)
    if len(parts) == 1 or parts[1] == "":
        diff = np.zeros(3, np.uint8)
    else:
        if len(parts[1]) != 6:
            raise ValueError(f"偏色格式不对：{text!r}（要 6 位十六进制）")
        diff = np.array([int(parts[1][i:i + 2], 16) for i in (0, 2, 4)], np.uint8)
    return rgb, diff


def format_desc(rgb, diff=None) -> str:
    rgb = np.asarray(rgb).astype(int)[:3]
    d = np.zeros(3, int) if diff is None else np.asarray(diff).astype(int)[:3]
    return "%02x%02x%02x-%02x%02x%02x" % (*rgb, *d)


def gray_of(rgb) -> int:
    return int(round(float(np.asarray(rgb)[:3] @ np.array([0.299, 0.587, 0.114]))))


def match_at(img: np.ndarray, x: int, y: int, rgb, diff) -> bool:
    """单点判定：img[y,x] 是否在容差内等于 rgb。"""
    h, w = img.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return False
    d = np.abs(img[y, x, :3].astype(np.int16) - np.asarray(rgb).astype(np.int16))
    return bool(np.all(d <= np.asarray(diff).astype(np.int16)))


def find_color(img: np.ndarray, rgb, diff, region=None, max_hits: int = 32) -> list[tuple[int, int]]:
    """全图（或 region=(x1,y1,x2,y2)）找单点颜色，返回命中坐标（最多 max_hits 个）。"""
    h, w = img.shape[:2]
    x1, y1, x2, y2 = region if region is not None else (0, 0, w, h)
    sub = img[y1:y2, x1:x2, :3].astype(np.int16)
    hit = np.all(np.abs(sub - np.asarray(rgb).astype(np.int16))
                 <= np.asarray(diff).astype(np.int16), axis=2)
    ys, xs = np.nonzero(hit)
    return [(int(x + x1), int(y + y1)) for y, x in zip(ys[:max_hits], xs[:max_hits])]


# ---------------------------------------------------------------- 多点
Point = tuple[int, int, np.ndarray, np.ndarray, bool]  # dx, dy, rgb, diff, enabled


def parse_multi(text: str) -> list[Point]:
    """"dx|dy|rrggbb-dddddd,..." → [(dx,dy,rgb,diff,True),...]"""
    pts: list[Point] = []
    for part in text.strip().split(","):
        fields = part.strip().split("|")
        if len(fields) != 3:
            raise ValueError(f"多点描述格式不对：{part!r}（要 dx|dy|颜色）")
        rgb, diff = parse_desc(fields[2])
        pts.append((int(fields[0]), int(fields[1]), rgb, diff, True))
    return pts


def format_multi(pts: list[Point]) -> str:
    return ",".join(f"{dx}|{dy}|{format_desc(rgb, diff)}" for dx, dy, rgb, diff, _ in pts)


def find_multi(img: np.ndarray, pts: list[Point], region=None,
               tol_anchor: bool = True, max_hits: int = 16) -> list[tuple[int, int]]:
    """多点找色：以第一个启用点为锚全图找，其余点按相对偏移核对。

    返回锚点坐标列表。锚点是 pts 里第一个 enabled 的。"""
    on = [p for p in pts if p[4]]
    if not on:
        return []
    ax, ay, argb, adiff, _ = on[0]
    anchors = find_color(img, argb, adiff, region=region, max_hits=max_hits * 4)
    hits = []
    for x, y in anchors:
        base_x, base_y = x - ax, y - ay
        if all(match_at(img, base_x + dx, base_y + dy, rgb, diff) for dx, dy, rgb, diff, _ in on[1:]):
            hits.append((x, y))
            if len(hits) >= max_hits:
                break
    return hits
