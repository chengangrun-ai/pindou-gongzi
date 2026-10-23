# -*- coding: utf-8 -*-
"""cutout.py —— 去掉平色背景，只留主体"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage


def cutout(im, tol=11, feather=1.6, big=45):
    """局部背景估计 + 从四边泛洪：渐变底也能去掉，硬边能挡住"""
    A = np.asarray(im.convert("RGB")).astype(np.float32)
    h, w, _ = A.shape
    edge = np.concatenate([A[0, :], A[-1, :], A[:, 0], A[:, -1]])
    gcol = np.median(edge, 0)
    d1 = np.abs(A - gcol).max(2)                       # 纯色底
    bg = np.stack([ndimage.gaussian_filter(A[..., c], big) for c in range(3)], -1)
    d2 = np.abs(A - bg).max(2)                         # 渐变底
    near = (d1 < tol * 2) | (d2 < tol * 0.7)

    lab, _ = ndimage.label(near)
    ids = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])
    ids.discard(0)
    bgmask = np.isin(lab, list(ids))

    # 去掉背景里的小洞（主体内部的同色块不该被抠掉）
    filled = ndimage.binary_fill_holes(bgmask)
    holes = filled & ~bgmask
    lab2, n2 = ndimage.label(holes)
    for i in range(1, n2 + 1):
        if (lab2 == i).sum() < (h * w) * 0.002:
            bgmask &= ~(lab2 == i)

    alpha = np.where(bgmask, 0, 255).astype(np.uint8)
    a = Image.fromarray(alpha)
    if feather > 0:
        a = a.filter(ImageFilter.GaussianBlur(feather))
        a = a.point(lambda v: 0 if v < 40 else (255 if v > 215 else int((v - 40) * 255 / 175)))
    out = im.convert("RGB").copy()
    out.putalpha(a)
    return out


def trim(im, pad=0.04):
    """按 alpha 裁到主体外框"""
    a = np.asarray(im.split()[3])
    ys, xs = np.where(a > 40)
    if len(ys) == 0:
        return im
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    w, h = x1 - x0, y1 - y0
    px, py = int(w * pad) + 2, int(h * pad) + 2
    box = (max(0, x0 - px), max(0, y0 - py),
           min(im.width, x1 + px), min(im.height, y1 + py))
    return im.crop(box)


def square_pad(im, pad=0.07):
    """补成正方形（透明），给构图留边"""
    w, h = im.size
    side = int(max(w, h) * (1 + pad * 2))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(im, ((side - w) // 2, (side - h) // 2), im)
    return canvas


def on_white(im):
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, (0, 0), im)
        return bg
    return im.convert("RGB")


def cutout_photo(im, rect_ratio=(0.20, 0.04, 0.60, 0.94), iters=6):
    """真人照片用 grabCut 分割（平色底判据对照片无效）"""
    import cv2
    arr = cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = arr.shape[:2]
    rx, ry, rw, rh = rect_ratio
    rect = (int(w*rx), int(h*ry), int(w*rw), int(h*rh))
    mask = np.zeros((h, w), np.uint8)
    bgd = np.zeros((1, 65), np.float64); fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(arr, mask, rect, bgd, fgd, iters, cv2.GC_INIT_WITH_RECT)
    m = np.where((mask == 2) | (mask == 0), 0, 255).astype(np.uint8)
    m = cv2.medianBlur(m, 7)
    rgba = cv2.cvtColor(arr, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = m
    return Image.fromarray(cv2.cvtColor(rgba, cv2.COLOR_BGRA2RGBA))


def clean_alpha(im, min_ratio=0.0005, feather=1.6):
    """去掉孤立小碎块，只留主体（多主体时保留所有大于阈值的）

    min_ratio: 小于画面这个比例的连通块视为噪点（默认 0.05%）
    """
    from scipy import ndimage
    a = np.asarray(im.split()[3])
    m = a > 40
    lab, n = ndimage.label(m)
    if n <= 1:
        return im
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    keep = [i + 1 for i, sz in enumerate(sizes) if sz >= m.size * min_ratio]
    if not keep:
        return im
    keep.sort(key=lambda i: -sizes[i - 1])
    mask = np.isin(lab, keep)
    out = im.copy()
    alpha = np.where(mask, a, 0).astype(np.uint8)
    img = Image.fromarray(alpha)
    if feather > 0:
        from PIL import ImageFilter
        img = img.filter(ImageFilter.GaussianBlur(feather))
    out.putalpha(img)
    return out


def quality(im):
    """抠图质量评分 0-100：覆盖率是否合理 + 边缘是否有锯齿 + 是否有碎块

    分数只用于提示，不参与出图决策。
    """
    from scipy import ndimage
    a = np.asarray(im.split()[3])
    cov = float((a > 128).mean())
    score = 100.0
    notes = []

    if cov > 0.92:
        score -= 40; notes.append("背景几乎没去掉")
    elif cov < 0.05:
        score -= 40; notes.append("主体太小或没抠到")
    elif cov > 0.85:
        score -= 12; notes.append("主体占比偏大")

    # 边缘锯齿：alpha 在 0/255 之间的像素占比
    soft = float(((a > 20) & (a < 235)).mean())
    if soft > 0.06:
        score -= 15; notes.append("边缘毛糙")
    elif soft < 0.002:
        score -= 8; notes.append("边缘过硬，可能有白边")

    # 碎块：连通块数量
    lab, n = ndimage.label(a > 128)
    if n > 6:
        score -= min(25, (n - 6) * 4); notes.append(f"{n} 个碎块")

    return max(0, round(score)), notes, round(cov, 3)
