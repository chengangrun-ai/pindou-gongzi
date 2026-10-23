# -*- coding: utf-8 -*-
"""prune_published.py —— 删除已发布作品的高保真版和精品版，只留无标版

判定「已发布」：作品清单.xlsx 的「状态」列含「已发布」或「1」，或「勾选」为 ☑/✓/1

删除范围（对每件已发布的）：
    NN_作品名/                  ← 删
    精品版/NN_作品名/            ← 删
    精品版/无LOGO版/NN_作品名/   ← 删
    无LOGO版/NN_作品名/          ← 保留（客户交付件）

用法：
    python prune_published.py            # 预演，只列出会删什么
    python prune_published.py --yes      # 真的删
"""
import os, sys, shutil, argparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import openpyxl
from config import CFG

OUT = CFG["paths"]["out"]
XLSX = os.path.join(OUT, "作品清单.xlsx")

PUBLISHED = ("已发布", "已发", "发布", "1", "是", "y", "yes", "✓", "✔", "☑", "√")


def load_published():
    if not os.path.exists(XLSX):
        print("找不到", XLSX)
        return []
    ws = openpyxl.load_workbook(XLSX, data_only=True)["作品清单"]
    head = [str(c.value or "") for c in ws[1]]
    try:
        i_name = head.index("作品名")
    except ValueError:
        i_name = 2
    i_stat = next((i for i, h in enumerate(head) if "状态" in h), None)
    i_tick = next((i for i, h in enumerate(head) if "勾选" in h), None)

    out = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        name = str(r[i_name] or "").strip()
        if not name:
            continue
        stat = str(r[i_stat] or "").strip().lower() if i_stat is not None else ""
        tick = str(r[i_tick] or "").strip() if i_tick is not None else ""
        if any(p.lower() in stat for p in PUBLISHED) or tick in ("☑", "✓", "✔", "1", "√"):
            out.append(name)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="真的删除（默认只预演）")
    a = ap.parse_args()

    names = load_published()
    if not names:
        print("清单里没有标记为「已发布」的作品。")
        print("请在「状态」列填「已发布」，或在「勾选」列打勾，保存后重跑。")
        return 1

    print(f"已发布 {len(names)} 件，将删除以下目录：\n")
    plan = []
    for n in names:
        for sub in ("", os.path.join("精品版", ""), os.path.join("精品版", "无LOGO版")):
            d = os.path.join(OUT, sub, n) if sub else os.path.join(OUT, n)
            if os.path.isdir(d):
                plan.append(d)
    for d in plan:
        print("  -", os.path.relpath(d, OUT))

    keep = [os.path.join(OUT, "无LOGO版", n) for n in names
            if os.path.isdir(os.path.join(OUT, "无LOGO版", n))]
    print(f"\n保留 {len(keep)} 个无标版：")
    for d in keep:
        print("  ✓", os.path.relpath(d, OUT))

    if not a.yes:
        print("\n这是预演。确认无误后加 --yes 执行。")
        return 0

    n = 0
    for d in plan:
        shutil.rmtree(d, ignore_errors=True)
        n += 1
    print(f"\n已删除 {n} 个目录。")

    # 台账里也去掉这些行
    ws = openpyxl.load_workbook(XLSX)["作品清单"]
    for row in range(ws.max_row, 1, -1):
        if str(ws.cell(row, 3).value or "").strip() in names:
            ws.delete_rows(row)
    ws.parent.save(XLSX)
    print(f"台账已移除这 {len(names)} 行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
