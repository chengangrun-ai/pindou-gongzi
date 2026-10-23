# -*- coding: utf-8 -*-
"""wm_hint.py —— 自动找「疑似水印」的位置，给人确认

水印没法 100% 自动去掉，但可以先标出来，省得一张张翻。

    python wm_hint.py --src <素材目录>

输出：每张图的疑似水印框（坐标），可直接粘进 batch34.CFG 或 HARD
"""
import os, sys, argparse, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
from scipy import ndimage

EXTS = (".jpg", ".jpeg", ".png", ".webp")


def candidates(path, max_n=4):
    """在四边和底部找「细长、低对比、像文字」的连通区域"""
    im = Image.open(path).convert("L")
    W, H = im.size
    a = np.asarray(im, np.float32)

    # 只扫四条边（水印几乎都在边上）：底部 18%、顶部 8%、左右各 8%
    bands = [
        (0, int(H*0.82), 0, W, "底部"),
        (0, int(H*0.08), 0, W, "顶部"),
        (0, H, 0, int(W*0.08), "左侧"),
        (0, H, int(W*0.92), W, "右侧"),
    ]
    out = []
    for y0, y1, x0, x1, where in bands:
        if y1 - y0 < 8 or x1 - x0 < 8:
            continue
        sub = a[y0:y1, x0:x1]
        # 局部对比度：高于背景但幅度小 = 半透明文字
        med = ndimage.median_filter(sub, 15)
        diff = sub - med
        mask = (np.abs(diff) > 6) & (np.abs(diff) < 45)
        mask = ndimage.binary_closing(mask, np.ones((3, 7)))
        lab, n = ndimage.label(mask)
        for i in range(1, n + 1):
            ys, xs = np.where(lab == i)
            if len(ys) < 40:
                continue
            bh, bw = ys.max()-ys.min()+1, xs.max()-xs.min()+1
            # 像一行字：宽 > 3×高，高 < 40px（相对 1000px 宽）
            if bw > 3*bh and 4 < bh < max(12, H*0.05) and bw > W*0.04:
                out.append((x0+xs.min(), y0+ys.min(), x0+xs.max()+1, y0+ys.max()+1,
                            where, round(float(np.abs(diff[ys, xs]).mean()), 1)))
    out.sort(key=lambda r: -r[5])
    return out[:max_n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None)
    ap.add_argument("--all", action="store_true", help="连没检测到也打印")
    a = ap.parse_args()
    if a.src is None:
        from config import CFG
        a.src = CFG["paths"]["src"]
    files = [p for p in sorted(glob.glob(os.path.join(a.src, "*"))) if p.lower().endswith(EXTS)]
    if not files:
        print("素材目录里没有图片：", a.src); return

    hit = 0
    for p in files:
        try:
            c = candidates(p)
        except Exception as e:
            print(f"{os.path.basename(p)}  读取失败：{e}"); continue
        if not c and not a.all:
            continue
        hit += 1
        print(f"\n{os.path.basename(p)}   {Image.open(p).size}")
        if not c:
            print("   未发现疑似水印")
        for x0, y0, x1, y1, where, s in c:
            print(f"   [{where}] ({x0}, {y0}, {x1}, {y1})   强度 {s}")
    print(f"\n共扫 {len(files)} 张，{hit} 张有疑似水印。")
    print("确认后写进 batch34.CFG 第 4 个字段：[(x0, y0, x1, y1)]，切不掉就用 HARD 硬裁。")


if __name__ == "__main__":
    main()
