# -*- coding: utf-8 -*-
"""batch34.py —— 34 张素材统一出图（原图/成品图/色彩图/对比图 + 带标/无标 + 台账）"""
import os, sys, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops
from scipy import ndimage
import brand as BR
import cutout as CO
import beadify as B

from config import CFG as _CFG

SRC = _CFG["paths"]["src"]      # 素材目录（改 config.json）
OUT = _CFG["paths"]["out"]      # 交付目录（改 config.json）
CARD = (_CFG["render"]["card_w"], _CFG["render"]["card_h"])

# 文件名 -> (作品名, 列数, 裁切框或None, 去水印矩形列表)
CFG = {
    "肌肉Kitty.jpg":  ("肌肉Kitty", 80, (61, 76, 503, 612), []),
    "开心路飞.jpg":    ("开心路飞", 80, (246, 471, 853, 1388), []),
    "猫猫美图.jpg":    ("猫猫美图", 80, (22, 13, 727, 1296), []),
    "迷路索隆.jpg":    ("迷路索隆", 80, (252, 850, 457, 1165), []),
    "蜜汁山治.png":    ("蜜汁山治", 80, (124, 580, 934, 1336), []),
    "尼卡路飞.jpg":    ("尼卡路飞", 80, (94, 81, 636, 666), []),
    "乔巴帽子.jpg":    ("乔巴帽子", 80, (70, 121, 528, 476), []),
    "三小只.jpg":      ("三小只", 80, (250, 340, 400, 560), []),
    "山治火腿.jpg":    ("山治火腿", 80, (83, 703, 664, 1237), []),
    "耍帅路飞.jpg":    ("耍帅路飞", 80, (7, 47, 1139, 2040), [(875, 1700, 1148, 1820)]),
    "睡觉路飞.jpg":    ("睡觉路飞", 80, (198, 525, 882, 1325), []),
    "索隆帽子.jpg":    ("索隆帽子", 80, (219, 732, 548, 951), []),
    "索隆之眼.jpg":    ("索隆之眼", 80, (220, 163, 903, 527), []),
    "探头山治.jpg":    ("探头山治", 80, (195, 417, 540, 713), []),
    "完整路飞.jpg":    ("完整路飞", 80, (7, 279, 719, 1006), []),
    "完整猫猫.jpg":    ("完整猫猫", 80, (7, 7, 824, 1208), []),
    "完整索隆.jpg":    ("完整索隆", 80, (67, 181, 669, 923), []),
    "万圣Kitty.jpg":  ("万圣Kitty", 80, (305, 280, 894, 919), []),
    "笑脸路飞.jpg":    ("笑脸路飞", 80, (50, 192, 684, 929), []),
    "修炼索隆.jpg":    ("修炼索隆", 80, (120, 470, 520, 870), []),
    "幽灵Kitty.jpg":  ("幽灵Kitty", 80, (101, 92, 614, 655), []),
    "Q版猫2.jpg":      ("Q版猫2", 80, (202, 523, 530, 841), []),
    "Q版猫猫.jpg":     ("Q版猫猫", 80, (18, 13, 317, 374), []),
    "Q版山治.jpg":     ("Q版山治", 80, (240, 600, 500, 905), []),
    "艾斯帽子.jpg":    ("艾斯帽子", 80, (190, 750, 528, 905), []),
    "霸总Kitty.jpg":  ("霸总Kitty", 80, (7, 7, 948, 1468), []),
    "半边山治.jpg":    ("半边山治", 80, (7, 341, 712, 1120), []),
    "半脸路飞.jpg":    ("半脸路飞", 80, (220, 223, 731, 1562), []),
    "草莓Kitty.jpg":  ("草莓Kitty", 80, None, []),
    "侧面索隆.jpg":    ("侧面索隆", 80, (91, 18, 620, 742), []),
    "大头猫猫.jpg":    ("大头猫猫", 80, (7, 7, 687, 712), []),
    "独眼索隆.jpg":    ("独眼索隆", 80, (381, 685, 699, 1229), []),
    "粉色猫猫.jpg":    ("粉色猫猫", 80, (7, 13, 721, 1013), []),
    "花朵山治.jpg":    ("花朵山治", 80, (177, 808, 544, 1277), []),
}

HARD = {"草莓Kitty.jpg": (0, 0, 847, 766), "Q版山治.jpg": (0, 0, 736, 905)}
# 平色判据抠不干净、或背景和主体同色系 → 改走 grabCut
GRAB = {"完整猫猫.jpg", "猫猫美图.jpg"}

CARD = (1080, 1440)      # 原图卡片统一尺寸


def clone_fill(im, rect):
    """用上方一条区域覆盖（适合纯色/渐变背景上的水印）"""
    x0, y0, x1, y1 = rect
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(im.width, x1), min(im.height, y1)
    h = y1 - y0
    src_y0 = max(0, y0 - h - 8)
    src_y1 = src_y0 + h
    if src_y1 - src_y0 < h or x1 <= x0:
        return im
    patch = im.crop((x0, src_y0, x1, src_y1))
    im.paste(patch, (x0, y0))
    return im


