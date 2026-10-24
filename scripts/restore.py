# -*- coding: utf-8 -*-
"""restore.py —— 台账丢了从备份恢复

每次写台账前都会自动备份到 `内部数据/台账备份/`，文件名带时间和条数：
    20261024_124111_89条_台账数据_高保真.json

用法：
    python scripts/restore.py            # 列出所有备份，看哪份条数对
    python scripts/restore.py --latest   # 恢复最新一份
    python scripts/restore.py --pick 89  # 恢复「条数最接近 89」的那份
    python scripts/restore.py --file 20261024_124111_89条_台账数据_高保真.json
"""
import argparse
import os
import re
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from config import CFG, dp

TARGET = "台账数据_高保真.json"


def _backups(out):
    d = dp(out, "台账备份")
    if not os.path.isdir(d):
        return []
    rows = []
    for f in os.listdir(d):
        m = re.match(r"(\d{8}_\d{6})_(\d+)条_", f)
        if m and f.endswith(TARGET):
            rows.append((m.group(1), int(m.group(2)), os.path.join(d, f)))
    rows.sort()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=CFG["paths"]["out"])
    ap.add_argument("--latest", action="store_true")
    ap.add_argument("--pick", type=int, help="按条数挑最接近的")
    ap.add_argument("--file", help="指定备份文件名")
    ap.add_argument("--yes", action="store_true", help="真的覆盖（默认只预览）")
    a = ap.parse_args()

    rows = _backups(a.out)
    if not rows:
        print("没有备份。")
        return 1

    cur = dp(a.out, TARGET)
    cur_n = 0
    if os.path.exists(cur):
        try:
            import json
            cur_n = len(json.load(open(cur, encoding="utf-8")))
        except Exception:
            pass

    print(f"现有台账：{cur_n} 条")
    print(f"备份 {len(rows)} 份：")
    for t, n, p in rows[-10:]:
        print(f"  {t}  {n:3d} 条  {os.path.basename(p)}")

    pick = None
    if a.file:
        pick = next((r for r in rows if os.path.basename(r[2]) == a.file), None)
    elif a.latest:
        pick = rows[-1]
    elif a.pick is not None:
        pick = min(rows, key=lambda r: abs(r[1] - a.pick))

    if not pick:
        print("\n加 --latest / --pick N / --file 名字 来选一份恢复。")
        return 0

    t, n, p = pick
    print(f"\n要恢复：{t}  {n} 条")
    if cur_n and n < cur_n:
        print(f"⚠️ 这份比现在的少 {cur_n - n} 条，确认是不是要的")
    if not a.yes:
        print("这是预览。加 --yes 覆盖。")
        return 0

    # 覆盖前先把当前存一份，别把现在的也弄丢
    if os.path.exists(cur):
        shutil.copy2(cur, cur + ".before-restore")
        print(f"当前台账已另存：{os.path.basename(cur)}.before-restore")
    shutil.copy2(p, cur)
    print(f"✓ 已恢复 {n} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
