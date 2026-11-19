# -*- coding: utf-8 -*-
"""sheet_hq.py —— 用「色号矩阵」直接排版出图（不是放大已渲染的 PNG）

为什么要这层：
    平台返回的 pngBase64 是画在小尺寸画布上、再把点阵字形放大，
    字边缘被插值糊掉。真正的做法是从 grid + palette（原始数据）重新排版，
    用系统 TrueType 字体按目标尺寸原生绘制：

        PNG  → 每格 64px、字号 23px 原生抗锯齿（照片查看器 100% 就清楚）
        PDF  → 每个色号是一段矢量文字（放大 800% 仍然锐利、打印不糊）

用法（由 pack-dolita.py 调用）：
    render_png(idx, pal, counts, cols, rows, cell, out_png, qr_png=..., total=...)
    render_pdf(idx, pal, counts, cols, rows, cell, out_pdf, qr_png=..., total=...)
"""
import math
import os
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = r"C:\Windows\Fonts"
F_BOLD = os.path.join(FONT_DIR, "arialbd.ttf")
F_CN = os.path.join(FONT_DIR, "msyh.ttc")
F_CNB = os.path.join(FONT_DIR, "msyhbd.ttc")

INK = (40, 40, 44)
MUTED = (150, 148, 150)
LINE = (214, 212, 208)
BRAND_TXT = "豆莉塔"
BRAND_SUB = "拼豆底稿生成器 · MARD 色板"


