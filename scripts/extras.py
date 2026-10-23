# -*- coding: utf-8 -*-
"""extras.py —— 增强件：预处理 / 查重 / 采购单 / 评级 / 画廊 / 打印分页

这些都不影响主流程，但让工具在真实使用中更省心。
"""
import os, sys, hashlib, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PIL import Image, ImageDraw, ImageFont

MAX_SIDE = 2400          # 超大图先缩到这个尺寸再算，避免卡死


# ---------------- 1. 图片预处理 ----------------
def preprocess(path):
    """EXIF 转向 / 透明 PNG / 超大图 / GIF·TIFF / 损坏图 / 极小图 / 裁白边"""
    notes = []
    try:
        im = Image.open(path)
        # 动图取第一帧 / 多页取第一页
        if getattr(im, "n_frames", 1) > 1:
            im.seek(0); notes.append(f"取第1帧/{im.n_frames}")
        elif getattr(im, "is_animated", False):
            im.seek(0); notes.append("动图")
    except Exception as e:
        raise RuntimeError(f"图片读不了（{os.path.basename(path)}）：{e}")

    # EXIF 方向（手机拍的常见，不转就是歪的）
    try:
        from PIL import ImageOps
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass

    # 透明 PNG：alpha 已经是抠好的，直接当抠图结果用
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    if has_alpha:
        im = im.convert("RGBA")
        a = np.asarray(im.split()[3])
        if (a < 250).mean() > 0.02:      # 真的有透明区域
            notes.append("透明底")

    # 16bit / CMYK / 灰度
    if im.mode in ("I;16", "I", "F"):
        im = im.point(lambda v: v / 256).convert("L")
        notes.append("16bit")
    if im.mode == "CMYK":
        im = im.convert("RGB")
        notes.append("CMYK")
    if im.mode == "L":
        im = im.convert("RGB")
        notes.append("灰度")

    # 极小图警告
    if min(im.size) < 200:
        notes.append("原图过小")

    # 自动裁掉四周纯色边框带
    try:
        a = np.asarray(im.convert("RGB"), np.int16)
        def uniform(line):
            return line.max(0) - line.min(0) < 10 and line.std(0).mean() < 8
        t = 0
        while t < a.shape[0] // 4 and uniform(a[t]):
            t += 1
        b = a.shape[0]
        while b > a.shape[0] * 3 // 4 and uniform(a[b - 1]):
            b -= 1
        l = 0
        while l < a.shape[1] // 4 and uniform(a[:, l]):
            l += 1
        r = a.shape[1]
        while r > a.shape[1] * 3 // 4 and uniform(a[:, r - 1]):
            r -= 1
        if (t or b < a.shape[0] or l or r < a.shape[1]) and (b - t) > 50 and (r - l) > 50:
            im = im.crop((l, t, r, b)); notes.append("裁白边")
    except Exception:
        pass

    # 超大图
    if max(im.size) > MAX_SIDE:
        s = MAX_SIDE / max(im.size)
        im = im.resize((int(im.width*s), int(im.height*s)), Image.LANCZOS)
        notes.append(f"缩到{MAX_SIDE}")

    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    return im, notes


# ---------------- 2. 重复图检测 ----------------
def ahash(im, n=16):
    """平均哈希：缩放成 n×n 灰度，比均值大小 → 0/1 位串"""
    a = np.asarray(im.convert("L").resize((n, n), Image.LANCZOS), np.float32)
    bits = (a > a.mean()).flatten()
    return "".join("1" if b else "0" for b in bits)


def ham(a, b):
    return sum(x != y for x, y in zip(a, b))


def find_dup(im, known, thr=6):
    """和已有作品比对，汉明距离 ≤thr 视为重复。known: [(name, hash)]"""
    h = ahash(im)
    for name, kh in known:
        if ham(h, kh) <= thr:
            return name, ham(h, kh)
    return None, 0


# ---------------- 3. 采购清单 ----------------
def purchase_list(pal, bead_mm=5.0):
    """pal: [(code, hex, name, count)] → 按用量排序，估算需要买几包（1000 颗/包）"""
    rows = []
    for code, hx, nm, cnt in sorted(pal, key=lambda x: -x[3]):
        packs = max(1, math.ceil(cnt / 1000 * 1.15))     # 留 15% 损耗
        rows.append(dict(code=code, hex=hx, name=nm, count=int(cnt), packs=packs))
    return rows


def purchase_md(name, pal, bead_mm=5.0):
    rows = purchase_list(pal, bead_mm)
    total = sum(r["count"] for r in rows)
    lines = [f"### {name}", "",
             f"共 {len(rows)} 色 / {total} 颗", "",
             "| 色号 | 颜色 | 名称 | 用量 | 建议买 |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['code']} | `{r['hex']}` | {r['name']} | {r['count']} 颗 | {r['packs']} 包 |")
    return "\n".join(lines)


