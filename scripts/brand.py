# -*- coding: utf-8 -*-
"""brand.py —— 带 LOGO / 水印的成品包装（仿 pintoo 版式）"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

from config import CFG

# ---------- 字体：自动找系统里的中文字体（Windows / macOS / Linux） ----------
_FONT_CANDIDATES = {
    True: [
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ],
    False: [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ],
}


def _find_font(bold):
    import os
    env = os.environ.get("PINDOU_FONT_BOLD" if bold else "PINDOU_FONT")
    if env and os.path.exists(env):
        return env
    for f in _FONT_CANDIDATES[bool(bold)]:
        if os.path.exists(f):
            return f
    return None


FONT = _find_font(False)
FONTB = _find_font(True) or FONT


def fnt(size, bold=False):
    path = FONTB if bold else FONT
    if path:
        try:
            return ImageFont.truetype(path, size, index=0)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


# ============ 品牌（读 config.json，换品牌不用改代码） ============
BRAND = CFG["brand"]["name"]
BRAND_SUB = CFG["brand"].get("en", "")
_c = CFG["brand"].get("color", "#C6705C").lstrip("#")
BRAND_COLOR = tuple(int(_c[i:i+2], 16) for i in (0, 2, 4))
INK = (38, 36, 40)
SUB = (140, 137, 142)
PAPER = (238, 236, 231)
WM = CFG["brand"].get("watermark") or ("@" + BRAND)


def hex2rgb(h):
    return np.array([int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)], np.float32) / 255


def paper(w, h, base=None, style=None):
    style = style or CFG["render"].get("paper_style", "linen")
    if base is None:
        base = {"linen": PAPER, "plain": (250, 249, 246), "dark": (54, 52, 56)}[style]
    if style != "linen":
        return Image.new("RGB", (w, h), base)
    """亚麻布贴纸：可见经纬织纹 + 纤维 + 折痕 + 定向光"""
    from scipy import ndimage
    rng = np.random.default_rng(11)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)

    T = 5.0                                   # 一根纱的宽度
    ph_x = rng.uniform(0, 2*np.pi, max(2, int(w / T) + 2))
    ph_y = rng.uniform(0, 2*np.pi, max(2, int(h / T) + 2))
    ix = np.clip((xx / T).astype(np.int32), 0, len(ph_x)-1)
    iy = np.clip((yy / T).astype(np.int32), 0, len(ph_y)-1)

    # 经线（竖）与纬线（横）：一根亮一根暗，交错像平纹
    vx = np.cos(xx * 2*np.pi/T + ph_x[ix]) * 0.5 + 0.5
    hy = np.cos(yy * 2*np.pi/T + ph_y[iy]) * 0.5 + 0.5
    weave = (vx * 0.55 + hy * 0.55) - 0.55
    # 平纹交错：交叉处压暗
    weave -= (vx * hy) * 0.30

    arr = np.zeros((h, w, 3), np.float32) + np.array(base, np.float32)
    arr += weave[..., None] * 15.0

    # 短纤维
    g = rng.normal(0, 1, (h, w)).astype(np.float32)
    arr += ndimage.gaussian_filter(g, 0.55)[..., None] * 7.0
    # 长纤维（横向）
    f2 = rng.normal(0, 1, (max(2, h//5), max(2, w//35))).astype(np.float32)
    f2 = np.asarray(Image.fromarray(((f2-f2.min())/(np.ptp(f2)+1e-6)*255).astype(np.uint8))
                    .resize((w, h), Image.BICUBIC), np.float32)/255 - .5
    arr += f2[..., None] * 6.0
    # 软折
    c = rng.normal(0, 1, (max(2, h//30), max(2, w//30))).astype(np.float32)
    c = np.asarray(Image.fromarray(((c-c.min())/(np.ptp(c)+1e-6)*255).astype(np.uint8))
                   .resize((w, h), Image.BICUBIC), np.float32)/255 - .5
    arr += ndimage.gaussian_filter(c, 14)[..., None] * 12.0

    lx, ly = xx / w, yy / h
    arr *= (1.0 + 0.07 * (1 - (lx*.7 + ly*.5)))[..., None]
    d = np.hypot(lx - .48, ly - .42)
    arr *= (1 - 0.13 * np.clip(d * 1.7, 0, 1) ** 2)[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def logo(size=64, color=BRAND_COLOR):
    """3×3 小豆格组成的标记"""
    S = size * 4
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = S * 0.10
    gap = S * 0.055
    cell = (S - pad * 2 - gap * 2) / 3
    for i in range(3):
        for j in range(3):
            x = pad + i * (cell + gap)
            y = pad + j * (cell + gap)
            d.ellipse([x, y, x + cell, y + cell], fill=color + (255,))
            h = cell * 0.26
            d.ellipse([x + cell / 2 - h, y + cell / 2 - h, x + cell / 2 + h, y + cell / 2 + h],
                      fill=(255, 255, 255, 235))
    return im.resize((size, size), Image.LANCZOS)


def _wm_tile(text, font, angle=28, pad=26):
    """白字 + 深色描边，任何底色上都读得出来"""
    tw = int(font.getlength(text)) + pad * 2
    th = font.size + pad * 2
    t = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(t)
    d.text((tw // 2, th // 2), text, font=font, fill=(146, 144, 148, 255),
           anchor="mm", stroke_width=max(2, font.size // 14), stroke_fill=(255, 255, 255, 235))
    return t.rotate(angle, expand=True, resample=Image.BICUBIC)


def watermark(canvas, text, box, size=64, alpha=118, angle=28, spacing=1.22):
    """在指定区域内斜向铺满水印（这是防盗的核心，必须压在图案上）"""
    x0, y0, x1, y1 = [int(v) for v in box]
    W, H = canvas.size
    tile = _wm_tile(text, fnt(size, True), angle)
    a = np.asarray(tile.split()[3]).astype(np.float32) * (alpha / 255.0)
    tile.putalpha(Image.fromarray(a.astype(np.uint8)))

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sx = int(tile.width * spacing)
    sy = int(tile.height * spacing)
    row = 0
    for y in range(y0, y1, max(sy, 40)):
        off = (row % 2) * (sx // 2)
        for x in range(x0, x1, max(sx, 40)):
            layer.paste(tile, (x + off, y), tile)
        row += 1

    mask = Image.new("L", (W, H), 0)
    mask.paste(255, (x0, y0, x1, y1))
    layer.putalpha(ImageChops.multiply(layer.split()[3], mask))
    canvas.paste(layer, (0, 0), layer)


def brand_footer(canvas, y=None, scale=1.0):
    W, H = canvas.size
    y = int(H - 52 * scale) if y is None else int(y)
    lg = logo(int(26 * scale))
    f = fnt(int(24 * scale), True)
    sub = fnt(int(13 * scale))
    tw = f.getlength(BRAND)
    total = lg.width + 10 + tw
    x0 = int((W - total) // 2)
    canvas.paste(lg, (x0, int(y - lg.height // 2)), lg)
    d = ImageDraw.Draw(canvas)
    d.text((x0 + lg.width + 10, y), "@" + BRAND, font=f, fill=(96, 94, 98), anchor="lm")
    d.text((W // 2, int(y + 26 * scale)), BRAND_SUB, font=sub, fill=(176, 173, 176), anchor="mm")


# ---------------------------------------------------------------- 成品卡 3:4
def render_card(idx, pal, cell=20, size=(1080, 1440), mark=True):
    NR, NC = idx.shape
    W, H = size
    canvas = paper(W, H)

    bead = mosaic(idx, pal, cell)

    # 放大到画面宽度的 84%，留出投影空间
    target_w = int(W * 0.84)
    s_ = target_w / bead.width
    bw, bh = int(bead.width * s_), int(bead.height * s_)
    if bh > H * 0.82:
        s_ = (H * 0.82) / bead.height
        bw, bh = int(bead.width * s_), int(bead.height * s_)
    bead = bead.resize((bw, bh), Image.LANCZOS)

    bx = (W - bw) // 2
    by = int(H * 0.47) - bh // 2

    alpha = bead.split()[3]

    # 1) 大范围柔和投影（豆板离纸的距离感）
    sh = Image.new("L", (W, H), 0)
    sh.paste(alpha, (bx, by + 16))
    sh = sh.filter(ImageFilter.GaussianBlur(26))
    canvas.paste((126, 118, 108), (0, 0), sh.point(lambda v: int(v * 0.46)))

    # 2) 紧贴边缘的接触阴影
    sh2 = Image.new("L", (W, H), 0)
    sh2.paste(alpha, (bx, by + 4))
    sh2 = sh2.filter(ImageFilter.GaussianBlur(5))
    canvas.paste((88, 82, 76), (0, 0), sh2.point(lambda v: int(v * 0.34)))

    # 3) 豆板侧面（厚度）—— 底边和右边加一条暗边
    body = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(body)
    bd.rectangle([bx, by + 5, bx + bw, by + bh + 5], fill=(58, 54, 50, 235))
    body.putalpha(ImageChops.multiply(body.split()[3], alpha.transform(
        (W, H), Image.AFFINE, (1, 0, 0, 0, 1, -6), resample=Image.BILINEAR)))
    canvas.paste(body, (0, 0), body)

    # 4) 豆板顶面
    canvas.paste(bead, (bx, by), bead)

    # 5) 顶边一道细高光，像受光的边缘
    hl = Image.new("L", (W, H), 0)
    ImageDraw.Draw(hl).rectangle([bx, by, bx + bw, by + 2], fill=90)
    canvas.paste((255, 255, 255), (0, 0), ImageChops.multiply(hl, alpha))

    if mark:
        watermark(canvas, WM, (bx, by, bx + bw, by + bh),
                  size=max(28, bw // 15), alpha=155, spacing=0.92)
        brand_footer(canvas, scale=1.0)
    return canvas


def mosaic(idx, pal, cell=20):
    NR, NC = idx.shape
    bead = Image.new("RGBA", (NC * cell, NR * cell), (0, 0, 0, 0))
    d = ImageDraw.Draw(bead)
    for y in range(NR):
        for x in range(NC):
            k = idx[y, x]
            if k < 0:
                continue
            c0 = hex2rgb(pal[k][1])
            lum0 = 0.299 * c0[0] + 0.587 * c0[1] + 0.114 * c0[2]
            f = 0.66 + 0.32 * lum0          # 白 → 0.98（几乎无缝），黑 → 0.66
            r, g, b = c0 * 255 * f
            d.rectangle([x * cell, y * cell, (x + 1) * cell, (y + 1) * cell],
                        fill=(int(r), int(g), int(b)))
    tiles = {i: _bead(hex2rgb(p[1]), cell) for i, p in enumerate(pal)}
    for y in range(NR):
        for x in range(NC):
            k = idx[y, x]
            if k >= 0:
                bead.paste(tiles[k], (x * cell, y * cell), tiles[k])
    return bead


def calibrate(idx, pal, target_mean, cell=16):
    """闭环校正：豆子渲染自带阴影，成品平均比原图暗。量出偏差反推修正色板"""
    m = mosaic(idx, pal, cell).convert("RGB")
    a = np.asarray(m).astype(np.float32) / 255.0
    mask = np.asarray(mosaic(idx, pal, cell).split()[3]) > 40
    got = a[mask].mean(0)
    ratio = np.clip(np.asarray(target_mean) / np.maximum(got, 1e-3), 0.88, 1.22)
    out = []
    for code, hx, nm, cnt in pal:
        rgb = np.clip(hex2rgb(hx) * ratio, 0, 1)
        out.append((code, "#%02X%02X%02X" % tuple((rgb * 255).astype(int)), nm, cnt))
    return out, ratio


def _bead(rgb, size, ss=4):
    n = size * ss
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    c = (n - 1) / 2
    dx, dy = (xx - c) / (n / 2), (yy - c) / (n / 2)
    r = np.hypot(dx, dy)
    base = np.array(rgb, np.float32)
    shade = 1.0 + 0.075 * (-dy) - 0.02 * r ** 2
    shade *= 1.0 - 0.10 * np.clip((r - 0.86) / 0.20, 0, 1) ** 1.4
    hole = 0.30
    wall = np.clip((hole + 0.10 - r) / 0.10, 0, 1) * (r > hole - 0.06)
    shade *= 1.0 - 0.20 * wall
    shade *= 1.0 - 0.28 * np.clip((hole - r) / 0.05, 0, 1)
    col = base[None, None, :] * shade[..., None]
    sp = np.exp(-(((dx + 0.30) ** 2 + (dy + 0.36) ** 2)) / (2 * 0.22 ** 2))
    col = col + (1 - col) * (sp[..., None] * 0.12)
    a = np.clip((1.06 - r) / 0.035, 0, 1) * 255
    rgba = np.dstack([np.clip(col, 0, 1) * 255, a]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA").resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------- 图纸卡
CHART_PAGE = "1/1"          # 页码，批量导出时可改


def render_chart(idx, pal, name, cell=30, max_w=6400, mark=True):
    NR, NC = idx.shape
    cell = max(20, min(26, 5200 // NC))
    M_L, M_R = 96, 96
    M_T = 150
    per_row = 9
    leg_rows = (len(pal) + per_row - 1) // per_row
    legend_h = 60 + leg_rows * 96
    W = M_L + NC * cell + M_R
    H = M_T + NR * cell + 56 + legend_h + 90
    canvas = paper(W, H, base=(238, 237, 234))

    dr = ImageDraw.Draw(canvas)
    total = int((idx >= 0).sum())
    _mm = CFG["bead"]["diameter_mm"]
    dr.text((M_L - 30, 34), f"{name}", font=fnt(30, True), fill=(70, 68, 72))
    # 摘要块：格数 / 色数 / 豆数 / 豆径 / 色卡 / 成品尺寸（出品必备信息）
    _pname = (CFG.get("palette") or {}).get("name", "mard").upper()
    _ncol = len(pal)
    # 色卡总色数（MARD291），不是本图用了几色
    _ptot = ""
    try:
        import json as _j, os as _o
        _f = _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), "..", "palettes",
                          f'{_pname.lower()}.json')
        _d = _j.load(open(_f, encoding="utf-8"))
        _ptot = str(len(_d.get("colors") or _d))
    except Exception:
        _ptot = ""
    _sum = (f"{NC}×{NR} 格   ·   {_ncol} 色   ·   {total:,} 颗   ·   "
            f"豆径 {_mm}mm   ·   {_pname}{_ptot}   ·   "
            f"约 {round(NC*_mm/10,1)}×{round(NR*_mm/10,1)} cm")
    dr.text((M_L - 30, 78), _sum, font=fnt(19), fill=(150, 147, 150))

    # 右上角：制作日期 + 页码（出品必备）
    import datetime as _dt
    _date = _dt.date.today().strftime("%Y.%m.%d")
    _pg = CHART_PAGE
    dr.text((W - M_R + 30, 36), f"{_date}   {_pg}", font=fnt(17), fill=(168, 165, 168), anchor="ra")

    X0, Y0 = M_L, M_T
    RGB = [(np.array(hex2rgb(p[1])) * 255).astype(int) for p in pal]
    dr.rectangle([X0, Y0, X0 + NC * cell, Y0 + NR * cell], fill=(250, 250, 251))
    for y in range(NR):
        for x in range(NC):
            k = idx[y, x]
            if k < 0:
                continue
            r, g, b = RGB[k]
            dr.rectangle([X0 + x * cell, Y0 + y * cell, X0 + (x + 1) * cell, Y0 + (y + 1) * cell],
                         fill=(int(r), int(g), int(b)))

    # 网格
    for c in range(NC + 1):
        w = 2 if c % 10 == 0 else 1
        col = (168, 170, 176) if c % 10 == 0 else (216, 217, 221)
        dr.line([X0 + c * cell, Y0, X0 + c * cell, Y0 + NR * cell], fill=col, width=w)
    for r in range(NR + 1):
        w = 2 if r % 10 == 0 else 1
        col = (168, 170, 176) if r % 10 == 0 else (216, 217, 221)
        dr.line([X0, Y0 + r * cell, X0 + NC * cell, Y0 + r * cell], fill=col, width=w)

    # 色号
    # 色号一定要画——没有色号这图就废了
    # 48 色号字体自适应：色号越长字号越小，保证不出格
    _maxlen = max(len(p[0]) for p in pal) if pal else 2
    _fsz = int(cell * 0.30 * min(1.0, 3.4 / max(_maxlen, 2)))
    fs = fnt(max(5, _fsz), True)
    for y in range(NR):
        for x in range(NC):
            k = idx[y, x]
            if k < 0:
                continue
            r, g, b = RGB[k]
            lum = .299 * r + .587 * g + .114 * b
            dr.text((X0 + x * cell + cell / 2, Y0 + y * cell + cell / 2), pal[k][0],
                    font=fs, fill=(255, 255, 255) if lum < 140 else (40, 40, 46), anchor="mm")

    # 四边坐标
    fn = fnt(max(8, int(cell * 0.34)))
    step = 1 if NC <= 46 else (2 if NC <= 76 else 5)
    for c in range(NC):
        if (c + 1) % step and c:
            continue
        dr.text((X0 + c * cell + cell / 2, Y0 - 10), str(c + 1), font=fn, fill=(120, 122, 128), anchor="ms")
        dr.text((X0 + c * cell + cell / 2, Y0 + NR * cell + 10), str(c + 1), font=fn,
                fill=(120, 122, 128), anchor="ma")
    for r in range(NR):
        if (r + 1) % step and r:
            continue
        dr.text((X0 - 12, Y0 + r * cell + cell / 2), str(r + 1), font=fn, fill=(120, 122, 128), anchor="rm")
        dr.text((X0 + NC * cell + 12, Y0 + r * cell + cell / 2), str(r + 1), font=fn,
                fill=(120, 122, 128), anchor="lm")

    # 色卡（pintoo 版式：色块 + 下方色号 + 下方数量）
    ly = Y0 + NR * cell + 76
    cw = (W - M_L - M_R) / per_row
    # 46 色卡按用量从多到少排，带百分比
    _order = sorted(range(len(pal)), key=lambda i: -pal[i][3])
    _tot = max(sum(p[3] for p in pal), 1)
    for _pos, i in enumerate(_order):
        p = pal[i]
        cx = M_L + (_pos % per_row) * cw
        cy = ly + (_pos // per_row) * 96
        r, g, b = RGB[i]
        dr.rounded_rectangle([cx, cy, cx + 62, cy + 44], 6, fill=(int(r), int(g), int(b)),
                             outline=(196, 195, 192), width=1)
        # 色号 × 颗数（客户按这个买豆）
        dr.text((cx + 31, cy + 62), f"{p[0]} × {p[3]}颗",
                font=fnt(15, True), fill=(58, 56, 60), anchor="ma")
        dr.text((cx + 31, cy + 80), f"{p[3]/_tot*100:.0f}%",
                font=fnt(11), fill=(168, 165, 168), anchor="ma")

    if mark:
        watermark(canvas, WM, (X0, Y0, X0 + NC * cell, Y0 + NR * cell),
                  size=max(56, int(cell * 2.6)), alpha=104, spacing=1.45)
        brand_footer(canvas, y=H - 40, scale=0.85)
    return canvas


def render_compare(orig, bead, name, size=(1400, 920), mark=True):
    """左原图 / 右成品，同高并排"""
    W, H = size
    canvas = paper(W, H)
    dr = ImageDraw.Draw(canvas)
    dr.text((60, 40), name, font=fnt(34, True), fill=(48, 46, 50))
    dr.text((60 + fnt(34, True).getlength(name) + 16, 50), "原图 → 拼豆", font=fnt(20), fill=(150, 147, 150))

    top, ph = 116, 700
    pw = 590
    for i, img in enumerate([orig, bead]):
        x = 60 + i * (pw + 40)
        if img.mode == "RGBA":
            panel = paper(pw, ph)
            s_ = min((pw - 30) / img.width, (ph - 30) / img.height)
            t = img.resize((int(img.width * s_), int(img.height * s_)), Image.LANCZOS)
            panel.paste(t, ((pw - t.width) // 2, (ph - t.height) // 2), t)
            canvas.paste(panel, (x, top))
            dr.rectangle([x, top, x + pw, top + ph], outline=(224, 222, 218), width=1)
        else:
            s_ = min((pw - 20) / img.width, (ph - 20) / img.height)
            t = img.resize((int(img.width * s_), int(img.height * s_)), Image.LANCZOS)
            canvas.paste(t, (x + (pw - t.width) // 2, top + (ph - t.height) // 2),
                         t if t.mode == "RGBA" else None)
        dr.text((x + 4, top + ph + 12), "原图" if i == 0 else "拼豆成品",
                font=fnt(18), fill=(150, 147, 150))
    if mark:
        watermark(canvas, WM, (60 + pw + 40, top, 60 + pw + 40 + pw, top + ph),
                  size=54, alpha=150, spacing=1.15)
        brand_footer(canvas, y=H - 34, scale=0.8)
    return canvas
