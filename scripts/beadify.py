# -*- coding: utf-8 -*-
"""
beadify.py —— 照片 / 像素图 → 拼豆图纸 一键生成

用法示例：
  python beadify.py --src a.jpg --crop 150,480,810,1240 --cols 68 --name 白猫 --outdir out

产出（outdir 下）：
  01_成品预览.png     模拟真实豆子的成品效果
  02_图纸_全图.png    带色号 / 坐标 / 色卡的完整图纸
  03_小红书封面.png   3:4 竖版封面
  04_图纸_可打印.pdf  A4 横版分块图纸
  spec.json           色板与统计
"""
import argparse, json, os
import numpy as np
from collections import Counter
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops
from scipy import ndimage

# ---------------------------------------------------------------- 色板
# 通用「宠物照片」色板：22 色，覆盖 白/灰/黑 中性阶 + 暖奶油 + 棕 + 琥珀 + 粉
PALETTE = [
    ("W1", "#FBFAF6", "雪白"), ("W2", "#EFEBE2", "暖白"), ("W3", "#DED8CC", "米白"),
    ("W4", "#C9C3B6", "珍珠灰"), ("W5", "#ADA79B", "浅灰"), ("W6", "#8C877D", "中灰"),
    ("W7", "#68645C", "石灰"), ("W8", "#494640", "深灰"),
    ("K1", "#2B2926", "炭黑"), ("K2", "#141310", "墨黑"),
    ("C1", "#EFE0C6", "奶油"), ("C2", "#DCC5A2", "浅驼"), ("C3", "#BFA47C", "驼色"),
    ("C4", "#9A7F5C", "深驼"), ("C5", "#6E563C", "咖啡棕"),
    ("Y1", "#E0B45A", "琥珀黄"), ("Y2", "#A8823C", "暗金"),
    ("P1", "#E8BDB6", "浅粉"), ("P2", "#C58B85", "玫瑰粉"),
    ("R1", "#E85A50", "亮红"), ("R2", "#D2605A", "苹果红"), ("R3", "#A83E3C", "深红"),
    ("N1", "#A9B1B9", "灰蓝"), ("N2", "#7B848D", "钢灰"),
    ("B1", "#C2DDE6", "浅雾蓝"), ("B2", "#8FB6C6", "雾蓝"),
    ("B3", "#5FA0D2", "晴空蓝"), ("B4", "#3D7CB0", "深天蓝"),
]

FONT = r"C:\Windows\Fonts\msyh.ttc"
FONTB = r"C:\Windows\Fonts\msyhbd.ttc"


def F(size, bold=False):
    return ImageFont.truetype(FONTB if bold else FONT, size, index=0)


def hex2rgb(h):
    return np.array([int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)], np.float32) / 255


def rgb2lab(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    f = lambda u: np.where(u > 0.04045, ((u + 0.055) / 1.055) ** 2.4, u / 12.92)
    r, g, b = f(r), f(g), f(b)
    X = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    Y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    g2 = lambda t: np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16 / 116)
    fx, fy, fz = g2(X), g2(Y), g2(Z)
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], -1)


def srgb2lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def lin2srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055)


