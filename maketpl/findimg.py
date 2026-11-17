"""透明模板匹配：和 mhxy 第三层 src/nav/match.py 同一套算法（拷过来的，保持同步）。

模板是 RGBA：alpha>=128 的像素参与比对，其余忽略——正是本工具输出的格式。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Hit:
    x: int
    y: int
    w: int
    h: int
    score: float

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2


def _split(tpl: np.ndarray):
    if tpl.ndim == 3 and tpl.shape[2] == 4:
        return tpl[:, :, :3], tpl[:, :, 3] >= 128
    return tpl, np.ones(tpl.shape[:2], dtype=bool)


def pick_keys(rgb: np.ndarray, mask: np.ndarray, count: int = 6) -> list[tuple[int, int]]:
    ys, xs = np.nonzero(mask)
    if len(ys) < 4:
        raise ValueError("模板里有效像素太少（少于 4 个）")
    mean = rgb[mask].astype(np.int32).mean(axis=0)
    dist = np.abs(rgb[ys, xs].astype(np.int32) - mean).sum(axis=1)
    order = np.argsort(-dist, kind="stable")
    spacing = max(2, min(mask.shape) // 4)
    keys: list[tuple[int, int]] = []
    for i in order:
        y, x = int(ys[i]), int(xs[i])
        if all(max(abs(y - ky), abs(x - kx)) >= spacing for ky, kx in keys):
            keys.append((y, x))
            if len(keys) == count:
                break
    return keys


def find_all(frame: np.ndarray, tpl: np.ndarray, *, region=None, tol: int = 24,
             max_score: float = 10.0, max_hits: int = 10,
             max_candidates: int = 5000) -> list[Hit]:
    rgb, mask = _split(tpl)
    h, w = mask.shape
    fh, fw = frame.shape[:2]
    x1, y1, x2, y2 = region if region is not None else (0, 0, fw, fh)
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(fw, x2), min(fh, y2)
    if x2 - x1 < w or y2 - y1 < h:
        return []
    sub = frame[y1:y2, x1:x2, :3].astype(np.int16)
    ch, cw = sub.shape[0] - h + 1, sub.shape[1] - w + 1
    t16 = rgb.astype(np.int16)
    ok = np.ones((ch, cw), dtype=bool)
    for ky, kx in pick_keys(rgb, mask):
        window = sub[ky:ky + ch, kx:kx + cw]
        ok &= np.all(np.abs(window - t16[ky, kx]) <= tol, axis=2)
        if not ok.any():
            return []
    ys, xs = np.nonzero(ok)
    if len(ys) > max_candidates:
        raise ValueError(f"候选位置 {len(ys)} 个，模板太普通，换一块更有特征的")
    n = int(mask.sum()) * 3
    # 逐个候选切 h×w 评分太慢：改成按 mask 分块的一次性索引累加，分数结果完全一样
    mys, mxs = np.nonzero(mask)
    tv = t16[mys, mxs]                                   # (M, 3)
    scores = np.zeros(len(ys), np.int64)
    B = 2048
    for i in range(0, len(mys), B):
        my_c, mx_c = mys[i:i + B], mxs[i:i + B]
        win = sub[ys[:, None] + my_c[None, :], xs[:, None] + mx_c[None, :]]
        scores += np.abs(win - tv[i:i + B]).sum(axis=(1, 2), dtype=np.int64)
    hits: list[Hit] = []
    for (y, x), s in zip(zip(ys.tolist(), xs.tolist()), scores):
        score = float(s) / n
        if score <= max_score:
            hits.append(Hit(x + x1, y + y1, w, h, score))
    hits.sort(key=lambda t: t.score)
    kept: list[Hit] = []
    for t in hits:
        if all(abs(t.x - k.x) >= max(1, w // 2) or abs(t.y - k.y) >= max(1, h // 2) for k in kept):
            kept.append(t)
            if len(kept) >= max_hits:
                break
    return kept


def find_best(frame, tpl, **kwargs) -> Hit | None:
    hits = find_all(frame, tpl, **kwargs)
    return hits[0] if hits else None