# ---------------- 4. 质量分级 ----------------
def grade(fidelity, speckle=0.0, colors=0):
    """A 可主推 / B 可用 / C 建议复查
    阈值和流水线自己的验收线对齐（speckle 上限 0.048）：
    A 还原 ≥96% 且几乎不碎 / B 还原 ≥92% 且碎点在容差内 / C 其余"""
    try:
        from config import CFG as _C
        sp_max = _C["pipeline"]["speckle_max"]
        fid_min = _C["pipeline"]["fidelity_min"]
    except Exception:
        sp_max, fid_min = 0.048, 0.90
    if fidelity >= fid_min + 0.06 and speckle <= sp_max * 0.52:
        return "A"
    if fidelity >= fid_min + 0.02 and speckle <= sp_max:
        return "B"
    return "C"


# ---------------- 5. HTML 画廊 ----------------
def gallery(out_dir, rows, title="拼豆图纸"):
    """生成 gallery.html，一页看完全部作品，点开看大图"""
    items = []
    for r in sorted(rows, key=lambda x: x["no"]):
        d = f'{r["no"]:02d}_{r["name"]}'
        thumb = f"{d}/02_成品图.png"
        if not os.path.exists(os.path.join(out_dir, thumb)):
            continue
        g = r.get("grade", "")
        items.append(f'''
    <figure>
      <a href="{d}/03_色彩图.png" target="_blank"><img src="{thumb}" loading="lazy" alt="{r["name"]}"></a>
      <figcaption><b>{r["no"]:02d} {r["name"]}</b>
        <span class="meta">{r["cols"]}×{r["rows"]} · {r["colors"]}色 · {r["beads"]}颗</span>
        <span class="grade g{g}">{g}</span></figcaption>
    </figure>''')

    html = f'''<!doctype html><html lang="zh"><meta charset="utf-8">
<title>{title}</title>
<style>
:root{{--ink:#26242a;--sub:#8b8890;--bg:#faf9f7;--card:#fff}}
*{{box-sizing:border-box}}
body{{margin:0;padding:28px;background:var(--bg);color:var(--ink);
 font:15px/1.6 "PingFang SC","Microsoft YaHei",system-ui,sans-serif}}
h1{{font-size:22px;margin:0 0 6px}} .sub{{color:var(--sub);font-size:13px;margin-bottom:22px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:16px}}
figure{{margin:0;background:var(--card);border-radius:10px;overflow:hidden;
 box-shadow:0 1px 3px rgba(0,0,0,.07);transition:.15s}}
figure:hover{{transform:translateY(-2px);box-shadow:0 6px 18px rgba(0,0,0,.12)}}
img{{width:100%;display:block;aspect-ratio:3/4;object-fit:cover;background:#eee}}
figcaption{{padding:8px 10px;font-size:12px}}
figcaption b{{display:block;font-size:13px;margin-bottom:2px}}
.meta{{color:var(--sub)}}
.grade{{float:right;font-weight:700;padding:0 6px;border-radius:4px;color:#fff}}
.gA{{background:#2e9e5b}} .gB{{background:#c9963c}} .gC{{background:#b45a4f}}
</style>
<h1>{title}</h1>
<div class="sub">共 {len(items)} 件 · 点图看色号图纸 · A 可主推 / B 可用 / C 建议复查</div>
<div class="grid">{''.join(items)}</div></html>'''
    p = os.path.join(out_dir, "gallery.html")
    open(p, "w", encoding="utf-8").write(html)
    return p


# ---------------- 6. 打印分页 PDF ----------------
def chart_to_pdf(chart_path, pdf_path, dpi=150, overlap=40):
    """把超宽图纸切成 A4 页，带页码和对齐标记，方便打印后拼起来"""
    im = Image.open(chart_path).convert("RGB")
    W, H = im.size
    pw, ph = int(8.27*dpi), int(11.69*dpi)          # A4 @ dpi
    m = int(0.28*dpi)                                # 页边距
    cw, ch = pw - 2*m, ph - 2*m
    cols = math.ceil((W - overlap) / (cw - overlap))
    rows = math.ceil((H - overlap) / (ch - overlap))
    pages = []
    for ry in range(rows):
        for rx in range(cols):
            x0 = rx * (cw - overlap); y0 = ry * (ch - overlap)
            x1 = min(x0 + cw, W); y1 = min(y0 + ch, H)
            tile = im.crop((x0, y0, x1, y1))
            page = Image.new("RGB", (pw, ph), "white")
            page.paste(tile, (m, m))
            d = ImageDraw.Draw(page)
            d.rectangle([m-2, m-2, m+tile.width+2, m+tile.height+2], outline=(200, 200, 200))
            try:
                f = ImageFont.truetype(
                    "C:/Windows/Fonts/msyh.ttc" if os.name == "nt" else
                    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 16)
            except Exception:
                f = ImageFont.load_default()
            d.text((m, ph - m + 6), f"第 {ry*cols+rx+1} / {rows*cols} 页   "
                                    f"行{ry+1}列{rx+1}   拼贴时按灰框对齐（重叠 {overlap}px）",
                   font=f, fill=(90, 90, 90))
            # 四角对齐标记
            for (cx, cy) in ((m, m), (m+tile.width, m), (m, m+tile.height), (m+tile.width, m+tile.height)):
                d.line([(cx-8, cy), (cx+8, cy)], fill=(180, 180, 180))
                d.line([(cx, cy-8), (cx, cy+8)], fill=(180, 180, 180))
            pages.append(page)
    pages[0].save(pdf_path, save_all=True, append_images=pages[1:], resolution=dpi)
    return pdf_path, len(pages)