# ---------------------------------------------------------------- 1. 取格子
def make_grid(src, crop, cols, junk=None, contrast=1.18, pivot=0.62, gamma=0.97,
              sharpen=0.5, wb=1.0, auto=True, level="", blur=0.0):
    im = Image.open(src).convert("RGB").crop(crop)
    W, H = im.size
    A = np.asarray(im).astype(np.float32) / 255.0

    if junk:
        l, t, r_, b_ = junk
        x0, y0 = max(l - crop[0], 0), max(t - crop[1], 0)
        x1, y1 = min(r_ - crop[0], W), min(b_ - crop[1], H)
        if x1 > x0 and y1 > y0:
            mask = np.zeros((H, W), bool)
            mask[y0:y1, x0:x1] = True
            # 调和插值（Jacobi 扩散）：用四周真实地面把杂物区平滑地「长」回来
            ys, ye = max(y0 - 2, 0), min(y1 + 2, H)
            xs, xe = max(x0 - 2, 0), min(x1 + 2, W)
            sub = A[ys:ye, xs:xe].copy()
            m = mask[ys:ye, xs:xe]
            sub[m] = sub[~m].mean(0) if (~m).any() else 0.5
            for _ in range(900):
                nb = np.zeros_like(sub)
                nb[1:-1, 1:-1] = (sub[:-2, 1:-1] + sub[2:, 1:-1] +
                                  sub[1:-1, :-2] + sub[1:-1, 2:]) * 0.25
                nb[0] = sub[0]; nb[-1] = sub[-1]; nb[:, 0] = sub[:, 0]; nb[:, -1] = sub[:, -1]
                sub[m] = nb[m]
            sub = ndimage.gaussian_filter(sub, (1.2, 1.2, 0))
            A[ys:ye, xs:xe] = sub

    # 白平衡 + 自动曝光（室内暖光照片必须做，否则白猫会变成灰猫）
    if wb < 0:      # 白点白平衡：拿最亮 2% 当白参考，比灰度世界准
        l0 = 0.299 * A[..., 0] + 0.587 * A[..., 1] + 0.114 * A[..., 2]
        ref = A[l0 >= np.percentile(l0, 98)].reshape(-1, 3).mean(0)
        A = np.clip(A * (0.95 / np.maximum(ref, 1e-3)), 0, 1)
    else:
        mean = A.reshape(-1, 3).mean(0)
        A = np.clip(A * (mean.mean() / np.maximum(mean, 1e-3)) ** wb, 0, 1)
    if auto:
        lum = 0.299 * A[..., 0] + 0.587 * A[..., 1] + 0.114 * A[..., 2]
        p97 = float(np.percentile(lum, 97))
        if p97 > 1e-3:
            A = np.clip(A * (0.94 / p97), 0, 1)
    if level:
        blk, wht = (float(v) for v in level.split(","))
        A = np.clip((A - blk) / max(wht - blk, 1e-3), 0, 1)
    lum0 = 0.299 * A[..., 0] + 0.587 * A[..., 1] + 0.114 * A[..., 2]
    new = np.clip(pivot + (lum0 - pivot) * contrast, 0, 1) ** gamma
    A = np.clip(A * (new / np.maximum(lum0, 1e-3))[..., None], 0, 1)

    # 线性光 box 降采样
    NR = int(round(cols * H / W))
    if blur > 0:
        A = ndimage.gaussian_filter(A, (blur, blur, 0))
    L = srgb2lin(A)
    small = np.zeros((NR, cols, 3), np.float32)
    for c in range(3):
        ch = Image.fromarray(L[..., c].astype(np.float32), mode="F").resize((cols, NR), Image.BOX)
        small[..., c] = np.asarray(ch)
    G = lin2srgb(small)

    # 局部对比增强（保眼睛）
    lum = 0.299 * G[..., 0] + 0.587 * G[..., 1] + 0.114 * G[..., 2]
    blur = ndimage.gaussian_filter(lum, 0.9)
    G = np.clip(G * (np.clip(lum + sharpen * (lum - blur), 0, 1) / np.maximum(lum, 1e-3))[..., None], 0, 1)
    return G


