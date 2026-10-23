# -*- coding: utf-8 -*-
"""lowcolor.py —— 低色号精品模式：少颜色 + 大格子 + 干净平涂"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
import beadify as B
from config import CFG as _C
_P = _C['pipeline']


def mode_filter(grid, dark_ids, k=3):
    """网格众数滤波（向量化）：抹掉碎点，但不动描边色

    老版本是 Python 逐格 np.unique，256 格要跑 20 秒；
    改成 K 次 uniform_filter 取最大，0.3 秒。
    """
    from scipy import ndimage
    NR, NC = grid.shape
    K = int(grid.max()) + 1
    best = grid.copy()
    bestv = np.full(grid.shape, -1.0, np.float32)
    for c in range(K):
        m = (grid == c).astype(np.float32)
        sc = ndimage.uniform_filter(m, k, mode="constant")
        upd = sc > bestv
        best[upd] = c
        bestv[upd] = sc[upd]
    # 描边色原样保留
    if len(dark_ids):
        keep = np.isin(grid, list(dark_ids))
        best[keep] = grid[keep]
    return best.astype(np.int16)


def speckle_vec(g):
    """碎点率（向量化）：8 邻域同色 ≤2 的格子占比"""
    valid = g >= 0
    same = np.zeros(g.shape, np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            same += (np.roll(np.roll(g, dy, 0), dx, 1) == g)
    iso = (same <= 2) & valid
    iso[:1, :] = iso[-1:, :] = False
    iso[:, :1] = iso[:, -1:] = False
    n = valid.sum()
    return float(iso.sum()) / max(int(n), 1)


def beadify_low(im, cols=88, K=13):
    """少色号：先去噪 → 少量聚类 → 众数取格 → 众数滤波"""
    im = im.convert("RGB")
    W, H = im.size
    n = max(2, W // cols)
    im2 = im.crop((0, 0, n * cols, n * (H // n)))
    NR = im2.height // n

    # 去噪（保边），让大片区域变干净
    im2 = im2.filter(ImageFilter.MedianFilter(5))
    A = np.asarray(im2).astype(np.float32) / 255.0

    pal = B.build_adaptive_palette(A, K)
    # 低色号模式：ΔE<10 的近似色合并，避免同一片白分成好几个色
    Pl = B.rgb2lab(np.array([B.hex2rgb(p[1]) for p in pal], np.float32))
    chroma = np.hypot(Pl[:, 1], Pl[:, 2])
    keep_idx = []
    for i in range(len(pal)):
        dup = False
        for j in keep_idx:
            d = np.linalg.norm(Pl[i] - Pl[j])
            # 中性色（白/灰/黑）多合一点；有彩色的要保留色相差异
            neutral = chroma[i] < 12 and chroma[j] < 12
            if d < (18 if neutral else 9):
                dup = True
                break
        if not dup:
            keep_idx.append(i)
    pal = [pal[i] for i in keep_idx]
    P = np.array([B.hex2rgb(p[1]) for p in pal], np.float32)
    flat = A.reshape(-1, 3)
    pidx = ((flat[:, None, :] - P[None]) ** 2).sum(-1).argmin(1).reshape(im2.height, im2.width)

    blk = pidx.reshape(NR, n, cols, n)
    cnt = np.stack([(blk == k).sum(axis=(1, 3)) for k in range(len(pal))])
    grid = cnt.argmax(0).astype(np.int16)

    # 暗色优先（保描边）
    lum = (P * [0.299, 0.587, 0.114]).sum(1)
    dark = np.where(lum < 0.30)[0]
    if len(dark):
        ds = cnt[dark].sum(0)
        m = ds > float(_P['outline_ratio']) * n * n
        if m.any():
            grid[m] = dark[cnt[dark][:, m].argmax(0)]

    # 先全图去碎点，再把「原图里确实很黑」的格子恢复成描边
    grid = mode_filter(grid, [], 3)
    grid = mode_filter(grid, [], 3)
    if len(dark):
        strong = ds > 0.55 * n * n
        grid[strong] = dark[cnt[dark][:, strong].argmax(0)]

    used = np.bincount(grid.ravel(), minlength=len(pal))
    keep = [i for i in range(len(pal)) if used[i] > 0]
    remap = np.zeros(len(pal), np.int16)
    for j, k in enumerate(keep):
        remap[k] = j
    grid = remap[grid]
    pal2 = [(pal[k][0], pal[k][1], pal[k][2], int(used[k])) for k in keep]
    return grid, pal2


def is_lineart(im):
    """线稿：大面积近白 + 少量近黑，中间调很少（纹身手稿、素描、漫画线稿）"""
    g = np.asarray(im.convert("L"), np.float32) / 255.0
    white = float((g > 0.90).mean())
    black = float((g < 0.25).mean())
    mid = float(((g > 0.35) & (g < 0.75)).mean())
    return white > 0.42 and black > 0.015 and mid < 0.28


def beadify_line(im, cols, levels=4):
    """线稿专用取色：按亮度分档，每格取「最暗的分位数」保住细线

    普通众数会把细线抹掉（细线在格子里只占少数），所以这里取暗分位。
    """
    im = im.convert("RGB")
    W, H = im.size
    n = max(2, W // cols)
    im2 = im.crop((0, 0, n * cols, n * (H // n)))
    NR = im2.height // n

    g = np.asarray(im2.convert("L"), np.float32) / 255.0
    blk = g.reshape(NR, n, cols, n)
    # 20% 分位：格子里的暗部优先，细线不会被平均掉
    dark = np.percentile(blk, 20, axis=(1, 3))

    # 分档：黑 / 深灰 / 浅灰 / 白
    th = np.array([0.28, 0.55, 0.82])[:max(1, levels - 1)]
    idx = np.digitize(dark, th).astype(np.int16)

    # 调色板：4 档灰阶
    shades = [(0.10, 0.10, 0.11), (0.35, 0.35, 0.37), (0.66, 0.66, 0.68), (1.0, 1.0, 1.0)]
    shades = shades[:levels]
    pal = []
    for i, (r, gg, b) in enumerate(shades):
        hx = "#%02X%02X%02X" % (int(r*255), int(gg*255), int(b*255))
        nm = ["黑", "深灰", "浅灰", "白"][i]
        code = ["K1", "G1", "G2", "W1"][i]
        cnt = int((idx == i).sum())
        pal.append((code, hx, nm, cnt))

    # 去掉没用到的档，重编号
    used = [i for i in range(levels) if pal[i][3] > 0]
    remap = np.zeros(levels, np.int16)
    for j, k in enumerate(used):
        remap[k] = j
    return remap[idx], [pal[k] for k in used]