if __name__ == "__main__":
    print("extras.py 是工具库，用 auto_run.py 调用")


# ---------------- 7. 定价建议 ----------------
def price_hint(beads, colors, fidelity=0.95):
    """按豆数和色数给一个建议售价区间（人民币）"""
    base = 4.0
    if beads > 20000:
        base = 12.0
    elif beads > 12000:
        base = 9.0
    elif beads > 8000:
        base = 7.0
    elif beads > 4000:
        base = 5.0
    if colors >= 40:
        base += 3.0
    elif colors >= 25:
        base += 1.5
    if fidelity >= 0.97:
        base += 2.0
    lo, hi = max(3, base * 0.8), base * 1.5
    return round(lo, 0), round(hi, 0)


# ---------------- 8. 文案 A/B 变体 ----------------
TITLE_STYLES = {
    "直白": "{name}｜拼豆图纸",
    "卖点": "{name}｜{colors}色 {beads}颗 新手也能拼",
    "治愈": "把{name}拼成一颗一颗的｜{cols}×{rows}",
}


def title_variants(name, cols, rows, colors, beads):
    return [v.format(name=name, cols=cols, rows=rows, colors=colors, beads=beads)
            for v in TITLE_STYLES.values()]


# ---------------- 9. 发布排期 ----------------
def schedule(n, per_week=5, start_weekday="周一"):
    """按每周 per_week 条给出排期建议"""
    out = []
    for i in range(n):
        w, d = divmod(i, per_week)
        out.append(f"第{w+1}周 第{d+1}条")
    return out


# ---------------- 10. 素材来源记录 ----------------
def source_note(path):
    """记录素材文件名 + 哈希，便于版权追溯"""
    import hashlib
    h = hashlib.md5(open(path, "rb").read()).hexdigest()[:16]
    return dict(file=os.path.basename(path), md5=h,
                added=time.strftime("%Y-%m-%d %H:%M") if (time := __import__("time")) else "")


# ---------------- 11. 纹理缓存 ----------------
_PAPER_CACHE = {}


def paper_cached(brand, w, h, style=None):
    key = (w, h, style)
    if key not in _PAPER_CACHE:
        _PAPER_CACHE[key] = brand.paper(w, h, style=style)
    return _PAPER_CACHE[key].copy()


# ---------------- 12. 文件名安全化 ----------------
def safe_name(name, maxlen=40):
    """去掉路径分隔符和控制字符，限制长度（emoji 保留）"""
    bad = '\\/:*?"<>|\n\r\t'
    out = "".join(ch for ch in name if ch not in bad).strip()
    return (out or "未命名")[:maxlen]


# ---------------- 13. 量化误差热力图（调试） ----------------
def error_heatmap(im, grid, pal, out_path):
    """把每格的量化误差画成热力图，用于排查「哪块颜色失真」"""
    from PIL import ImageDraw
    P = np.array([[int(p[1][1:3], 16), int(p[1][3:5], 16), int(p[1][5:7], 16)] for p in pal], np.float32)
    NR, NC = grid.shape
    H, W = im.height // NR, im.width // NC
    src = np.asarray(im.convert("RGB").resize((NC * W, NR * H)), np.float32)
    err = np.zeros((NR, NC), np.float32)
    for y in range(NR):
        for x in range(NC):
            k = grid[y, x]
            if k < 0:
                continue
            blk = src[y*H:(y+1)*H, x*W:(x+1)*W]
            err[y, x] = np.abs(blk - P[k]).mean()
    e = err / max(err.max(), 1)
    hm = Image.fromarray((np.stack([e, 1 - e, np.zeros_like(e)], -1) * 255).astype(np.uint8))
    hm = hm.resize((NC * 6, NR * 6), Image.NEAREST)
    hm.save(out_path)
    return out_path, float(err.mean())


# ---------------- 14. 竞品参数对照 ----------------
def competitor_table(rows):
    lines = ["## 与市面同类图纸对照", "",
             "| 项目 | 本工具（精品版） | 市面常见 |", "|---|---|---|"]
    if rows:
        cs = [r for r in rows if r.get("colors")]
        beads = [r["beads"] for r in rows]
        lines.append(f"| 色数 | {min(r['colors'] for r in cs)}–{max(r['colors'] for r in cs)} 色 | 10–20 色 |")
        lines.append(f"| 豆数 | {min(beads):,}–{max(beads):,} 颗 | 5,000–8,000 颗 |")
        lines.append(f"| 图纸色号 | 每格标注 + 用量百分比 | 多数只给色块 |")
        lines.append(f"| 版本 | 高保真 / 精品 双版本 | 单一版本 |")
    return "\n".join(lines)
