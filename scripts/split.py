# -*- coding: utf-8 -*-
"""split.py —— 把色号图切成小块，绕开网盘的预览降采样

为什么切：色号图 3500×5000 像素，网盘（夸克/百度）在线预览只加载缩小版，
客户一放大就糊。切成 1200×1600 的小块后，每块就是原尺寸，预览不降采样。

每块带 40px 重叠，相邻块有交集，拼的时候好对齐。

用法：
    python scripts/split.py <作品目录>
    python scripts/split.py --all
"""
import argparse
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PIL import Image, ImageDraw, ImageFont

from config import CFG

BLOCK_W, BLOCK_H = 1200, 1600
OVERLAP = 40


def _f(size):
    for p in (r"C:\Windows\Fonts\msyhbd.ttc", "/System/Library/Fonts/PingFang.ttc"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def split(chart_path, out_dir, prefix="色号图"):
    im = Image.open(chart_path).convert("RGB")
    W, H = im.size
    cols = max(1, -(-(W - OVERLAP) // (BLOCK_W - OVERLAP)))
    rows = max(1, -(-(H - OVERLAP) // (BLOCK_H - OVERLAP)))
    os.makedirs(out_dir, exist_ok=True)

    made = []
    for ry in range(rows):
        for rx in range(cols):
            x0 = rx * (BLOCK_W - OVERLAP)
            y0 = ry * (BLOCK_H - OVERLAP)
            x1, y1 = min(x0 + BLOCK_W, W), min(y0 + BLOCK_H, H)
            tile = im.crop((x0, y0, x1, y1))

            # 顶部加一条标签，写明这是第几块
            tag_h = 46
            canvas = Image.new("RGB", (tile.width, tile.height + tag_h), "white")
            canvas.paste(tile, (0, tag_h))
            d = ImageDraw.Draw(canvas)
            d.rectangle([0, 0, canvas.width, tag_h - 1], fill=(246, 244, 240))
            d.text((14, tag_h // 2), f"第 {ry + 1} 行 · 第 {rx + 1} 列（共 {rows}×{cols} 块）",
                   font=_f(24), fill=(90, 86, 84), anchor="lm")

            name = f"{prefix}_{ry + 1}-{rx + 1}.png"
            p = os.path.join(out_dir, name)
            canvas.save(p, optimize=True)
            made.append(name)
    return made, (rows, cols)


def _items(root):
    for f in ("03_色彩图.png", "03_色彩图_无标.png", "色号图.png"):
        if os.path.exists(os.path.join(root, f)):
            return [root]
    out = []
    for d in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        p = os.path.join(root, d)
        if os.path.isdir(p):
            out += _items(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default=CFG["paths"]["out"])
    a = ap.parse_args()

    if a.all:
        targets = _items(os.path.join(a.out, "分类"))
    elif a.path:
        targets = _items(a.path)
    else:
        print("给个目录，或用 --all")
        return 1

    for t in targets:
        ch = None
        for f in ("03_色彩图_无标.png", "03_色彩图.png", "色号图.png"):
            p = os.path.join(t, f)
            if os.path.exists(p):
                ch = p
                break
        if not ch:
            continue
        made, (r, c) = split(ch, os.path.join(t, "分块"))
        print(f"  ✓ {os.path.basename(t)}: {r}×{c} = {len(made)} 块")
    print("\n完成。每块约 1200×1600，网盘预览不会降采样。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
