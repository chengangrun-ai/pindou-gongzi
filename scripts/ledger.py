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
    """在社媒版/<分类>/<编号>_<名>/ 里找原图，找不到再退回交付版成品图"""
    no, name = row["no"], row["name"]
    cat = row.get("cat") or ""
    cands = []
    if cat:
        cands.append(os.path.join(out, "社媒版", cat, f"{no:02d}_{name}"))
    cands.append(os.path.join(out, "社媒版", f"{no:02d}_{name}"))
    for d in cands:
        for f in ("01_原图.png", "02_成品图.png"):
            p = os.path.join(d, f)
            if os.path.exists(p):
                return p
    # 兜底：任何分类下的这个作品
    import glob as _g
    for p in _g.glob(os.path.join(out, "社媒版", "*", f"{no:02d}_{name}", "*.png")):
        return p
    for p in _g.glob(os.path.join(out, "交付版", "*", f"{no:02d}_{name}", "*.jpg")):
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


# ---------------- 小红书标签 ----------------
# 10 个标签的搭配逻辑：
#   4 个大词（吃品类流量）+ 3~4 个内容词（吃精准搜索）+ 2 个场景词（吃人群）
# 全是大词没精准流量，全是小词没人搜。

# ---------------- 小红书标签（10 个，全部围绕拼豆） ----------------
# 配比：6 个拼豆核心词 + 2 个内容词 + 2 个拼豆场景词
# 不放 #天空 #云朵 这种和拼豆无关的泛词——搜那些词的人不会买图纸。

_T_BIG = ["#拼豆", "#拼豆图纸", "#拼豆diy", "#拼豆教程", "#拼豆成品", "#小红书拼豆图纸库"]

_T_KW = [
    (("马", "骑"), ["#马拼豆", "#动物拼豆"]),
    (("羊", "牛", "鸟", "蝶", "鱼", "猫", "狗"), ["#动物拼豆", "#小动物拼豆"]),
    (("冲浪", "浪", "海", "舟", "船", "网"), ["#海景拼豆", "#冲浪拼豆"]),
    (("冰",), ["#自然拼豆", "#极地拼豆"]),
    (("麦田", "稻", "田", "草坡", "草地"), ["#田野拼豆", "#草地拼豆"]),
    (("雪山", "山", "岩", "丘", "瀑"), ["#山野拼豆", "#风景拼豆"]),
    (("网球", "滑板", "运动"), ["#运动拼豆", "#潮流拼豆"]),
    (("烛", "冠", "绸", "静物"), ["#静物拼豆", "#质感拼豆"]),
    (("树", "林"), ["#大树拼豆", "#自然拼豆"]),
    (("屋", "房", "墙", "邮筒", "车", "建筑", "步道"), ["#建筑拼豆", "#小屋拼豆"]),
    (("花",), ["#花海拼豆", "#花卉拼豆"]),
    (("云", "天空", "光"), ["#云朵拼豆", "#天空拼豆"]),
    (("人", "少年", "情侣", "双人", "人物", "人像", "女孩", "外婆", "饮", "女", "男"),
     ["#人像拼豆", "#人物拼豆"]),
    (("夜", "灯"), ["#夜景拼豆", "#灯光拼豆"]),
    (("倒影", "影", "水"), ["#倒影拼豆", "#光影拼豆"]),
    (("红", "橙"), ["#红色拼豆", "#暖色拼豆"]),
    (("绿",), ["#绿色拼豆", "#治愈拼豆"]),
    (("电脑", "宴", "洞"), ["#超现实拼豆", "#创意拼豆"]),
]

_T_SCENE = ["#拼豆日常", "#拼豆分享", "#拼豆手作", "#拼豆控", "#拼豆入坑", "#拼豆新手"]
_T_TAIL = ["#像素画", "#手工diy", "#手作", "#解压手工", "#宅家日常"]

_T_CAT = {"动漫人物": "#动漫拼豆", "风景": "#风景拼豆", "墨纹": "#纹身拼豆"}


def tags_for(name, cat="", colors=0):
    """10 个小红书标签：6 拼豆核心 + 2 内容 + 2 场景，全部围绕拼豆"""
    # 仙人掌/人参 含「人」字，先剔掉再匹配，否则会被判成人像
    nm = name.replace("仙人掌", "").replace("人参", "")
    content = []
    for kws, tags in _T_KW:
        if any(k in nm for k in kws):
            for t in tags:
                if t not in content:
                    content.append(t)
    ct = _T_CAT.get(cat)
    if ct and ct not in content:
        content.append(ct)
    if not content:
        content.append("#风景拼豆")

    out = list(_T_BIG) + content[:2] + _T_SCENE[:2]
    for t in _T_SCENE + content + _T_TAIL:
        if len(out) >= 10:
            break
        if t not in out:
            out.append(t)
    return " ".join(out[:10])


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
    HDR = ["图", "编号", "作品名", "格数", "色数", "豆数", "尺寸",
           "标题", "正文（复制发笔记）", "标签", "已发社媒", "已交付", "备注"]
    WID = [13, 5, 14, 11, 6, 9, 11, 24, 46, 30, 9, 9, 16]
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
                   f'拼豆图纸 | {r["name"]}', copy_text(r),
                   tags_for(r["name"], r.get("cat", ""), r.get("colors") or 0), "☐", "☐", ""])
        rr = ws.max_row
        ws.row_dimensions[rr].height = 96
        for col in (2, 5, 11, 12):
            ws.cell(rr, col).alignment = Alignment(horizontal="center", vertical="center")
        for col in (8, 9, 10):
            ws.cell(rr, col).alignment = Alignment(wrap_text=True, vertical="top")
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