def center_square(im, pad=0.0):
    s = min(im.width, im.height)
    l = (im.width - s) // 2
    t = (im.height - s) // 2
    return im.crop((l, t, l + s, t + s))


def median_fill(im, rect, feather=6):
    """用四周一圈的中位色填掉矩形（适合纯色/浅渐变背景上的文字水印）"""
    x0, y0, x1, y1 = rect
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(im.width, x1), min(im.height, y1)
    if x1 <= x0 or y1 <= y0:
        return im
    m = 12
    ring = []
    for yy in range(max(0, y0 - m), min(im.height, y1 + m)):
        for xx in (max(0, x0 - m), min(im.width - 1, x1 + m - 1)):
            ring.append(im.getpixel((xx, yy)))
    for xx in range(max(0, x0 - m), min(im.width, x1 + m)):
        for yy in (max(0, y0 - m), min(im.height - 1, y1 + m - 1)):
            ring.append(im.getpixel((xx, yy)))
    if not ring:
        return im
    col = tuple(int(v) for v in np.median(np.array(ring, np.float32), 0))
    patch = Image.new("RGB", (x1 - x0, y1 - y0), col)
    mask = Image.new("L", (x1 - x0, y1 - y0), 255)
    if feather > 0:
        d = ImageDraw.Draw(mask)
        for k in range(feather):
            v = int(255 * k / feather)
            d.rectangle([k, k, mask.width - 1 - k, mask.height - 1 - k], outline=v)
    im.paste(patch, (x0, y0), mask)
    return im


def square_crop(im, box, pad=0.06):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    side = int(max(w, h) * (1 + pad * 2))
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    l, t = cx - side // 2, cy - side // 2
    # 越界时整体平移，不裁掉主体
    if l < 0:
        l = 0
    if t < 0:
        t = 0
    if l + side > im.width:
        l = max(0, im.width - side)
    if t + side > im.height:
        t = max(0, im.height - side)
    side = min(side, im.width, im.height)
    return im.crop((l, t, l + side, t + side))


