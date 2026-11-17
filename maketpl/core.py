"""多帧求稳做透明模板：同一个区域连拍 N 张，每个像素在 N 张里颜色一致的留下、
不一致的（走动的角色、飘动的光效等噪音）设成透明。

输出 RGBA 数组，alpha>=128 的像素参与比对。
"""
from __future__ import annotations

import numpy as np


def _stack(frames: list[np.ndarray]) -> np.ndarray:
    if len(frames) < 2:
        raise ValueError("至少要 2 张帧才能求稳（连拍多采几张）")
    shapes = {f.shape for f in frames}
    if len(shapes) != 1:
        raise ValueError(f"帧尺寸不一致：{sorted(shapes)}，连拍期间窗口/面板动过？")
    arr = np.stack(frames)
    if arr.ndim != 4 or arr.shape[3] < 3:
        raise ValueError("帧必须是 HxWx3(或4) 的图")
    return arr[:, :, :, :3]


def stable_mask(frames: list[np.ndarray], tol: int = 8, min_count: int | None = None) -> np.ndarray:
    """逐像素求稳：取 N 张的中位数当基准，和中位数每通道差 <=tol 的算"一致"，
    一致帧数 >= min_count 的像素保留，其余当噪音。min_count 默认要求 N-1 张一致。"""
    arr = _stack(frames).astype(np.int16)
    n = arr.shape[0]
    min_count = (n - 1) if min_count is None else int(min_count)
    if not 1 <= min_count <= n:
        raise ValueError(f"min_count 要在 1..{n} 之间（当前 {min_count}）")
    med = np.median(arr, axis=0)
    agree = np.all(np.abs(arr - med) <= tol, axis=3)
    return agree.sum(axis=0) >= min_count


def vary_mask(frames: list[np.ndarray], tol: int = 8, min_count: int | None = None) -> np.ndarray:
    """删除不变：stable_mask 的反操作，只留下 N 帧里有变化的像素（抠动画/闪烁部分用）。"""
    arr = _stack(frames).astype(np.int16)
    n = arr.shape[0]
    min_count = (n - 1) if min_count is None else int(min_count)
    if not 1 <= min_count <= n:
        raise ValueError(f"min_count 要在 1..{n} 之间（当前 {min_count}）")
    med = np.median(arr, axis=0)
    agree = np.all(np.abs(arr - med) <= tol, axis=3)
    return agree.sum(axis=0) < min_count


def compose_rgba(frames: list[np.ndarray], mask: np.ndarray) -> np.ndarray:
    """保留的像素取 N 张的中位数颜色，丢掉的 alpha=0。"""
    arr = _stack(frames)
    if mask.shape != arr.shape[1:3] or mask.dtype != bool:
        raise ValueError("mask 形状和帧不一致")
    h, w = mask.shape
    out = np.empty((h, w, 4), np.uint8)
    out[:, :, :3] = np.median(arr, axis=0).astype(np.uint8)
    out[:, :, 3] = np.where(mask, 255, 0)
    return out


def crop_to_content(rgba: np.ndarray, pad: int = 0) -> np.ndarray:
    """按不透明像素的外接矩形裁掉四周全透明的边，pad 是向外多留的像素。"""
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("要 RGBA 图")
    ys, xs = np.nonzero(rgba[:, :, 3] >= 128)
    if len(ys) == 0:
        raise ValueError("一个有效像素都没留下：帧数太少、min_count 太严，或这块区域一直在变")
    h, w = rgba.shape[:2]
    y1, y2 = max(0, ys.min() - pad), min(h, ys.max() + pad + 1)
    x1, x2 = max(0, xs.min() - pad), min(w, xs.max() + pad + 1)
    return rgba[y1:y2, x1:x2]


