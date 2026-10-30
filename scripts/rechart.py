# -*- coding: utf-8 -*-
"""rechart.py —— 只重绘色号图，不动编号、不动其他文件

改了图纸版式（顶栏信息、色卡、页码）之后，需要把已有的图重出一遍。
但 `auto_run --force` 会重新分配编号（max+len+1），把目录搞乱。

这个工具的做法：
  1. 按台账逐件重新算网格（同参数，结果确定）
  2. 输出到临时目录
  3. 只把新生成的色号图拷回去，其余文件不碰

用法：
    python scripts/rechart.py            # 预演
    python scripts/rechart.py --yes      # 真做
    python scripts/rechart.py --yes --only 风景
"""
import argparse
import glob
import json
import os
import shutil
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PIL import Image

import auto_run as A
from config import CFG, dp


def _src_of(name, src_dir):
    for ext in (".jpg", ".png", ".jpeg", ".webp", ".tif", ".tiff", ".gif"):
        p = os.path.join(src_dir, name + ext)
        if os.path.exists(p):
            return p
    return None


def _find(tree, out, no, name):
    hits = glob.glob(os.path.join(out, tree, "*", f"{no:02d}_{name}", "*.png"))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=CFG["paths"]["out"])
    ap.add_argument("--src", default=CFG["paths"]["src"])
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--only", help="只处理某个分类")
    a = ap.parse_args()

    rows = json.load(open(dp(a.out, "台账数据_高保真.json"), encoding="utf-8"))
    if a.only:
        rows = [r for r in rows if r.get("cat") == a.only]
    if not rows:
        print("台账是空的")
        return 1

    miss = []
    todo = []
    for r in rows:
        s = _src_of(r["name"], a.src)
        if not s:
            miss.append(r["name"])
            continue
        todo.append((r, s))

    print(f"可重绘 {len(todo)} 件" + (f"，缺源图 {len(miss)} 件：{'、'.join(miss[:6])}" if miss else ""))
    if not a.yes:
        print("\n这是预演。加 --yes 执行。")
        return 0

    tmp = tempfile.mkdtemp(prefix="rechart_")
    ok = 0
    for r, src in todo:
        try:
            im = Image.open(src).convert("RGB")
            scene = A.is_scene(im)
            cut = im.convert("RGBA") if scene else A.auto_cut(im)[0]
            # 用台账里的实际格数，保证和原来一致
            CFG.setdefault("grid", {})
            CFG["grid"]["cols"] = int(r["cols"])
            CFG["grid"]["rows"] = int(r["rows"])
            CFG["paths"]["out"] = tmp
            A.do_high(cut, r["name"], r["no"], scene, tmp)

            # 只取色号图，拷回原位
            new = glob.glob(os.path.join(tmp, "社媒版", "*", f'{r["no"]:02d}_{r["name"]}', "03_色号图.png"))
            if not new:
                print(f"  ! {r['name']}: 没生成色号图")
                continue
            for dst in _find("社媒版", a.out, r["no"], r["name"]):
                if dst.endswith("03_色号图.png"):
                    shutil.copy2(new[0], dst)
            for dst in _find("交付版", a.out, r["no"], r["name"]):
                if dst.endswith("色号图.png"):
                    shutil.copy2(new[0], dst)
            ok += 1
            print(f"  ✓ {r['no']:02d} {r['name']}")
        except Exception as e:
            print(f"  ! {r['no']:02d} {r['name']}: {e}")

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n完成 {ok} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
