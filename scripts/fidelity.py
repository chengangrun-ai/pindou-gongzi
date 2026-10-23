# -*- coding: utf-8 -*-
"""fidelity.py —— 用「重建误差」量化还原度，按图自动选分辨率"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
import batch34 as M
import beadify as B


def rebuild(im, grid, pal):
    """把格子还原成同尺寸平面图（不含豆子光影），用来量还原度"""
    H, W = im.size[1], im.size[0]
    P = np.array([B.hex2rgb(p[1]) for p in pal], np.float32)
    rgb = P[grid]                       # NR×NC×3
    small = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
    return small.resize((W, H), Image.NEAREST)


def score(im, grid, pal, blur=0.0):
    """必须在「同一块被裁过的源图」上比，否则会错位，分数乱跳"""
    cols = grid.shape[1]
    n = max(2, im.width // cols)
    im2 = im.crop((0, 0, n * cols, n * (im.height // n)))
    rec_i = rebuild(im2, grid, pal)
    src_i = im2
    if blur > 0:
        from PIL import ImageFilter
        rec_i = rec_i.filter(ImageFilter.GaussianBlur(blur))
        src_i = src_i.filter(ImageFilter.GaussianBlur(blur))
    rec = np.asarray(rec_i).astype(np.float32) / 255.0
    src = np.asarray(src_i).astype(np.float32) / 255.0
    return 1.0 - np.abs(src - rec).mean()


def auto_res(im, target=0.95, hi=176, K_of=None):
    """逐档提高分辨率，直到重建还原度达到 target"""
    best = None
    for cols in (64, 80, 96, 112, 128, 144, 160, 176):
        if cols > hi:
            break
        K = K_of(cols) if K_of else int(min(48, 18 + cols / 5))
        g, p = M.beadify(im, cols, K=K)
        s = score(im, g, p)
        if best is None or s > best[2]:
            best = (cols, K, s, g, p)
        if s >= target:
            return cols, K, s, g, p
    return best
