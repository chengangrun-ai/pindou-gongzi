# -*- coding: utf-8 -*-
"""floatcard.py —— 角色直接浮在亚麻纸上（无白板）"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops
import brand as BR


def grid_alpha(im_rgba, cols):
    """把 alpha 降到格子分辨率，返回 NR×NC 的 0/1 掩膜"""
    W, H = im_rgba.size
    n = max(2, W // cols)
    a = np.asarray(im_rgba.split()[3]).astype(np.float32) / 255.0
    a = a[:n * (H // n), :n * cols]
    NR, NC = a.shape[0] // n, cols
    blk = a.reshape(NR, n, NC, n).mean(axis=(1, 3))
    return blk


def float_card(grid, pal, cell=20, size=(1080, 1440), mark=True):
    NR, NC = grid.shape
    W, H = size
    canvas = BR.paper(W, H)
    bead = BR.mosaic(grid, pal, cell)

    tw = int(W * 0.72)
    s = tw / bead.width
    bw, bh = int(bead.width * s), int(bead.height * s)
    if bh > H * 0.74:
        s = (H * 0.74) / bead.height
        bw, bh = int(bead.width * s), int(bead.height * s)
    bead = bead.resize((bw, bh), Image.LANCZOS)
    bx, by = (W - bw) // 2, int(H * 0.47) - bh // 2

    alpha = bead.split()[3]
    sh = Image.new("L", (W, H), 0)
    sh.paste(alpha, (bx, by + 10))
    sh = sh.filter(ImageFilter.GaussianBlur(14))
    canvas.paste((124, 116, 106), (0, 0), sh.point(lambda v: int(v * 0.30)))
    canvas.paste(bead, (bx, by), bead)

    # 水印只铺在角色实际占的范围内
    ys, xs = np.where(grid >= 0)
    if len(ys):
        r0, r1, c0, c1 = ys.min(), ys.max(), xs.min(), xs.max()
        k = bw / NC
        wm_box = (bx + int(c0 * k), by + int(r0 * k),
                  bx + int((c1 + 1) * k), by + int((r1 + 1) * k))
    else:
        wm_box = (bx, by, bx + bw, by + bh)
    if mark:
        BR.watermark(canvas, BR.WM, wm_box,
                     size=max(26, int((wm_box[2]-wm_box[0]) // 15)), alpha=155, spacing=0.92)
        BR.brand_footer(canvas, scale=1.0)
    return canvas
