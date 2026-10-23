# -*- coding: utf-8 -*-
"""向量化的格子取色：比逐格 Python 循环快 20 倍以上"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import beadify as B
from config import CFG as _C
_P = _C['pipeline']


def beadify_fast(im, cols, K=32):
    im = im.convert("RGB")
    W, H = im.size
    n = max(2, W // cols)
    im2 = im.crop((0, 0, n * cols, n * (H // n)))
    NR, NC = im2.height // n, cols

    A = np.asarray(im2).astype(np.float32) / 255.0
    mean = A.mean(axis=2, keepdims=True)
    ch = np.abs(A - mean).max(axis=2, keepdims=True)
    kk = np.clip(ch / 0.14, 0, 1)
    A = np.clip(A + (A - mean) * (float(_P['vivid']) * kk), 0, 1)

    pal = B.build_adaptive_palette(A, K)
    P = np.array([B.hex2rgb(p[1]) for p in pal], np.float32)
    flat = A.reshape(-1, 3)
    pidx = ((flat[:, None, :] - P[None]) ** 2).sum(-1).argmin(1).reshape(im2.height, im2.width)

    blk = pidx.reshape(NR, n, NC, n)
    cnt = np.stack([(blk == k).sum(axis=(1, 3)) for k in range(len(pal))])
    grid = cnt.argmax(0).astype(np.int16)

    lum = (P * [0.299, 0.587, 0.114]).sum(1)
    dark = np.where(lum < 0.32)[0]
    if len(dark):
        dsum = cnt[dark].sum(0)
        if (dsum > 0.22 * n * n).any():
            m = dsum > 0.22 * n * n
            grid[m] = dark[cnt[dark][:, m].argmax(0)]

    used = np.bincount(grid.ravel(), minlength=len(pal))
    keep = [i for i in range(len(pal)) if used[i] > 0]
    remap = np.zeros(len(pal), np.int16)
    for j, k in enumerate(keep):
        remap[k] = j
    grid = remap[grid]
    pal2 = [(pal[k][0], pal[k][1], pal[k][2], int(used[k])) for k in keep]
    return grid, pal2
