# -*- coding: utf-8 -*-
"""make_excel2.py —— 台账 + 可直接复制的发布文案"""
import os, json
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter
from PIL import Image

OUT = r"C:\Users\Administrator\Downloads\拼豆成品"
rows = json.load(open(dp(OUT, "台账数据_高保真.json"), encoding="utf-8"))
_prem = {}
_pp = dp(OUT, "台账数据_精品版.json")
if os.path.exists(_pp):
    _prem = {r["no"]: r for r in json.load(open(_pp, encoding="utf-8"))}
for r in rows:
    q = _prem.get(r["no"])
    r["p"] = q

from config import CFG as _CFG, dp
BRAND = _CFG["brand"].get("watermark") or ("@" + _CFG["brand"]["name"])
BEAD_MM = _CFG["bead"]["diameter_mm"]
BASE_TAGS = ["#拼豆创意美学", "#拼豆", "#像素图", "#小红书拼豆大赛", "#我染上了拼豆", "#设计", "#手工日常"]


def theme_tags(name):
    t = []
    if any(k in name for k in ("路飞", "尼卡")):
        t += ["#海贼王", "#路飞", "#蒙奇D路飞"]
    if "索隆" in name:
        t += ["#海贼王", "#索隆"]
    if "山治" in name:
        t += ["#海贼王", "#山治"]
    if "乔巴" in name:
        t += ["#海贼王", "#乔巴"]
    if "艾斯" in name:
        t += ["#海贼王", "#波特卡斯D艾斯"]
    if "Kitty" in name:
        t += ["#hellokitty", "#凯蒂猫"]
    if "猫" in name:
        t += ["#猫", "#猫咪日常"]
    if any(k in name for k in ("三小只",)):
        t += ["#海贼王", "#草帽一伙"]
    if not t:
        t += ["#插画", "#治愈系"]
    return t


def _price(it):
    """建议售价区间（元），按豆数/色数/还原度估"""
    q = it.get("p") or it
    beads, colors = q.get("beads", it["beads"]), q.get("colors", it["colors"])
    fid = it.get("fidelity", 0.95)
    base = 4.0
    if beads > 20000: base = 12.0
    elif beads > 12000: base = 9.0
    elif beads > 8000: base = 7.0
    elif beads > 4000: base = 5.0
    if colors >= 40: base += 3.0
    elif colors >= 25: base += 1.5
    if fid >= 0.97: base += 2.0
    return f"¥{max(3, base*0.8):.0f}-{base*1.5:.0f}"


def copy_text(it):
    """照香香Puyo 的格式：尺寸 / 颜色 / 豆子 三行规格放在最前面。
    有精品低色号版就用精品版的规格（那是要卖的那个）。"""
    q = it.get("p")
    if q:
        cols, rows_, colors, beads = q["cols"], q["rows"], q["colors"], q["beads"]
    else:
        cols, rows_, colors, beads = it["cols"], it["rows"], it["colors"], it["beads"]
    title = f'拼豆图纸 | {it["name"]}'
    body = (f'拼豆图纸 | {it["name"]}\n'
            f'尺寸 | {cols}*{rows_}\n'
            f'颜色 | {colors}色\n'
            f'豆子 | {beads}粒\n'
            f'\n'
            f'拼完可以发社交媒体也可以评论返图，作品艾特我就可以啦{BRAND}\n'
            f'原创图纸 商用需要授权\n'
            f'图纸禁止二传')
    tags = " ".join(BASE_TAGS + theme_tags(it["name"]))
    return title, body, tags


wb = Workbook()
ws = wb.active
ws.title = "作品清单"

head = ["勾选", "原图", "作品名", "高保真规格", "高保真豆数", "色数", "还原度",
        "精品版", "推荐版本", "标题（复制用）", "正文（复制用）", "标签（复制用）",
        "状态", "发布日期", "备注", "评级", "建议售价"]
widths = [6, 16, 16, 20, 11, 6, 8, 34, 11, 26, 46, 40, 10, 12, 16, 7, 12]
for i, (h, w) in enumerate(zip(head, widths), 1):
    c = ws.cell(1, i, h)
    c.font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
    c.fill = PatternFill("solid", fgColor="5B5A56")
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.column_dimensions[get_column_letter(i)].width = w
ws.row_dimensions[1].height = 30

thin = Side(style="thin", color="D8D6D2")
TMP = dp(OUT, "缩略图缓存")
os.makedirs(TMP, exist_ok=True)

