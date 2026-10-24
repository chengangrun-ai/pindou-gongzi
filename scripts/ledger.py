# -*- coding: utf-8 -*-
"""ledger.py —— 生成「人看的」作品清单

一张表一个分类，每行带缩略图，正文/标签单独放，避免一列塞满字。

用法：
    python scripts/ledger.py                 # 生成到 config 里的 out 目录
    python scripts/ledger.py --thumb 96      # 缩略图边长
    python scripts/ledger.py --no-text       # 不生成文案表

产物：
    作品清单.xlsx     ← 每个分类两个 sheet：概览（带图）+ 文案
    文案清单_<分类>.csv
    文案_<分类>.txt
"""
import argparse
import csv
import json
import os
import shutil
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from PIL import Image

from config import CFG, dp

HEAD_FILL = PatternFill("solid", fgColor="C6705C")
TITLE_FONT = Font(bold=True, color="FFFFFF", size=11)
THUMB_COL_W = 14


def _load(out):
    p = dp(out, "台账数据_高保真.json")
    if not os.path.exists(p):
        print("找不到台账：", p)
        return []
    rows = json.load(open(p, encoding="utf-8"))
    return [r for r in rows if r.get("no")]


def _thumb(src, size, tmpdir, key):
    """生成方形缩略图，返回临时文件路径"""
    if not src or not os.path.exists(src):
        return None
    im = Image.open(src).convert("RGB")
    im.thumbnail((size, size), Image.LANCZOS)
    bg = Image.new("RGB", (size, size), (245, 243, 240))
    bg.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    p = os.path.join(tmpdir, f"{key}.png")
    bg.save(p, optimize=True)
    return p


def _find_img(row, out):
    """优先用原图，其次成品图"""
    base = row.get("path") or os.path.join(out, f'{row["no"]:02d}_{row["name"]}')
    if not os.path.isabs(base):
        base = os.path.join(out, base)
    for f in ("01_原图.jpg", "01_原图.png", "02_成品图.jpg", "02_成品图.png",
              "04_对比图.jpg", "04_对比图.png"):
        p = os.path.join(base, f)
        if os.path.exists(p):
            return p
    return None