# ---------------------------------------------------------------- 2. 量化
def quantize(G, sat=1.5, max_colors=99, vib=True):
    NR, NC, _ = G.shape
    lab = rgb2lab(np.clip(G, 0, 1))
    if vib:
        # 鲜艳度（vibrance）：只放大「本来就有颜色」的像素，中性色保持中性
        ch = np.hypot(lab[..., 1], lab[..., 2])
        k = np.clip((ch - 9.0) / 16.0, 0, 1) ** 0.8
        f = 1.0 + (sat - 1.0) * k
        lab[..., 1] = np.clip(lab[..., 1] * f, -110, 110)
        lab[..., 2] = np.clip(lab[..., 2] * f, -110, 110)
    else:
        lab[..., 1:] = np.clip(lab[..., 1:] * sat, -110, 110)
    P_lab = rgb2lab(np.array([hex2rgb(p[1]) for p in PALETTE], np.float32))
    d = ((lab[:, :, None, :] - P_lab[None, None]) ** 2).sum(-1) ** 0.5
    idx = d.argmin(-1)

    de = lambda a, b: float(np.linalg.norm(P_lab[a] - P_lab[b]))
    ch = lambda a: float(np.hypot(P_lab[a][1], P_lab[a][2]))

    for _ in range(3):
        new = idx.copy()
        for y in range(NR):
            for x in range(NC):
                k = idx[y, x]
                if ch(k) > 15:
                    continue
                nb = [idx[y + dy, x + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                      if not (dy == 0 and dx == 0) and 0 <= y + dy < NR and 0 <= x + dx < NC]
                cc = Counter(nb)
                top, tn = cc.most_common(1)[0]
                if cc.get(k, 0) <= 1 and tn >= 3 and top != k and de(k, top) < 12:
                    new[y, x] = top
        if (new == idx).all():
            break
        idx = new

    # 限制色数：软调照片不限制会散成一堆近似灰，读起来很脏
    while True:
        cnt = Counter(idx.ravel().tolist())
        if len(cnt) <= max_colors:
            break
        k = min(cnt, key=lambda k: cnt[k])
        cand = [j for j in cnt if j != k]
        if not cand:
            break
        idx[idx == k] = min(cand, key=lambda j: de(k, j))

    cnt = Counter(idx.ravel().tolist())
    for k, v in list(cnt.items()):
        if v < 4:
            cand = [j for j in cnt if cnt[j] >= 4 and j != k]
            if cand:
                idx[idx == k] = min(cand, key=lambda j: de(k, j))
    cnt = Counter(idx.ravel().tolist())
    keep = sorted(cnt, key=lambda k: -cnt[k])
    out = np.full_like(idx, -1)
    for i, k in enumerate(keep):
        out[idx == k] = i
    pal = [(PALETTE[k][0], PALETTE[k][1], PALETTE[k][2], int(cnt[k])) for k in keep]
    return out, pal




# ---------------------------------------------------------------- 自适应色板
def _kmeans(X, K, iters=45, seed=0):
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), K, replace=False)].copy()
    for _ in range(iters):
        d = ((X[:, None, :] - C[None]) ** 2).sum(-1)
        lb = d.argmin(1)
        for k in range(K):
            m = lb == k
            if m.any():
                C[k] = X[m].mean(0)
    d = ((X[:, None, :] - C[None]) ** 2).sum(-1)
    return C, d.argmin(1)


