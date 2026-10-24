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


def build(out, thumb=80, with_text=False, order=None):
    """只产出一张清单：图 / 编号 / 作品名 / 规格 / 已发社媒 / 已交付"""
    rows = _load(out)
    if not rows:
        return 1

    import openpyxl
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from PIL import Image as _I

    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "作品清单"
    HDR = ["图", "编号", "作品名", "格数", "色数", "豆数", "尺寸", "已发社媒", "已交付", "备注"]
    WID = [14, 6, 18, 12, 7, 10, 14, 10, 10, 20]
    ws.append(HDR)
    for i, w in enumerate(WID, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="C6705C")
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 26

    tmpdir = tempfile.mkdtemp(prefix="ledger_")
    for r in sorted(rows, key=lambda x: x["no"]):
        ws.append(["", r["no"], r["name"],
                   f'{r["cols"]}×{r["rows"]}' if r.get("cols") else "—",
                   r.get("colors") or "—", r.get("beads") or "—",
                   f'约{round((r["cols"] or 0) * 0.5)}cm' if r.get("cols") else "—",
                   "☐", "☐", ""])
        rr = ws.max_row
        ws.row_dimensions[rr].height = thumb * 0.8
        for col in (2, 5, 8, 9):
            ws.cell(rr, col).alignment = Alignment(horizontal="center", vertical="center")
        src = _find_img(r, out)
        tp = _thumb(src, thumb, tmpdir, str(r["no"]))
        if tp:
            img = XLImage(tp); img.width = img.height = thumb
            ws.add_image(img, f"A{rr}")

    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    xlsx = os.path.join(out, "作品清单.xlsx")
    try:
        os.remove(xlsx)
    except Exception:
        xlsx = _safe_path(xlsx)
    wb.save(xlsx)
    shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"清单已生成：{xlsx}（{len(rows)} 件）")
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