def _hex(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lum(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


def _lighten(rgb, k=0.14):
    """原作者图纸每格有一道很浅的边，格子边界才立得住"""
    return tuple(int(v + (255 - v) * k) for v in rgb)


def layout(cols, rows, cell, ncolors, margin=96, top=326, per_row=8):
    grid_w = cols * cell
    grid_h = rows * cell
    W = margin * 2 + grid_w
    list_top = top + grid_h + 120
    block_h = 112
    rows_n = math.ceil(ncolors / per_row) if ncolors else 0
    list_h = 66 + rows_n * block_h + 28
    brand_h = 160
    H = list_top + list_h + brand_h
    return dict(W=W, H=H, margin=margin, top=top, grid_w=grid_w, grid_h=grid_h,
                list_top=list_top, per_row=per_row, rows_n=rows_n,
                block_h=block_h, list_h=list_h, brand_h=brand_h)


def _code_px(cell):
    # 原作者图纸里色号约占格宽的 42%，照它来
    return max(12, int(cell * 0.42))


# ------------------------------------------------------------------ PNG
def render_png(idx, pal, counts, cols, rows, cell, out_png,
               qr_png=None, total=None, per_row=8):
    L = layout(cols, rows, cell, len(pal), per_row=per_row)
    W, H, m, top = L["W"], L["H"], L["margin"], L["top"]
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)

    f_title = ImageFont.truetype(F_BOLD, 44)
    f_sub = ImageFont.truetype(F_CN, 22)
    f_axis = ImageFont.truetype(F_BOLD, 20)
    f_px = _code_px(cell)
    f_code = ImageFont.truetype(F_BOLD, f_px)
    f_listt = ImageFont.truetype(F_CNB, 30)
    f_cn = ImageFont.truetype(F_CN, 16)
    f_small = ImageFont.truetype(F_CN, 15)

    d.text((m, 52), "MARD", font=f_title, fill=INK)
    tw = d.textlength("MARD", font=f_title)
    d.text((m + tw + 12, 72), "色号", font=f_sub, fill=MUTED)

    x0, y0 = m, top
    # 网格底
    for r in range(rows):
        yy = y0 + r * cell
        for c in range(cols):
            k = idx[r][c]
            if k < 0:
                continue
            rgb = _hex(pal[k][1])
            xx = x0 + c * cell
            d.rectangle([xx, yy, xx + cell - 1, yy + cell - 1], fill=rgb,
                        outline=_lighten(rgb, 0.16))

    # 色号（原生字号，抗锯齿）
    for r in range(rows):
        yy = y0 + r * cell
        for c in range(cols):
            k = idx[r][c]
            if k < 0:
                continue
            rgb = _hex(pal[k][1])
            code = pal[k][0]
            fill = (255, 255, 255) if _lum(*rgb) < 150 else (32, 32, 36)
            d.text((x0 + c * cell + cell / 2, yy + cell / 2 + 1), code,
                   font=f_code, fill=fill, anchor="mm")

    # 10 格粗线
    for c in range(0, cols + 1, 10):
        xx = x0 + c * cell
        d.line([(xx, y0), (xx, y0 + L["grid_h"])], fill=LINE, width=2)
    for r in range(0, rows + 1, 10):
        yy = y0 + r * cell
        d.line([(x0, yy), (x0 + L["grid_w"], yy)], fill=LINE, width=2)

    # 坐标
    for c in range(0, cols, 10):
        xx = x0 + c * cell + cell / 2
        d.text((xx, y0 - 22), str(c + 1), font=f_axis, fill=MUTED, anchor="mm")
    for r in range(0, rows, 10):
        yy = y0 + r * cell + cell / 2
        d.text((x0 - 26, yy), str(r + 1), font=f_axis, fill=MUTED, anchor="mm")

    # 用料清单
    lt = L["list_top"]
    d.text((m, lt), "用料清单", font=f_listt, fill=INK)
    if total is not None:
        txt = f"共 {total:,} 颗"
        d.text((W - m, lt + 6), txt, font=f_listt, fill=INK, anchor="ra")
    cw = (W - 2 * m) // per_row
    for i, k in enumerate(sorted(range(len(pal)), key=lambda j: -counts[j])):
        r_, c_ = divmod(i, per_row)
        bx = m + c_ * cw
        by = lt + 66 + r_ * L["block_h"]
        rgb = _hex(pal[k][1])
        d.rectangle([bx, by, bx + 92, by + 62], fill=rgb, outline=(200, 198, 196))
        d.text((bx + 46, by + 84), pal[k][0], font=f_code, fill=INK, anchor="ma")
        d.text((bx + 46, by + 112), f"{counts[k]:,}", font=f_small, fill=MUTED, anchor="ma")

    # 品牌条
    by0 = H - L["brand_h"]
    d.line([(m, by0), (W - m, by0)], fill=LINE, width=2)
    d.text((m, by0 + 44), BRAND_TXT, font=ImageFont.truetype(F_CNB, 26), fill=INK)
    d.text((m, by0 + 84), BRAND_SUB, font=f_cn, fill=MUTED)
    if qr_png and os.path.exists(qr_png):
        q = Image.open(qr_png).convert("RGB")
        q = q.resize((118, 118), Image.NEAREST)
        im.paste(q, (W - m - 118, by0 + 20))
    im.save(out_png, optimize=True)
    return out_png, (W, H)


# ------------------------------------------------------------------ PDF（矢量）
def render_pdf(idx, pal, counts, cols, rows, cell, out_pdf,
               qr_png=None, total=None, per_row=8, wm_text=None, wm_alpha=0.20):
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import ImageReader

    try:
        pdfmetrics.registerFont(TTFont("AB", F_BOLD))
    except Exception:
        pass
    pdfmetrics.registerFont(TTFont("CN", F_CN))

    L = layout(cols, rows, cell, len(pal), per_row=per_row)
    W, H, m, top = L["W"], L["H"], L["margin"], L["top"]
    c = rl_canvas.Canvas(out_pdf, pagesize=(W, H))
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, W, H, stroke=0, fill=1)

    def T(x, y, s, font="AB", size=20, rgb=INK, anchor="l"):
        c.setFillColorRGB(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
        c.setFont(font, size)
        if anchor == "l":
            c.drawString(x, H - y, s)
        elif anchor == "m":
            c.drawCentredString(x, H - y, s)
        elif anchor == "r":
            c.drawRightString(x, H - y, s)

    f_px = _code_px(cell)
    T(m, 92, "MARD", "AB", 44, INK)
    T(m + 128, 92, "色号", "CN", 22, MUTED)

    x0, y0 = m, top
    # 色块（矢量矩形）
    for r in range(rows):
        yy = y0 + r * cell
        for cc in range(cols):
            k = idx[r][cc]
            if k < 0:
                continue
            rgb = _hex(pal[k][1])
            c.setFillColorRGB(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
            c.rect(x0 + cc * cell, H - (yy + cell), cell, cell, stroke=0, fill=1)

    # 色号（矢量文字）
    for r in range(rows):
        yy = y0 + r * cell
        for cc in range(cols):
            k = idx[r][cc]
            if k < 0:
                continue
            rgb = _hex(pal[k][1])
            color = (255, 255, 255) if _lum(*rgb) < 150 else (32, 32, 36)
            c.setFillColorRGB(color[0] / 255, color[1] / 255, color[2] / 255)
            c.setFont("AB", f_px)
            c.drawCentredString(x0 + cc * cell + cell / 2, H - (yy + cell / 2) - f_px * 0.36,
                                pal[k][0])

    # 网格线 / 坐标
    c.setStrokeColorRGB(LINE[0] / 255, LINE[1] / 255, LINE[2] / 255)
    c.setLineWidth(1.4)
    for cc in range(0, cols + 1, 10):
        c.line(x0 + cc * cell, H - y0, x0 + cc * cell, H - (y0 + L["grid_h"]))
    for r in range(0, rows + 1, 10):
        c.line(x0, H - (y0 + r * cell), x0 + L["grid_w"], H - (y0 + r * cell))
    for cc in range(0, cols, 10):
        T(x0 + cc * cell + cell / 2, y0 - 12, str(cc + 1), "AB", 20, MUTED, "m")
    for r in range(0, rows, 10):
        T(x0 - 30, y0 + r * cell + cell / 2 + 8, str(r + 1), "AB", 20, MUTED, "m")

    # 用料清单
    lt = L["list_top"]
    T(m, lt + 26, "用料清单", "CN", 30, INK)
    if total is not None:
        T(W - m, lt + 26, f"共 {total:,} 颗", "CN", 30, INK, "r")
    cw = (W - 2 * m) // per_row
    for i, k in enumerate(sorted(range(len(pal)), key=lambda j: -counts[j])):
        r_, c_ = divmod(i, per_row)
        bx = m + c_ * cw
        by = lt + 66 + r_ * L["block_h"]
        rgb = _hex(pal[k][1])
        c.setFillColorRGB(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
        c.rect(bx, H - (by + 62), 92, 62, stroke=0, fill=1)
        c.setStrokeColorRGB(0.78, 0.78, 0.76)
        c.setLineWidth(0.8)
        c.rect(bx, H - (by + 62), 92, 62, stroke=1, fill=0)
        T(bx + 46, by + 84, pal[k][0], "AB", f_px, INK, "m")
        T(bx + 46, by + 112, f"{counts[k]:,}", "CN", 15, MUTED, "m")

    # 品牌条
    by0 = H - L["brand_h"]
    c.setStrokeColorRGB(LINE[0] / 255, LINE[1] / 255, LINE[2] / 255)
    c.setLineWidth(1.4)
    c.line(m, H - by0, W - m, H - by0)
    T(m, by0 + 44, BRAND_TXT, "CN", 26, INK)
    T(m, by0 + 84, BRAND_SUB, "CN", 16, MUTED)
    if qr_png and os.path.exists(qr_png):
        c.drawImage(ImageReader(qr_png), W - m - 118, H - (by0 + 138), 118, 118, mask=None)

    # 水印（矢量文字，斜向铺满网格区域；放大也不糊）
    if wm_text:
        wsize = int(cell * 1.6)
        step_x = int(wsize * 3.4)
        step_y = int(wsize * 2.7)
        c.setFont("CN", wsize)
        c.setFillColorRGB(0.52, 0.51, 0.56)
        c.setFillAlpha(wm_alpha)
        for yy in range(int(y0) + wsize, int(y0 + L["grid_h"]), max(step_y, 40)):
            for xx in range(int(x0), int(x0 + L["grid_w"]), max(step_x, 40)):
                c.saveState()
                c.translate(xx, H - yy)
                c.rotate(28)
                c.drawString(0, 0, wm_text)
                c.restoreState()
        c.setFillAlpha(1)

    c.showPage()
    c.save()
    return out_pdf, (W, H)


def render_svg(idx, pal, counts, cols, rows, cell, out_svg,
               total=None, per_row=8, wm_text=None, wm_alpha=0.14):
    """矢量 SVG：浏览器直接打开，滚轮缩放到多少倍都不会糊。"""
    L = layout(cols, rows, cell, len(pal), per_row=per_row)
    W, H, m, top = L["W"], L["H"], L["margin"], L["top"]
    f_px = _code_px(cell)
    x0, y0 = m, top

    def esc(s):
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    parts = [f'<?xml version="1.0" encoding="UTF-8"?>',
             f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}" shape-rendering="crispEdges">',
             f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
             f'<text x="{m}" y="92" font-family="Arial" font-weight="bold" font-size="44" '
             f'fill="#28282c">MARD</text>',
             f'<text x="{m + 128}" y="92" font-family="Microsoft YaHei,Arial" font-size="22" '
             f'fill="#969496">色号</text>']

    # 色块
    parts.append('<g>')
    for r in range(rows):
        yy = y0 + r * cell
        for c in range(cols):
            k = idx[r][c]
            if k < 0:
                continue
            parts.append(f'<rect x="{x0 + c * cell}" y="{yy}" width="{cell}" height="{cell}" '
                         f'fill="{pal[k][1]}"/>')
    parts.append('</g>')

    # 色号（矢量文字）
    parts.append(f'<g font-family="Arial" font-weight="bold" font-size="{f_px}" '
                 f'text-anchor="middle" dominant-baseline="central">')
    for r in range(rows):
        yy = y0 + r * cell + cell / 2
        for c in range(cols):
            k = idx[r][c]
            if k < 0:
                continue
            rgb = _hex(pal[k][1])
            color = "#ffffff" if _lum(*rgb) < 150 else "#202024"
            parts.append(f'<text x="{x0 + c * cell + cell / 2:.0f}" y="{yy:.0f}" '
                         f'fill="{color}">{esc(pal[k][0])}</text>')
    parts.append('</g>')

    # 10 格线 + 坐标
    parts.append('<g stroke="#d6d4d0" stroke-width="1.6">')
    for c in range(0, cols + 1, 10):
        xx = x0 + c * cell
        parts.append(f'<line x1="{xx}" y1="{y0}" x2="{xx}" y2="{y0 + L["grid_h"]}"/>')
    for r in range(0, rows + 1, 10):
        yy = y0 + r * cell
        parts.append(f'<line x1="{x0}" y1="{yy}" x2="{x0 + L["grid_w"]}" y2="{yy}"/>')
    parts.append('</g>')
    parts.append('<g font-family="Arial" font-weight="bold" font-size="20" fill="#969496" '
                 'text-anchor="middle" dominant-baseline="central">')
    for c in range(0, cols, 10):
        parts.append(f'<text x="{x0 + c * cell + cell / 2:.0f}" y="{y0 - 20}">{c + 1}</text>')
    for r in range(0, rows, 10):
        parts.append(f'<text x="{x0 - 34}" y="{y0 + r * cell + cell / 2:.0f}">{r + 1}</text>')
    parts.append('</g>')

    # 水印（矢量斜排）
    if wm_text:
        wsize = int(cell * 1.8)
        sx, sy = int(wsize * 3.4), int(wsize * 2.7)
        parts.append(f'<g opacity="{wm_alpha}" fill="#7d7c82" font-family="Microsoft YaHei" '
                     f'font-size="{wsize}" font-weight="bold">')
        for yy in range(int(y0) + wsize, int(y0 + L["grid_h"]), max(sy, 40)):
            for xx in range(int(x0), int(x0 + L["grid_w"]), max(sx, 40)):
                parts.append(f'<text x="{xx}" y="{yy}" '
                             f'transform="rotate(-30 {xx} {yy})">{esc(wm_text)}</text>')
        parts.append('</g>')

    # 用料清单
    lt = L["list_top"]
    parts.append(f'<text x="{m}" y="{lt + 34}" font-family="Microsoft YaHei" font-weight="bold" '
                 f'font-size="30" fill="#28282c">用料清单</text>')
    if total is not None:
        parts.append(f'<text x="{W - m}" y="{lt + 34}" text-anchor="end" '
                     f'font-family="Microsoft YaHei" font-weight="bold" font-size="30" '
                     f'fill="#28282c">共 {total:,} 颗</text>')
    cw = (W - 2 * m) // per_row
    for i, k in enumerate(sorted(range(len(pal)), key=lambda j: -counts[j])):
        r_, c_ = divmod(i, per_row)
        bx = m + c_ * cw
        by = lt + 66 + r_ * L["block_h"]
        parts.append(f'<rect x="{bx}" y="{by}" width="92" height="62" fill="{pal[k][1]}" '
                     f'stroke="#c8c6c4" stroke-width="1"/>')
        parts.append(f'<text x="{bx + 46}" y="{by + 88}" text-anchor="middle" '
                     f'font-family="Arial" font-weight="bold" font-size="{f_px}" '
                     f'fill="#28282c">{esc(pal[k][0])}</text>')
        parts.append(f'<text x="{bx + 46}" y="{by + 112}" text-anchor="middle" '
                     f'font-family="Microsoft YaHei" font-size="15" fill="#969496">'
                     f'{counts[k]:,}</text>')

    # 品牌条
    by0 = H - L["brand_h"]
    parts.append(f'<line x1="{m}" y1="{by0}" x2="{W - m}" y2="{by0}" stroke="#d6d4d0" '
                 f'stroke-width="1.6"/>')
    parts.append(f'<text x="{m}" y="{by0 + 52}" font-family="Microsoft YaHei" font-weight="bold" '
                 f'font-size="26" fill="#28282c">{BRAND_TXT}</text>')
    parts.append(f'<text x="{m}" y="{by0 + 88}" font-family="Microsoft YaHei" font-size="16" '
                 f'fill="#969496">{BRAND_SUB}</text>')
    parts.append('</svg>')

    with open(out_svg, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return out_svg, (W, H)


def make_qr(url, out_png, box=420):
    import qrcode
    qr = qrcode.QRCode(border=1, box_size=10)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1D1D1F", back_color="white").convert("RGB")
    img = img.resize((box, box), Image.NEAREST)
    img.save(out_png)
    return out_png