def build_adaptive_palette(G, K=24, weight_pow=0.45):
    """按图建色板：在 5bit 颜色直方图上做「加权」k-means。
    weight_pow<0.5 会给面积小但独特的颜色更多发言权，
    否则大片单色（比如一整片红花）会把色板名额吃光，山体/天空就没色可用。"""
    q = np.clip((G * 31).round(), 0, 31).astype(np.int32)
    keys = q[..., 0] * 1024 + q[..., 1] * 32 + q[..., 2]
    cnt = np.bincount(keys.ravel(), minlength=32768).astype(np.float32)
    nz = np.nonzero(cnt)[0]
    X = np.stack([(nz // 1024) / 31.0, ((nz // 32) % 32) / 31.0, (nz % 32) / 31.0], -1).astype(np.float32)
    w = cnt[nz] ** weight_pow
    w = w / w.sum()

    rng = np.random.default_rng(0)
    C = [X[rng.choice(len(X), p=w)]]
    for _ in range(K - 1):
        d = ((X[:, None, :] - np.array(C)[None]) ** 2).sum(-1).min(1)
        p_ = d * w
        s_ = p_.sum()
        if s_ <= 0:
            break
        C.append(X[rng.choice(len(X), p=p_ / s_)])
    C = np.array(C, np.float32)

    for _ in range(40):
        d = ((X[:, None, :] - C[None]) ** 2).sum(-1)
        lb = d.argmin(1)
        for k in range(len(C)):
            m = lb == k
            if m.any():
                ww = w[m]
                C[k] = (X[m] * ww[:, None]).sum(0) / ww.sum()

    d = ((X[:, None, :] - C[None]) ** 2).sum(-1)
    lb = d.argmin(1)
    tot = np.bincount(lb, weights=cnt[nz], minlength=len(C))
    keep = [k for k in range(len(C)) if tot[k] > 0]
    C = C[keep]
    lab = rgb2lab(C)

    def family(L, a, b):
        ch = np.hypot(a, b)
        if ch < 9:
            return "W" if L > 62 else ("N" if L > 38 else "K")
        h = (np.degrees(np.arctan2(b, a)) + 360) % 360
        if h < 20 or h >= 330: return "R"
        if h < 55: return "C"
        if h < 95: return "Y"
        if h < 175: return "G"
        if h < 265: return "B"
        return "P"

    groups = {}
    for i, (L, a, b) in enumerate(lab):
        groups.setdefault(family(L, a, b), []).append(i)
    order, codes = [], {}
    for fam in ["W", "N", "K", "C", "Y", "R", "P", "G", "B"]:
        if fam not in groups:
            continue
        for n, i in enumerate(sorted(groups[fam], key=lambda i: -lab[i][0]), 1):
            codes[i] = f"{fam}{n}"
            order.append(i)

    NAMES = {"W": "浅", "N": "灰", "K": "深", "C": "驼", "Y": "黄",
             "R": "红", "P": "紫粉", "G": "绿", "B": "蓝"}
    pal = []
    for i in order:
        rgb = np.clip(C[i], 0, 1)
        hx = "#%02X%02X%02X" % tuple((rgb * 255).astype(int))
        fam = codes[i][0]
        pal.append([codes[i], hx, f"{NAMES[fam]}{codes[i][1:]}", int(tot[keep[i]])])
    return pal


def apply_adaptive(G, pal):
    P = np.array([hex2rgb(p[1]) for p in pal], np.float32)
    flat = G.reshape(-1, 3)
    idx = ((flat[:, None, :] - P[None]) ** 2).sum(-1).argmin(1)
    return idx.reshape(G.shape[:2]), pal


# ---------------------------------------------------------------- 3. 豆子贴图
def bead_tile(rgb, size, ss=4):
    n = size * ss
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    c = (n - 1) / 2
    dx, dy = (xx - c) / (n / 2), (yy - c) / (n / 2)
    r = np.hypot(dx, dy)
    R = 0.965
    shade = 1.0 + 0.20 * (-(dx + dy) / 2.0) - 0.10 * r ** 2
    shade *= 1.0 - 0.16 * np.clip((r - R * 0.72) / (R * 0.28), 0, 1) ** 1.6
    col = np.array(rgb, np.float32)[None, None, :] * shade[..., None]
    ring = np.exp(-((r - 0.60 * R) ** 2) / (2 * (0.055 * R) ** 2)) * 0.55
    col = col + (1 - col) * ring[..., None] * 0.55
    inner = np.clip((0.295 * R - r) / (0.05 * R), 0, 1) * (r > 0.20 * R)
    col = col * (1 - 0.30 * inner[..., None])
    sp = np.exp(-(((dx + 0.34) ** 2 + (dy + 0.40) ** 2)) / (2 * 0.20 ** 2))
    col = col + (1 - col) * (sp[..., None] * 0.55)
    a = np.clip((R - r) / 0.035, 0, 1) * 255
    a = a * (1 - np.clip((0.245 * R - r) / (0.05 * R), 0, 1))
    rgba = np.dstack([np.clip(col, 0, 1) * 255, a]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA").resize((size, size), Image.LANCZOS)


def render_preview(idx, pal, cell=20, pad=46, bg=(247, 244, 238)):
    NR, NC = idx.shape
    W, H = NC * cell + pad * 2, NR * cell + pad * 2
    rng = np.random.default_rng(7)
    canvas = np.zeros((H, W, 3), np.float32) + np.array(bg, np.float32)
    canvas += rng.normal(0, 3.0, (H, W, 1))
    gy, gx = np.mgrid[0:H, 0:W]
    canvas *= (1 - 0.05 * ((gy / H - .5) ** 2 + (gx / W - .5) ** 2))[..., None]
    canvas = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8))

    # 整块投影
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).rectangle([pad, pad, pad + NC * cell, pad + NR * cell], fill=255)
    sh = ImageChops.offset(m.filter(ImageFilter.GaussianBlur(13)), 0, 8)
    canvas.paste((58, 56, 54), (0, 0), sh.point(lambda v: int(v * 0.40)))

    # 豆间缝隙铺暗底，避免露白
    d = ImageDraw.Draw(canvas)
    for y in range(NR):
        for x in range(NC):
            k = idx[y, x]
            if k < 0:
                continue
            r, g, b = hex2rgb(pal[k][1]) * 255 * 0.52
            d.rectangle([pad + x * cell, pad + y * cell,
                         pad + (x + 1) * cell, pad + (y + 1) * cell],
                        fill=(int(r), int(g), int(b)))

    tiles = {i: bead_tile(hex2rgb(p[1]), cell) for i, p in enumerate(pal)}
    for y in range(NR):
        for x in range(NC):
            k = idx[y, x]
            if k >= 0:
                canvas.paste(tiles[k], (pad + x * cell, pad + y * cell), tiles[k])
    return canvas


# ---------------------------------------------------------------- 4. 全图图纸
def render_chart(idx, pal, name, cell=30, ruler=True):
    NR, NC = idx.shape
    M_L, M_T, M_R, M_B = (74 if ruler else 34), 132, 40, 40
    per_row = 8
    leg_rows = (len(pal) + per_row - 1) // per_row
    legend_h = 52 + leg_rows * 58
    W = M_L + NC * cell + M_R
    H = M_T + NR * cell + M_B + legend_h
    im = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(im)

    # 标题
    dr.text((M_L, 34), f"{name} · 拼豆图纸", font=F(34, True), fill=(28, 30, 36))
    dr.text((M_L, 78), f"PERLER BEAD CHART　{NC} × {NR} 格　·　{len(pal)} 色　·　{NC*NR} 颗",
            font=F(17), fill=(120, 124, 134))

    X0, Y0 = M_L, M_T
    # 底色
    dr.rectangle([X0, Y0, X0 + NC * cell, Y0 + NR * cell], fill=(252, 252, 253))
    # 色块
    RGB = [(np.array(hex2rgb(p[1])) * 255).astype(int) for p in pal]
    for y in range(NR):
        for x in range(NC):
            k = idx[y, x]
            if k < 0:
                continue
            r, g, b = RGB[k]
            dr.rectangle([X0 + x * cell, Y0 + y * cell, X0 + (x + 1) * cell, Y0 + (y + 1) * cell],
                         fill=(int(r), int(g), int(b)))
    # 网格线
    for c in range(NC + 1):
        w = 2 if c % 10 == 0 else 1
        col = (150, 152, 158) if c % 10 == 0 else (218, 219, 223)
        dr.line([X0 + c * cell, Y0, X0 + c * cell, Y0 + NR * cell], fill=col, width=w)
    for r in range(NR + 1):
        w = 2 if r % 10 == 0 else 1
        col = (150, 152, 158) if r % 10 == 0 else (218, 219, 223)
        dr.line([X0, Y0 + r * cell, X0 + NC * cell, Y0 + r * cell], fill=col, width=w)

    # 色号文字
    fs = F(max(8, int(cell * 0.30)), True)
    for y in range(NR):
        for x in range(NC):
            k = idx[y, x]
            if k < 0:
                continue
            r, g, b = RGB[k]
            lum = .299 * r + .587 * g + .114 * b
            dr.text((X0 + x * cell + cell / 2, Y0 + y * cell + cell / 2), pal[k][0],
                    font=fs, fill=(255, 255, 255) if lum < 140 else (38, 38, 44), anchor="mm")

    # 坐标尺
    if ruler:
        fnum = F(12)
        for c in range(NC):
            if (c + 1) % 5 == 0 or c == 0:
                dr.text((X0 + c * cell + cell / 2, Y0 - 12), str(c + 1), font=fnum,
                        fill=(120, 124, 134), anchor="ms")
        for r in range(NR):
            if (r + 1) % 5 == 0 or r == 0:
                dr.text((X0 - 12, Y0 + r * cell + cell / 2), str(r + 1), font=fnum,
                        fill=(120, 124, 134), anchor="rm")

    # 色卡
    ly = H - legend_h + 34
    dr.line([M_L, ly - 22, W - M_R, ly - 22], fill=(226, 227, 231), width=1)
    cw = (W - M_L - M_R) / per_row
    for i, p in enumerate(pal):
        cx = M_L + (i % per_row) * cw
        cy = ly + (i // per_row) * 58
        r, g, b = RGB[i]
        dr.rounded_rectangle([cx, cy, cx + 30, cy + 30], 5, fill=(int(r), int(g), int(b)),
                             outline=(196, 197, 201), width=1)
        dr.text((cx + 40, cy - 1), p[0], font=F(15, True), fill=(30, 32, 38))
        dr.text((cx + 40, cy + 17), f"{p[2]} · {p[3]}", font=F(11), fill=(132, 136, 146))
    return im


# ---------------------------------------------------------------- 5. 封面
def render_cover(prev, name, cols, rows, ncolor, nbead, size=(1080, 1440)):
    W, H = size
    # 铺底
    cov = Image.new("RGB", size, (247, 244, 238))
    s = max(W / prev.width, H / prev.height)
    pw, ph = int(prev.width * s), int(prev.height * s)
    p = prev.resize((pw, ph), Image.LANCZOS)
    cov.paste(p, ((W - pw) // 2, (H - ph) // 2 - 60))
    # 底部渐变
    grad = Image.new("L", (1, H), 0)
    for i in range(H):
        v = 0 if i < H * 0.55 else int(215 * ((i - H * 0.55) / (H * 0.45)) ** 1.5)
        grad.putpixel((0, i), min(v, 215))
    grad = grad.resize((W, H))
    cov = Image.composite(Image.new("RGB", size, (24, 22, 26)), cov, grad)

    dr = ImageDraw.Draw(cov)
    dr.text((72, H - 250), name, font=F(76, True), fill=(255, 255, 255))
    dr.text((74, H - 158), f"{cols} × {rows} 格　·　{ncolor} 色　·　{nbead} 颗", font=F(30), fill=(236, 232, 228))
    dr.rounded_rectangle([72, H - 96, 72 + 330, H - 44], 26, fill=(255, 255, 255))
    dr.text((72 + 165, H - 70), "照片 → 拼豆图纸", font=F(26, True), fill=(40, 36, 34), anchor="mm")
    return cov


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--crop", default="")
    ap.add_argument("--cols", type=int, default=64)
    ap.add_argument("--name", default="作品")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--junk", default="")
    ap.add_argument("--sat", type=float, default=1.5)
    ap.add_argument("--contrast", type=float, default=1.18)
    ap.add_argument("--gamma", type=float, default=0.97)
    ap.add_argument("--pivot", type=float, default=0.62)
    ap.add_argument("--noauto", action="store_true")
    ap.add_argument("--wb", type=float, default=0.55)
    ap.add_argument("--colors", type=int, default=99)
    ap.add_argument("--adaptive", type=int, default=0)
    ap.add_argument("--sharpen", type=float, default=0.5)
    ap.add_argument("--novib", action="store_true")
    ap.add_argument("--blur", type=float, default=0.0)
    ap.add_argument("--level", default="")
    ap.add_argument("--cell", type=int, default=20)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    im0 = Image.open(a.src)
    crop = tuple(int(v) for v in a.crop.split(",")) if a.crop else (0, 0, *im0.size)
    junk = tuple(int(v) for v in a.junk.split(",")) if a.junk else None

    G = make_grid(a.src, crop, a.cols, junk=junk, contrast=a.contrast, gamma=a.gamma,
                  pivot=a.pivot, auto=not a.noauto, wb=a.wb, sharpen=a.sharpen, level=a.level,
                  blur=a.blur)
    if a.adaptive:
        pal = build_adaptive_palette(G, a.adaptive)
        idx, pal = apply_adaptive(G, pal)
    else:
        idx, pal = quantize(G, sat=a.sat, max_colors=a.colors, vib=not a.novib)
    NR, NC = idx.shape
    print(f"grid {NC}x{NR}  beads {NC*NR}  colors {len(pal)}")

    prev = render_preview(idx, pal, cell=a.cell)
    prev.save(os.path.join(a.outdir, "01_成品预览.png"))

    chart = render_chart(idx, pal, a.name)
    chart.save(os.path.join(a.outdir, "02_图纸_全图.png"))

    cov = render_cover(prev, a.name, NC, NR, len(pal), NC * NR)
    cov.save(os.path.join(a.outdir, "03_小红书封面.png"))

    json.dump({"name": a.name, "cols": NC, "rows": NR, "palette": pal},
              open(os.path.join(a.outdir, "spec.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    np.save(os.path.join(a.outdir, "idx.npy"), idx)
    print("done ->", a.outdir)


if __name__ == "__main__":
    main()