def _style_header(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for c in ws[1]:
        c.font = TITLE_FONT
        c.fill = HEAD_FILL
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions


def _price(r):
    b = r.get("beads") or 0
    base = 4.0
    if b > 20000: base = 12.0
    elif b > 12000: base = 9.0
    elif b > 8000: base = 7.0
    elif b > 4000: base = 5.0
    if (r.get("colors") or 0) >= 40: base += 3.0
    elif (r.get("colors") or 0) >= 25: base += 1.5
    return f"¥{max(3, base * 0.8):.0f}-{base * 1.5:.0f}"


def copy_text(r, wm=None):
    wm = wm or CFG["brand"].get("watermark") or "@" + CFG["brand"]["name"]
    c = f'{r["colors"]}色' if r.get("colors") else "见色号图"
    b = f'{r["beads"]}粒' if r.get("beads") else "见色号图"
    return (f'拼豆图纸 | {r["name"]}\n'
            f'尺寸 | {r["cols"]}*{r["rows"]}\n'
            f'颜色 | {c}\n豆子 | {b}\n\n'
            f'拼完可以发社交媒体也可以评论返图，作品艾特我就可以啦{wm}\n'
            f'原创图纸 商用需要授权\n图纸禁止二次传')


TAGS = {
    "动漫人物": "#拼豆 #像素图 #动漫周边 #手工日常 #治愈系",
    "风景": "#拼豆 #像素图 #风景 #艺术摄影 #手工日常",
    "墨纹": "#拼豆 #像素图 #纹身手稿 #黑白线稿 #手工日常",
}


def _safe_path(path):
    """文件被 Excel 占用时，换个名字写，别中断整个流程"""
    try:
        with open(path, "a", encoding="utf-8"):
            pass
        return path
    except PermissionError:
        stem, ext = os.path.splitext(path)
        alt = f"{stem}_新{ext}"
        print(f"  ! {os.path.basename(path)} 被占用，改存 {os.path.basename(alt)}")
        return alt


def build(out, thumb=88, with_text=True, order=None):
    rows = _load(out)
    if not rows:
        return 1
    cats = order or CFG.get("categories", {}).get("order") or ["动漫人物", "风景", "墨纹"]
    cats = [c for c in cats if any(r.get("cat") == c for r in rows)]
    for c in {r.get("cat") for r in rows}:
        if c and c not in cats:
            cats.append(c)

    tmpdir = tempfile.mkdtemp(prefix="ledger_")
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    H_MAIN = ["图", "编号", "作品名", "规格", "色数", "豆数", "评级", "售价", "标题", "状态"]
    W_MAIN = [THUMB_COL_W, 6, 16, 22, 7, 9, 7, 11, 30, 10]
    H_TEXT = ["图", "编号", "作品名", "正文（复制用）", "标签（复制用）"]
    W_TEXT = [THUMB_COL_W, 6, 16, 56, 34]

    for cat in cats:
        items = sorted([r for r in rows if r.get("cat") == cat], key=lambda x: x["no"])
        if not items:
            continue

        # 概览
        ws = wb.create_sheet(cat)
        ws.append(H_MAIN)
        _style_header(ws, W_MAIN)
        for r in items:
            ws.append(["", r["no"], r["name"],
                       f'{r["cols"]}×{r["rows"]} / 约{round(r["cols"] * 0.5, 1)}cm',
                       r.get("colors") or "—", r.get("beads") or "—",
                       r.get("grade") or "—", _price(r),
                       f'拼豆图纸 | {r["name"]}', "未发布"])
            rr = ws.max_row
            ws.row_dimensions[rr].height = thumb * 0.78
            ws.cell(rr, 3).alignment = Alignment(vertical="center")
            ws.cell(rr, 2).alignment = Alignment(horizontal="center", vertical="center")
            src = _find_img(r, out)
            tp = _thumb(src, thumb, tmpdir, f'{cat}_{r["no"]}')
            if tp:
                img = XLImage(tp)
                img.width = img.height = thumb
                ws.add_image(img, f"A{rr}")

        # 文案
        if with_text:
            ws2 = wb.create_sheet(f"{cat}·文案")
            ws2.append(H_TEXT)
            _style_header(ws2, W_TEXT)
            for r in items:
                ws2.append(["", r["no"], r["name"], copy_text(r), TAGS.get(cat, "")])
                rr = ws2.max_row
                ws2.row_dimensions[rr].height = 76
                ws2.cell(rr, 4).alignment = Alignment(wrap_text=True, vertical="top")
                ws2.cell(rr, 5).alignment = Alignment(wrap_text=True, vertical="top")
                src = _find_img(r, out)
                tp = _thumb(src, 64, tmpdir, f't_{cat}_{r["no"]}')
                if tp:
                    img = XLImage(tp)
                    img.width = img.height = 64
                    ws2.add_image(img, f"A{rr}")

        # 分类 CSV / TXT
        with open(_safe_path(os.path.join(out, f"文案_{cat}.txt")), "w", encoding="utf-8") as f:
            for r in items:
                f.write(f'【{r["no"]:02d} {r["name"]}】\n{copy_text(r)}\n{TAGS.get(cat, "")}\n{"-" * 40}\n')

    xlsx = os.path.join(out, "作品清单.xlsx")
    try:
        os.remove(xlsx)
    except Exception:
        xlsx = _safe_path(xlsx)
    wb.save(xlsx)
    shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"已生成 {xlsx}（{len(cats)} 个分类，每类 2 个 sheet）")
    for c in cats:
        print(f"  {c}: {len([r for r in rows if r.get('cat') == c])} 件")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=CFG["paths"]["out"])
    ap.add_argument("--thumb", type=int, default=88)
    ap.add_argument("--no-text", action="store_true")
    a = ap.parse_args()
    return build(a.out, thumb=a.thumb, with_text=not a.no_text)


if __name__ == "__main__":
    sys.exit(main())