for r, it in enumerate(rows, 2):
    title, body, tags = copy_text(it)
    q = it.get("p")
    prem_txt = (f'{q["cols"]}×{q["rows"]} / 约{round(q["cols"]*BEAD_MM/10,1)}cm / '
                f'{q["colors"]}色 / {q["beads"]}颗 / {q["fidelity"]*100:.1f}%') if q else "—"
    # 有精品版就推荐精品版（客户拼得动是第一位的），没有才用高保真
    use = "精品版" if q else "高保真版"
    cm = round(it["cols"] * BEAD_MM / 10, 1)
    vals = ["☐", "", it["name"], f'{it["cols"]}×{it["rows"]} / 约{cm}cm',
            it["beads"], it["colors"], f'{it.get("fidelity", 0)*100:.1f}%',
            prem_txt, use, title, body, tags, "未发布", "", "",
            it.get("grade", ""), _price(it)]
    for i, v in enumerate(vals, 1):
        c = ws.cell(r, i, v)
        c.font = Font(name="微软雅黑", size=9)
        c.alignment = Alignment(horizontal="center" if i not in (10, 11, 12) else "left",
                                vertical="center", wrap_text=(i in (8, 9, 10, 11, 12)))
        c.border = Border(bottom=thin)
    ws.row_dimensions[r].height = 116

    src = it["thumb"]
    if os.path.exists(src):
        im = Image.open(src).convert("RGB")
        im.thumbnail((150, 200))
        tp = os.path.join(TMP, f'{it["no"]:02d}.png')
        im.save(tp)
        xi = XLImage(tp)
        xi.width, xi.height = im.width * 0.60, im.height * 0.60
        ws.add_image(xi, f"B{r}")

last = len(rows) + 1
dv = DataValidation(type="list", formula1='"☑,☐"', allow_blank=True)
ws.add_data_validation(dv); dv.add(f"A2:A{last}")
dv2 = DataValidation(type="list", formula1='"未发布,已发布,草稿,已归档"', allow_blank=True)
ws.add_data_validation(dv2); dv2.add(f"M2:M{last}")

ws.conditional_formatting.add(f"A2:O{last}",
    FormulaRule(formula=['$A2="☑"'], fill=PatternFill("solid", fgColor="E3F2E5")))
ws.conditional_formatting.add(f"A2:O{last}",
    FormulaRule(formula=['$M2="已发布"'], fill=PatternFill("solid", fgColor="E3F2E5")))
ws.conditional_formatting.add(f"I2:I{last}",
    FormulaRule(formula=['$I2="精品版"'], fill=PatternFill("solid", fgColor="DDEBF7")))
ws.conditional_formatting.add(f"G2:G{last}",
    FormulaRule(formula=['VALUE(SUBSTITUTE($G2,"%",""))<95'],
                fill=PatternFill("solid", fgColor="FDE2E2")))

ws.freeze_panes = "C2"
ws.auto_filter.ref = f"A1:O{last}"

ws2 = wb.create_sheet("统计")
ws2.column_dimensions["A"].width = 22
ws2.column_dimensions["B"].width = 14
ws2["A1"], ws2["B1"] = "项目", "数量"
for c in ("A1", "B1"):
    ws2[c].font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
    ws2[c].fill = PatternFill("solid", fgColor="5B5A56")
    ws2[c].alignment = Alignment(horizontal="center")
items = [("总作品数", f"=COUNTA(作品清单!C2:C{last})"),
         ("已勾选（发过）", f'=COUNTIF(作品清单!A2:A{last},"☑")'),
         ("未勾选（没发）", f'=COUNTIF(作品清单!A2:A{last},"☐")'),
         ("状态=已发布", f'=COUNTIF(作品清单!M2:M{last},"已发布")'),
         ("总豆数", f"=SUM(作品清单!E2:E{last})"),
         ("还原度<95%", f'=COUNTIF(作品清单!G2:G{last},"<95%")'),
         ("有精品低色号版", f'=COUNTIF(作品清单!H2:H{last},"*色*")'),
         ("推荐用精品版", f'=COUNTIF(作品清单!I2:I{last},"精品版")'),
         ("推荐用高保真", f'=COUNTIF(作品清单!I2:I{last},"高保真版")')]
for i, (k, v) in enumerate(items, 2):
    ws2.cell(i, 1, k).font = Font(name="微软雅黑", size=10)
    ws2.cell(i, 2, v).font = Font(name="微软雅黑", size=10)
    ws2.cell(i, 1).alignment = Alignment(horizontal="left")
    ws2.cell(i, 2).alignment = Alignment(horizontal="center")

# 列宽自适应（按内容长度，中文按 2 个字宽）
try:
    for col in ws.columns:
        letter = col[0].column_letter
        if letter in ("H", "I", "J"):      # 长文本列用固定宽
            continue
        w = 8
        for c in col[:60]:
            v = str(c.value or "")
            n = sum(2 if ord(ch) > 127 else 1 for ch in v)
            w = max(w, min(34, n + 2))
        ws.column_dimensions[letter].width = w
except Exception:
    pass

# CSV 导出（方便导入别的工具）
if _CFG.get("excel", {}).get("csv", True):
    import csv
    cp = os.path.join(OUT, "作品清单.csv")
    with open(cp, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        for row in ws.iter_rows(values_only=True):
            wr.writerow(["" if v is None else v for v in row])
    print("CSV ->", cp)

path = os.path.join(OUT, "作品清单.xlsx")
try:
    wb.save(path)
    print("EXCEL ->", path, len(rows), "行")
except PermissionError:
    alt = os.path.join(OUT, "作品清单_新版.xlsx")
    wb.save(alt)
    print("!! 原文件被占用（Excel 开着），已存为：", alt)
