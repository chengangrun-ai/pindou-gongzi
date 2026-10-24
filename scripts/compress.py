# -*- coding: utf-8 -*-
"""compress.py —— 给交付目录降重

三类文件分开处理，各用各的最优方式：

| 文件 | 处理 | 典型效果 |
|---|---|---|
| `01_原图` `02_成品图` `04_对比图` | 256 色量化 + 抖动（原地覆盖） | 2.2MB → 0.6MB |
| `03_色彩图` | PNG 调色板量化（色号是文字，不能有损） | 6.0MB → 3.1MB |
| 缩略图 | 跳过 | — |

用法：
    python scripts/compress.py                # 预演，只统计
    python scripts/compress.py --yes          # 真的压
    python scripts/compress.py --yes --q 88   # JPEG 质量（默认 92）
"""
import argparse
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PIL import Image

from config import CFG

PHOTO = ("01_原图", "02_成品图", "04_对比图")
CHART = ("03_色彩图",)


def _mb(p):
    return os.path.getsize(p) / 1048576


def _is(dirname, prefixes):
    return any(dirname.startswith(p) for p in prefixes)


def _walk(out):
    for root, dirs, files in os.walk(out):
        if "内部数据" in root or "台账备份" in root or "缩略图缓存" in root:
            continue
        for f in files:
            if f.lower().endswith(".png"):
                yield root, f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=CFG["paths"]["out"])
    ap.add_argument("--yes", action="store_true", help="真的执行（默认只统计）")
    ap.add_argument("--q", type=int, default=92, help="JPEG 质量，默认 92")
    a = ap.parse_args()

    todo = list(_walk(a.out))
    if not todo:
        print("没找到需要处理的 PNG")
        return 1

    before = after = 0.0
    n_jpg = n_png = 0
    for root, f in todo:
        p = os.path.join(root, f)
        try:
            before += _mb(p)
        except Exception:
            continue
        if _is(f, PHOTO):
            # 照片：量化 + 抖动（原地覆盖，不删文件）
            after += 0.33 * _mb(p)
            n_jpg += 1
            if a.yes:
                im = Image.open(p).convert("RGB")
                im.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG) \
                  .save(p, optimize=True, compress_level=9)
        elif _is(f, CHART):
            # 色号图：量化但不抖动（保住文字边缘）
            after += 0.52 * _mb(p)
            n_png += 1
            if a.yes:
                im = Image.open(p).convert("RGB")
                im.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.NONE) \
                  .save(p, optimize=True, compress_level=9)
        else:
            after += _mb(p)

    print(f"待处理：{n_jpg} 张照片量化，{n_png} 张色号图量化")
    print(f"体积：{before:,.0f} MB → 约 {after:,.0f} MB（省 {100 - after / max(before, 1) * 100:.0f}%）")
    if not a.yes:
        print("\n这是预演。确认后加 --yes 执行。")
        return 0

    after_real = sum(os.path.getsize(os.path.join(r, x)) / 1048576
                     for r, _, fs in os.walk(a.out) for x in fs
                     if x.lower().endswith((".png", ".jpg")) and "内部数据" not in r)
    print(f"完成。实际体积：{after_real:,.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
