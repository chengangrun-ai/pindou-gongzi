# -*- coding: utf-8 -*-
"""rebuild.py —— 重排编号 / 重建台账

用途一：重跑前清空编号空间（防止新旧编号撞车把老作品覆盖掉）
用途二：目录乱了之后，按分类重新连续编号

用法：
    python scripts/rebuild.py                 # 预演，只看会怎么变
    python scripts/rebuild.py --yes           # 真的重排
    python scripts/rebuild.py --yes --only 风景   # 只重排一个分类
"""
import argparse
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from config import CFG, dp

ORDER = ["动漫人物", "风景", "墨纹"]


def _scan(out, only=None):
    items = []
    base = os.path.join(out, "分类")
    if not os.path.isdir(base):
        return items
    cats = [only] if only else [c for c in ORDER if os.path.isdir(os.path.join(base, c))]
    for cat in cats:
        d0 = os.path.join(base, cat)
        for d in sorted(os.listdir(d0)):
            p = os.path.join(d0, d)
            if os.path.isdir(p) and d[:2].isdigit() and d[2] == "_":
                items.append({"cat": cat, "dir": d, "name": d[3:], "path": p,
                              "old": int(d[:2])})
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=CFG["paths"]["out"])
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--only", help="只处理某个分类")
    a = ap.parse_args()

    items = _scan(a.out, a.only)
    if not items:
        print("没找到作品目录")
        return 1

    # 按分类顺序 + 现有编号排
    items.sort(key=lambda x: (ORDER.index(x["cat"]) if x["cat"] in ORDER else 99, x["old"]))
    start = 1 if a.only else 1
    for i, it in enumerate(items, start):
        it["no"] = i
        it["new"] = f'{i:02d}_{it["name"]}'

    changed = [x for x in items if x["dir"] != x["new"]]
    print(f"共 {len(items)} 件，需要改编号 {len(changed)} 件")
    for x in changed[:8]:
        print(f"  {x['cat']}/{x['dir']}  →  {x['new']}")
    if len(changed) > 8:
        print(f"  …… 还有 {len(changed) - 8} 件")

    if not a.yes:
        print("\n这是预演。加 --yes 执行。")
        return 0

    # 两阶段改名，避免中途撞名
    for x in changed:
        p = x["path"]
        os.rename(p, p + ".__tmp__")
    for x in changed:
        os.rename(x["path"] + ".__tmp__", os.path.join(os.path.dirname(x["path"]), x["new"]))

    # 重建台账（规格留空，后面可用 ledger 补）
    rows = []
    for x in items:
        rows.append({"no": x["no"], "name": x["name"], "cat": x["cat"],
                     "cols": None, "rows": None, "beads": None,
                     "colors": None, "fidelity": None,
                     "path": os.path.join("分类", x["cat"], x["new"])})
    json.dump(rows, open(dp(a.out, "台账数据_高保真.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n✓ 重排完成，台账 {len(rows)} 条")
    print("  规格（格数/色数）已清空，跑一次 auto_run 会自动补")
    return 0


if __name__ == "__main__":
    sys.exit(main())