# ---------------------------------------------------------------- 拼豆核心
def beadify(img, cols, K=32, cleanup=True):
    """扁平插画专用：按图建板 → 逐像素量化 → 整格众数（暗色优先保住描边）"""
    im = img.convert("RGB")
    W, H = im.size
    n = max(2, W // cols)
    im2 = im.crop((0, 0, n * cols, n * (H // n)))
    NR = im2.height // n

    A = np.asarray(im2).astype(np.float32) / 255.0
    # 轻度鲜艳度：豆子渲染会吃掉一点饱和度，这里补回来（中性色不动）
    mean = A.mean(axis=2, keepdims=True)
    ch = np.abs(A - mean).max(axis=2, keepdims=True)
    kk = np.clip(ch / 0.14, 0, 1)
    A = np.clip(A + (A - mean) * (0.20 * kk), 0, 1)
    pal = B.build_adaptive_palette(A, K)
    # 合并 ΔE 太近的色，避免同一片背景在几个近似色之间来回跳
    Pl = B.rgb2lab(np.array([B.hex2rgb(p[1]) for p in pal], np.float32))
    merged, keep_idx = [], []
    for i in range(len(pal)):
        for j in keep_idx:
            if np.linalg.norm(Pl[i] - Pl[j]) < 7:
                break
        else:
            keep_idx.append(i)
    pal = [pal[i] for i in keep_idx]
    P = np.array([B.hex2rgb(p[1]) for p in pal], np.float32)
    flat = A.reshape(-1, 3)
    pidx = ((flat[:, None, :] - P[None]) ** 2).sum(-1).argmin(1).reshape(im2.height, im2.width)

    # 暗色（描边）优先
    lum = (P * [0.299, 0.587, 0.114]).sum(1)
    dark_ids = np.where(lum < 0.32)[0]

    grid = np.zeros((NR, cols), np.int16)
    for r in range(NR):
        for c in range(cols):
            blk = pidx[r * n:(r + 1) * n, c * n:(c + 1) * n].ravel()
            cnt = np.bincount(blk, minlength=len(pal))
            best = int(cnt.argmax())
            if len(dark_ids):
                if cnt[dark_ids].sum() / blk.size > 0.22:
                    best = int(dark_ids[cnt[dark_ids].argmax()])
            grid[r, c] = best

    # 清掉平坦区域的碎点（背景噪点）；描边色和「高饱和点缀色」都不动
    Plab = B.rgb2lab(P)
    chroma = np.hypot(Plab[:, 1], Plab[:, 2])
    for _ in range(3 if cleanup else 0):
        new = grid.copy()
        for r in range(NR):
            for c in range(cols):
                k = grid[r, c]
                if lum[k] < 0.32 or chroma[k] > 22:
                    continue
                nb = [grid[r + dy, c + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                      if not (dy == 0 and dx == 0) and 0 <= r + dy < NR and 0 <= c + dx < cols]
                vals, cnts = np.unique(nb, return_counts=True)
                top = int(vals[cnts.argmax()])
                if top != k and cnts.max() >= 5:
                    new[r, c] = top
        if (new == grid).all():
            break
        grid = new

    used = np.bincount(grid.ravel(), minlength=len(pal))
    keep = [i for i in range(len(pal)) if used[i] > 0]
    remap = {k: j for j, k in enumerate(keep)}
    grid2 = np.vectorize(remap.get)(grid).astype(np.int16)
    pal2 = [(pal[k][0], pal[k][1], pal[k][2], int(used[k])) for k in keep]
    # 闭环校正：豆子渲染自带阴影，按原图平均色反推补偿
    m = BR.mosaic(grid2, pal2, 14).convert("RGB")
    a = np.asarray(m).astype(np.float32) / 255.0
    alpha = np.asarray(BR.mosaic(grid2, pal2, 14).split()[3]) > 40
    got = a[alpha].mean(0)
    want = A.reshape(-1, 3).mean(0)
    ratio = np.clip(want / np.maximum(got, 1e-3), 0.90, 1.20)
    out = []
    for code, hx, nm, cnt in pal2:
        rgb = np.clip(B.hex2rgb(hx) * ratio, 0, 1)
        out.append((code, "#%02X%02X%02X" % tuple((rgb * 255).astype(int)), nm, cnt))
    return grid2, out


def to_card(img, size=CARD):
    """把原图放到通用背景纸上（pintoo 版式）"""
    W, H = size
    canvas = BR.paper(W, H)
    s = min((W * 0.66) / img.width, (H * 0.72) / img.height)
    w, h = int(img.width * s), int(img.height * s)
    t = img.resize((w, h), Image.LANCZOS)
    x, y = (W - w) // 2, int(H * 0.45) - h // 2

    mask = Image.new("L", (W, H), 0)
    if t.mode == "RGBA":
        mask.paste(t.split()[3], (x, y))
    else:
        ImageDraw.Draw(mask).rectangle([x, y, x + w, y + h], fill=255)
    sh = ImageChops.offset(mask.filter(ImageFilter.GaussianBlur(18)), 0, 10)
    canvas.paste((120, 112, 102), (0, 0), sh.point(lambda v: int(v * 0.34)))
    canvas.paste(t, (x, y), t if t.mode == "RGBA" else None)
    BR.watermark(canvas, BR.WM, (x, y, x + w, y + h), size=max(48, w // 7), alpha=118, spacing=1.25)
    BR.brand_footer(canvas, scale=1.0)
    return canvas


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for i, (fn, (name, cols, crop, wms)) in enumerate(sorted(CFG.items()), 1):
        src = os.path.join(SRC, fn)
        if not os.path.exists(src):
            print("MISS", fn); continue
        im = Image.open(src).convert("RGB")
        for r in wms:
            if isinstance(r, str):
                im = median_fill(im, tuple(int(v) for v in r.split(":")[1].split(",")))
            else:
                im = clone_fill(im, r)
        if fn in HARD:
            im = im.crop(HARD[fn])
        im = square_crop(im, crop) if crop else center_square(im)

        d = os.path.join(OUT, f"{i:02d}_{name}")
        dn = os.path.join(OUT, "无LOGO版", f"{i:02d}_{name}")
        os.makedirs(d, exist_ok=True)
        os.makedirs(dn, exist_ok=True)

        # 01 原图（放到通用背景纸）
        to_card(im).save(os.path.join(d, "01_原图.png"))
        plain = BR.paper(*CARD)
        s = min((CARD[0] * 0.62) / im.width, (CARD[1] * 0.70) / im.height)
        t = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        plain.paste(t, ((CARD[0] - t.width) // 2, int(CARD[1] * 0.45) - t.height // 2))
        plain.save(os.path.join(dn, "01_原图_无标.png"))

        # 02/03/04
        grid, pal = beadify(im, cols)
        BR.render_card(grid, pal).save(os.path.join(d, "02_成品图.png"))
        BR.render_chart(grid, pal, name).save(os.path.join(d, "03_色彩图.png"))
        BR.render_compare(im, BR.mosaic(grid, pal, 18), name).save(os.path.join(d, "04_对比图.png"))

        BR.render_card(grid, pal, mark=False).save(os.path.join(dn, "02_成品图_无标.png"))
        BR.render_chart(grid, pal, name, mark=False).save(os.path.join(dn, "03_色彩图_无标.png"))
        BR.render_compare(im, BR.mosaic(grid, pal, 18), name, mark=False).save(os.path.join(dn, "04_对比图_无标.png"))

        NR, NC = grid.shape
        rows.append(dict(no=i, name=name, file=fn, cols=int(NC), rows=int(NR),
                         beads=int(NC * NR), colors=len(pal),
                         path=d, thumb=os.path.join(d, "01_原图.png")))
        print(f"{i:02d} {name:10s} {NC}x{NR} {len(pal):2d}色 {NC*NR:5d}颗")

    json.dump(rows, open(os.path.join(OUT, "_rows.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("DONE", len(rows))


if __name__ == "__main__":
    main()
