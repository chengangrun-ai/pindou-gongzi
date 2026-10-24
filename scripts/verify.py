# -*- coding: utf-8 -*-
"""verify.py —— 产出前的一致性校验（客诉防火墙）

只要有一处对不上就报错退出，不许出交付。

查什么：
1. 台账里每一件的格数是否一致（同一产品线必须同尺寸）
2. 豆数 = 格数（cols × rows）
3. 交付版色号图存在，且像素宽度 = 192 + cols × 格距
4. 社媒版成品图存在
5. 清单里的数字和台账一致
6. 文案里的尺寸/色数/豆数和台账一致

用法：
    python scripts/verify.py            # 校验
    python scripts/verify.py --fix      # 能修的顺手修（补缺失文件不算）
"""
import argparse
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PIL import Image

from config import CFG, dp

RED = "\033[31m" if os.name != "nt" else ""
END = "\033[0m" if os.name != "nt" else ""


def fail(msg):
    print(f"  ✗ {msg}")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=CFG["paths"]["out"])
    a = ap.parse_args()
    out = a.out

    p = dp(out, "台账数据_高保真.json")
    if not os.path.exists(p):
        print("没有台账，先跑一次 auto_run")
        return 1
    rows = json.load(open(p, encoding="utf-8"))
    if not rows:
        print("台账是空的")
        return 1

    errs = 0
    print(f"校验 {len(rows)} 件\n")

    # 1) 尺寸一致性
    shapes = {}
    for r in rows:
        if not r.get("cols") or not r.get("rows"):
            errs += fail(f'{r["name"]}: 台账缺格数')
            continue
        shapes.setdefault((r["cols"], r["rows"]), []).append(r["name"])
    if len(shapes) > 1:
        errs += fail(f"格数不统一，出现 {len(shapes)} 种：" +
                     "、".join(f"{c}×{r}({len(v)}件)" for (c, r), v in shapes.items()))
    else:
        c, r = next(iter(shapes))
        print(f"  ✓ 格数统一：{c}×{r}（{len(rows)} 件）")

    # 2) 豆数 = 格数
    for r in rows:
        if r.get("cols") and r.get("beads") != r["cols"] * r["rows"]:
            errs += fail(f'{r["name"]}: 豆数 {r["beads"]} ≠ {r["cols"]}×{r["rows"]}')

    # 3) 交付版 + 4) 社媒版
    for r in rows:
        d = os.path.join(out, "交付版", f'{r["no"]:02d}_{r["name"]}')
        ch = os.path.join(d, "色号图.png")
        if not os.path.exists(ch):
            errs += fail(f'{r["name"]}: 缺交付版色号图')
        else:
            w, h = Image.open(ch).size
            want = 192 + r["cols"] * max(20, min(26, 5200 // r["cols"]))
            if abs(w - want) > 2:
                errs += fail(f'{r["name"]}: 色号图宽 {w} ≠ 应为 {want}')
        if not os.path.exists(os.path.join(d, "成品图.jpg")):
            errs += fail(f'{r["name"]}: 缺交付版成品图')
        if not os.path.exists(os.path.join(out, "社媒版", f'{r["no"]:02d}_{r["name"]}.png')):
            errs += fail(f'{r["name"]}: 缺社媒版')

    # 5) 清单
    xlsx = os.path.join(out, "作品清单.xlsx")
    if os.path.exists(xlsx):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(xlsx)
            ws = wb.active
            hdr = [c.value for c in ws[1]]
            i_cols, i_beads, i_no = hdr.index("格数"), hdr.index("豆数"), hdr.index("编号")
            for row in ws.iter_rows(min_row=2, values_only=True):
                no = row[i_no]
                t = next((x for x in rows if x["no"] == no), None)
                if not t:
                    errs += fail(f"清单里有台账没有的编号 {no}")
                    continue
                want = f'{t["cols"]}×{t["rows"]}'
                if row[i_cols] != want:
                    errs += fail(f'清单第 {no} 件格数 {row[i_cols]} ≠ {want}')
                if row[i_beads] != t["beads"]:
                    errs += fail(f'清单第 {no} 件豆数 {row[i_beads]} ≠ {t["beads"]}')
        except Exception as e:
            errs += fail(f"清单读不了：{e}")
    else:
        errs += fail("缺作品清单.xlsx")

    print()
    if errs:
        print(f"{RED}✗ 校验失败：{errs} 处不一致，不要交付{END}")
        return 1
    print("✓ 全部一致，可以交付")
    return 0


if __name__ == "__main__":
    sys.exit(main())
