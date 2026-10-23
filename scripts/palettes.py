# -*- coding: utf-8 -*-
"""palettes.py —— 品牌色板：把自编色号换成真实可买到的色号

    from palettes import snap
    g2, pal2 = snap(grid, pal, "mard")

原理：先按正常流程算出 K 个颜色，再把每个颜色「吸附」到品牌色板里最近的那个色，
色号、色值都换成品牌的。两个颜色吸附到同一色号时自动合并。
"""
import os, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PAL_DIR = os.path.join(os.path.dirname(HERE), "palettes")
_cache = {}


def _rgb(hx):
    hx = hx.lstrip("#")
    return np.array([int(hx[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255.0


def _lab(rgb):
    """sRGB → CIE Lab（只用于求最近色，简化版足够）"""
    c = np.where(rgb > 0.04045, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805],
                  [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]], np.float32)
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883], np.float32)
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])], np.float32)


def load(name="mard"):
    """返回 [(code, hex), ...]"""
    key = name.lower()
    if key in _cache:
        return _cache[key]
    p = os.path.join(PAL_DIR, key + ".json")
    if not os.path.exists(p):
        return []
    d = json.load(open(p, encoding="utf-8"))
    out = [(c["code"], c["hex"]) for c in d["colors"]]
    _cache[key] = out
    return out


def available():
    if not os.path.isdir(PAL_DIR):
        return []
    return sorted(os.path.splitext(f)[0] for f in os.listdir(PAL_DIR) if f.endswith(".json"))


def snap(grid, pal, name="mard"):
    """把调色板吸附到品牌色板

    grid: (NR,NC) int16，-1 为透明
    pal:  [(code, hex, label, count), ...]
    返回新的 (grid, pal)
    """
    brand = load(name)
    if not brand or not pal:
        return grid, pal

    brand_lab = np.stack([_lab(_rgb(h)) for _, h in brand])
    mapping = []
    for entry in pal:
        lb = _lab(_rgb(entry[1]))
        d = np.linalg.norm(brand_lab - lb, axis=1)
        mapping.append(int(d.argmin()))

    # 合并吸附到同一品牌色的
    uniq, new_pal = {}, []
    for bi in mapping:
        if bi not in uniq:
            uniq[bi] = len(new_pal)
            code, hx = brand[bi]
            new_pal.append((code, hx, "", 0))

    remap = np.array([uniq[b] for b in mapping], np.int16)
    safe = np.clip(grid, 0, len(remap) - 1)
    g2 = np.where(grid >= 0, remap[safe], -1).astype(np.int16)

    # 重算用量
    counts = np.bincount(g2[g2 >= 0], minlength=len(new_pal))
    new_pal = [(c, h, n, int(counts[i])) for i, (c, h, n, _) in enumerate(new_pal)]
    # 按用量排序（图纸色卡会按这个顺序排）
    order = sorted(range(len(new_pal)), key=lambda i: -new_pal[i][3])
    idx_map = np.zeros(len(new_pal), np.int16)
    for newi, oldi in enumerate(order):
        idx_map[oldi] = newi
    g3 = np.where(g2 >= 0, idx_map[np.clip(g2, 0, None)], -1).astype(np.int16)
    return g3, [new_pal[i] for i in order]


if __name__ == "__main__":
    import sys
    names = available()
    if "--list" in sys.argv or len(sys.argv) == 1:
        print("可用色板：")
        for n in names:
            d = load(n)
            print(f"  {n:10s} {len(d):3d} 色   示例 {d[0][0]} {d[0][1]}")
        print("\n切换：config.json 的 palette.name 改成上面的名字")


def score(pal, name="mard"):
    """这套颜色用该品牌色板还原的加权误差（越小越贴合）"""
    brand = load(name)
    if not brand or not pal:
        return 1e9
    brand_lab = np.stack([_lab(_rgb(h)) for _, h in brand])
    total, wsum = 0.0, 0
    for entry in pal:
        lb = _lab(_rgb(entry[1]))
        d = float(np.linalg.norm(brand_lab - lb, axis=1).min())
        w = max(int(entry[3]), 1)
        total += d * w
        wsum += w
    return total / max(wsum, 1)


def pick(pal, names=None):
    """在这几套色板里挑最贴合的一个 → (名字, [(名字, 分数), ...])"""
    names = names or available()
    res = [(n, score(pal, n)) for n in names]
    res.sort(key=lambda x: x[1])
    return res[0][0], res
