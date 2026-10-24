# -*- coding: utf-8 -*-
"""card.py —— 生成小红书私信可发的交付卡片

小红书私信只能发文字和图片，不能发文件；图片还会被压到 1080 宽。
但**二维码压缩后照样能扫**，所以把网盘链接做成二维码印在图上，
客户长按识别 → 打开网盘 → 下载原图，色号就清楚了。

卡片内容：成品图 + 作品名 + 规格 + 二维码 + 提取码

用法：
    python scripts/card.py --url "https://pan.quark.cn/s/xxxx" --code ab12
    python scripts/card.py --url ... --code ... --item <作品目录>
"""
import argparse
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import segno
from PIL import Image, ImageDraw, ImageFont

from config import CFG, dp

W, H = 1080, 1440
PAPER = (250, 249, 246)
INK = (34, 32, 38)
MUTED = (138, 134, 130)
ACCENT = (198, 112, 92)

FONT_B = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_R = r"C:\Windows\Fonts\msyh.ttc"


def _f(size, bold=False):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT_R, size)
    except Exception:
        return ImageFont.load_default()


def _qr(data, px):
    q = segno.make(data, error="h")          # 高纠错，压缩后仍可扫
    tmp = os.path.join(dp(CFG["paths"]["out"], "缓存"), "_qr.png")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    q.save(tmp, scale=10, border=2, dark="black", light="white")
    im = Image.open(tmp).convert("RGB").resize((px, px), Image.NEAREST)
    os.remove(tmp)
    return im


def build(item_dir, url, code, out_path=None):
    name = os.path.basename(item_dir)
    no, _, title = name.partition("_")
    title = title or name

    canvas = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, W, 8], fill=ACCENT)

    # 成品图
    shot = None
    for f in ("02_成品图.jpg", "02_成品图.png", "01_原图.jpg", "01_原图.png"):
        p = os.path.join(item_dir, f)
        if os.path.exists(p):
            shot = Image.open(p).convert("RGB")
            break
    if shot:
        shot.thumbnail((620, 620), Image.LANCZOS)
        x = (W - shot.width) // 2
        canvas.paste(shot, (x, 90))
        d.rectangle([x - 1, 89, x + shot.width, 91 + shot.height], outline=(226, 222, 216))

    y = 90 + (620 if shot else 0) + 34

    d.text((W // 2, y), title, font=_f(54, True), fill=INK, anchor="ma")
    y += 78
    d.text((W // 2, y), "拼豆图纸 · 高清 PDF + 色号图", font=_f(28), fill=MUTED, anchor="ma")
    y += 58

    # 二维码
    qr = _qr(url, 300)
    canvas.paste(qr, ((W - 300) // 2, y))
    y += 300 + 40
    d.text((W // 2, y), "长按识别二维码 → 打开网盘", font=_f(30), fill=INK, anchor="ma")
    y += 58
    if code:
        d.text((W // 2, y), f"提取码：{code}", font=_f(34, True), fill=ACCENT, anchor="ma")
        y += 62
    else:
        y += 10
    d.text((W // 2, y), "下载后用 PDF 阅读器打开，双指放大，色号清晰可见",
           font=_f(24), fill=MUTED, anchor="ma")

    d.text((W // 2, H - 48), CFG["brand"].get("watermark") or "", font=_f(26), fill=(190, 186, 182), anchor="ma")

    out = out_path or os.path.join(item_dir, f"交付卡片_{title}.png")
    canvas.save(out, optimize=True)
    return out


def _items(root):
    if os.path.exists(os.path.join(root, "03_色彩图.png")):
        return [root]
    out = []
    for c in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        p = os.path.join(root, c)
        if not os.path.isdir(p):
            continue
        if os.path.exists(os.path.join(p, "03_色彩图.png")):
            out.append(p)
        else:
            out += _items(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="网盘分享链接")
    ap.add_argument("--code", default="", help="提取码")
    ap.add_argument("--item", help="单个作品目录")
    ap.add_argument("--all", action="store_true", help="分类下全部")
    ap.add_argument("--out", default=CFG["paths"]["out"])
    a = ap.parse_args()

    if a.item:
        targets = _items(a.item)
    elif a.all:
        targets = _items(os.path.join(a.out, "分类"))
    else:
        print("用 --item <目录> 或 --all")
        return 1

    print(f"共 {len(targets)} 件")
    for t in targets:
        p = build(t, a.url, a.code)
        print(f"  ✓ {os.path.basename(p)}")
    print("\n完成。卡片直接发小红书私信，客户长按识别二维码即可下载。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
