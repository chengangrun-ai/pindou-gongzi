# -*- coding: utf-8 -*-
"""simplify.py —— 在「色号最少」和「还原度最高」之间取最优

思路：不重新聚类，而是在已有调色板上**逐步合并最接近的两个颜色**，
每一步都算还原度；一旦掉到阈值以下就停。这样得到的就是
「还原度还够的前提下，色号最少」的那一版。

    from simplify import reduce_palette
    g2, p2, info = reduce_palette(g, p, ref_image, floor=0.965)

为什么不用 K-means 重跑：重跑要试十几次 K，慢十倍；
合并法只走「色数 - 目标色数」步，每步一次距离计算，快得多。
"""
import numpy as np

import fidelity as F

try:
    from lowcolor import rgb2lab
except Exception:                                    # 兜底
    def rgb2lab(rgb):
        c = np.where(rgb > 0.04045, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)
        m = np.array([[0.4124, 0.3576, 0.1805],
                      [0.2126, 0.7152, 0.0722],
                      [0.0193, 0.1192, 0.9505]], np.float32)
        xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883], np.float32)
        f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
        return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])], np.float32)


def _hex2rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255.0


def _merge(g, p, i, j):
    """把色号 j 合并进 i：网格里所有 j 变成 i，调色板去掉 j"""
    g2 = g.copy()
    g2[g == j] = i
    g2[g2 > j] -= 1
    p2 = [x for k, x in enumerate(p) if k != j]
    return g2, p2


def reduce_palette(g, p, ref, floor=0.965, drop=0.012, min_colors=4,
                   max_delta=10.0, verbose=False):
    """逐步合并最接近的颜色，直到还原度跌破 floor

    g:   (NR,NC) int16，-1 为透明
    p:   [(code, hex, name, count), ...]
    ref: 源图（裁过的那张），用来算还原度
    floor: 绝对下限（兜底）
    drop:  允许比当前低多少，默认 0.012（1.2%）
    max_delta: 两个颜色差多远就不许合并（Lab 距离），默认 10
    返回 (grid, pal, info)
    """
    if not p or len(p) <= min_colors:
        return g, p, {"before": len(p), "after": len(p), "fidelity": None}

    best_score = float(F.score(ref, np.where(g >= 0, g, 0), p))
    # 门槛按「相对当前」算：允许掉 drop，而不是卡一个绝对分数
    floor = max(min(floor, best_score - drop), best_score - drop)
    n0 = len(p)
    cur_g, cur_p = g, list(p)
    cur_score = best_score

    while len(cur_p) > min_colors:
        # 每个颜色当前占多少格
        cnt = np.bincount(cur_g[cur_g >= 0], minlength=len(cur_p)).astype(np.float32)
        labs = np.stack([rgb2lab(_hex2rgb(c[1])) for c in cur_p])

        # 找「合并后代价最小」的一对：色差 × 像素数
        best = None
        for i in range(len(cur_p)):
            for j in range(i + 1, len(cur_p)):
                if cnt[i] + cnt[j] == 0:
                    continue
                d = float(np.linalg.norm(labs[i] - labs[j]))
                if d > max_delta:          # 差太远的颜色不许合并，否则画面会糊
                    continue
                cost = d * (cnt[i] + cnt[j])
                if best is None or cost < best[0]:
                    best = (cost, i, j)
        if best is None:
            break

        _, i, j = best
        ng, npal = _merge(cur_g, cur_p, i, j)
        # 合并后必须重算，因为色号索引变了
        sc = float(F.score(ref, np.where(ng >= 0, ng, 0), npal))
        if sc < floor:
            break
        cur_g, cur_p, cur_score = ng, npal, sc
        if verbose:
            print(f"    {len(cur_p)} 色  还原 {sc:.4f}")

    # 重算用量并按用量排序
    cnt = np.bincount(cur_g[cur_g >= 0], minlength=len(cur_p))
    order = sorted(range(len(cur_p)), key=lambda k: -cnt[k])
    idx = np.zeros(len(cur_p), np.int16)
    for new_i, old_i in enumerate(order):
        idx[old_i] = new_i
    g3 = np.where(cur_g >= 0, idx[np.clip(cur_g, 0, None)], -1).astype(np.int16)
    p3 = [(cur_p[k][0], cur_p[k][1], cur_p[k][2], int(cnt[k])) for k in order]

    return g3, p3, {"before": n0, "after": len(p3),
                    "fidelity": round(cur_score, 4),
                    "fidelity_before": round(best_score, 4)}


if __name__ == "__main__":
    print(__doc__)