def compose_from_base(base: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """用一张基准图 + 掩码合成 RGBA：保留处取基准颜色，丢掉处 alpha=0。"""
    if base.ndim != 3 or base.shape[2] < 3:
        raise ValueError("基准图必须是 HxWx3")
    if mask.shape != base.shape[:2] or mask.dtype != bool:
        raise ValueError("mask 形状和基准图不一致")
    h, w = mask.shape
    out = np.empty((h, w, 4), np.uint8)
    out[:, :, :3] = base[:, :, :3]
    out[:, :, 3] = np.where(mask, 255, 0)
    return out


def flood_fill(rgb: np.ndarray, seed: tuple[int, int], tol: int = 8) -> np.ndarray:
    """油漆桶：从 seed(y,x) 出发，颜色每通道差 <=tol 且四连通成片的像素置 True。

    用在基准图上算"要挖/要补"的区域；tol 要大就传大，防止抗锯齿边缘漏网。"""
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        raise ValueError("要 HxWx3 图")
    h, w = rgb.shape[:2]
    sy, sx = seed
    if not (0 <= sy < h and 0 <= sx < w):
        raise ValueError(f"种子点 ({sy},{sx}) 在图外")
    target = rgb[sy, sx].astype(np.int16)
    similar = np.all(np.abs(rgb[:, :, :3].astype(np.int16) - target) <= tol, axis=2)
    out = np.zeros((h, w), bool)
    frontier = np.zeros((h, w), bool)
    frontier[sy, sx] = True
    while frontier.any():
        grown = frontier.copy()
        grown[1:, :] |= frontier[:-1, :]
        grown[:-1, :] |= frontier[1:, :]
        grown[:, 1:] |= frontier[:, :-1]
        grown[:, :-1] |= frontier[:, 1:]
        frontier = grown & similar & ~out
        out |= frontier
    return out


def color_region(rgb: np.ndarray, seed: tuple[int, int], tol: int = 8) -> np.ndarray:
    """全图同色：和 seed(y,x) 颜色每通道差 <=tol 的像素全置 True，不要求连通。"""
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        raise ValueError("要 HxWx3 图")
    h, w = rgb.shape[:2]
    sy, sx = seed
    if not (0 <= sy < h and 0 <= sx < w):
        raise ValueError(f"种子点 ({sy},{sx}) 在图外")
    target = rgb[sy, sx].astype(np.int16)
    return np.all(np.abs(rgb[:, :, :3].astype(np.int16) - target) <= tol, axis=2)


def _label_components(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """四连通块标记（行程+并查集）。返回 (labels, sizes)：labels[i]=根标签或-1，
    sizes[根]=该块像素数。"""
    h, w = mask.shape
    labels = np.full((h, w), -1, np.int32)
    parent: list[int] = []

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> int:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
        return ra

    prev: list[tuple[int, int, int]] = []  # 上一行的 (x1, x2, label)
    for y in range(h):
        cur: list[tuple[int, int, int]] = []
        row = mask[y]
        x = 0
        while x < w:
            if not row[x]:
                x += 1
                continue
            x1 = x
            while x < w and row[x]:
                x += 1
            x2 = x - 1
            lab = -1
            for px1, px2, pl in prev:
                if px1 <= x2 and px2 >= x1:
                    lab = pl if lab < 0 else union(lab, pl)
            if lab < 0:
                lab = len(parent)
                parent.append(lab)
            cur.append((x1, x2, lab))
            labels[y, x1:x2 + 1] = lab
        prev = cur

    if not parent:
        return labels, np.zeros(0, np.int64)
    roots = np.fromiter((find(i) for i in range(len(parent))), np.int64, len(parent))
    lab = labels.copy()
    lab[mask] = roots[lab[mask]]
    sizes = np.bincount(lab[mask], minlength=len(parent))
    return lab, sizes


def filter_components(mask: np.ndarray, min_size: int = 0,
                      max_size: int | None = None) -> np.ndarray:
    """保留大小在 [min_size, max_size] 内的连通块。"""
    lab, sizes = _label_components(mask)
    out = mask.copy()
    if len(sizes) == 0:
        return out
    keep = sizes >= min_size
    if max_size is not None:
        keep &= sizes <= max_size
    out[mask] = keep[lab[mask]]
    return out


def remove_small(mask: np.ndarray, max_size: int) -> np.ndarray:
    """去掉 <=max_size 像素的四连通小块（孤岛清理）。返回新 mask。"""
    return filter_components(mask, min_size=max_size + 1)


def erode(mask: np.ndarray, n: int = 1) -> np.ndarray:
    """收边：保留区向内缩 n 像素（四邻里有透明/图外的像素就去掉）。

    抠 NPC 这类带抗锯齿边的图时，最外一圈像素混着当时的背景色，换个背景就对不上，
    收掉它们匹配更稳。"""
    out = mask.copy()
    for _ in range(max(0, n)):
        nxt = out.copy()
        nxt[1:, :] &= out[:-1, :]
        nxt[0, :] = False
        nxt[:-1, :] &= out[1:, :]
        nxt[-1, :] = False
        nxt[:, 1:] &= out[:, :-1]
        nxt[:, 0] = False
        nxt[:, :-1] &= out[:, 1:]
        nxt[:, -1] = False
        out = nxt
    return out


def largest_component(mask: np.ndarray) -> np.ndarray:
    """只留最大的一块四连通区域（主体），其余碎块和阴影、飘字都去掉。"""
    lab, sizes = _label_components(mask)
    if len(sizes) == 0 or sizes.max() == 0:
        return mask.copy()
    return mask & (lab == int(np.argmax(sizes)))


def split_phases(frames: list[np.ndarray], tol: int = 12) -> list[list[int]]:
    """把连拍的帧按"长得一样"分成相位组（动图拆模板用）。返回下标分组的列表。

    判定：两张图的逐像素平均色差的均值 <= tol 就算同相位。贪心归组，
    每张帧和已见组的第一张比，够像就进组，否则开新组。帧在原列表里的顺序保留。"""
    arr = _stack(frames).astype(np.int16)
    groups: list[list[int]] = []
    reps: list[np.ndarray] = []  # 每组第一张帧
    for i in range(arr.shape[0]):
        placed = False
        for g, rep in enumerate(reps):
            if np.abs(arr[i] - rep).mean() <= tol:
                groups[g].append(i)
                placed = True
                break
        if not placed:
            groups.append([i])
            reps.append(arr[i])
    return groups


def disc(shape: tuple[int, int], center: tuple[int, int], radius: int) -> np.ndarray:
    """圆形画笔范围（y,x 中心，radius 含中心）。"""
    h, w = shape
    y, x = np.indices((h, w))
    cy, cx = center
    return (y - cy) ** 2 + (x - cx) ** 2 <= radius ** 2


def build(frames: list[np.ndarray], tol: int = 8, min_count: int | None = None,
          pad: int = 0) -> tuple[np.ndarray, np.ndarray, int]:
    """一步到位：返回 (裁好的 RGBA, 完整 mask, 保留像素数)。"""
    mask = stable_mask(frames, tol=tol, min_count=min_count)
    rgba = compose_rgba(frames, mask)
    kept = int(mask.sum())
    if kept == 0:
        raise ValueError("一个有效像素都没留下：帧数太少、min_count 太严，或这块区域一直在变")
    return crop_to_content(rgba, pad=pad), mask, kept
