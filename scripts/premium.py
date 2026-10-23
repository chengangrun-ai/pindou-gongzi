# -*- coding: utf-8 -*-
"""premium.py —— 精品低色号版：不碎的前提下，色数压到最低"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
import batch34 as M, cutout as C, fidelity as F, brand as BR
import floatcard as FC, lowcolor as L

OUT = M.OUT
PRE = os.path.join(OUT, "精品版")
COLS_LADDER = (96, 112, 128, 160)
K_LADDER = (10, 12, 14, 16, 20, 24)
from config import CFG as _C
SPECKLE_MAX = _C["pipeline"]["speckle_max"]
FID_MIN = _C["pipeline"]["fidelity_min"]


def speckle(g):
    return L.speckle_vec(g)


def load_cut(r):
    fn, name = r["file"], r["name"]
    if fn in M.CFG:
        im = Image.open(os.path.join(M.SRC, fn)).convert("RGB")
        for w in M.CFG[fn][3]:
            im = M.median_fill(im, w) if isinstance(w, str) else M.clone_fill(im, w)
        if fn in M.HARD:
            im = im.crop(M.HARD[fn])
        if M.CFG[fn][2]:
            im = im.crop(M.CFG[fn][2])
        if fn in M.GRAB:
            return C.square_pad(C.trim(C.cutout_photo(im, rect_ratio=(0.08, 0.02, 0.84, 0.96))))
        return C.square_pad(C.trim(C.cutout(im)))
    if "胡子" in name:
        p = r'C:/Cami chan\wechat talk\xwechat_files\wxid_nxfwyr0a45nr22_df7e\temp\RWTemp\2026-10\cdcdea6c8061a6c29bd850575f779bb2\434ff8f3ad27360639b62cd7a7e00fb5.jpg'
        return C.square_pad(C.trim(C.cutout_photo(Image.open(p).convert("RGB"))))
    src = os.path.join(r"C:/Users/Administrator/.workbuddy-ai/clipboard-images", fn)
    # 整幅场景：保持原始 3:4 构图（不要 center_square，否则和高保真版构图不一致）
    im = Image.open(src).convert("RGB")
    im = im.resize((768, int(im.height * 768 / im.width)), Image.LANCZOS)
    return im.convert("RGBA")   # alpha 全 255，走统一路径


rows = json.load(open(os.path.join(OUT, "台账数据_高保真.json"), encoding="utf-8"))
TARGET = {35,36,37,38,40,41,42,43,44,45,46,47}
rows = [r for r in rows if r["no"] in TARGET]
prem = json.load(open(os.path.join(OUT,"台账数据_精品版.json"),encoding="utf-8")) if os.path.exists(os.path.join(OUT,"台账数据_精品版.json")) else []
for r in rows:
    i, name = r["no"], r["name"]
    try:
        cut = load_cut(r)
        best = None
        for cols in COLS_LADDER:
            for K in K_LADDER:
                small = cut.resize((cols*3, int(cut.height * cols*3 / cut.width)), Image.LANCZOS)
                g, p = L.beadify_low(small, cols, K)
                if small.mode == "RGBA":          # 整幅场景没有 alpha，不能做透明置空
                    g = np.where(FC.grid_alpha(small, cols) > 0.35, g, -1)
                wi = min(range(len(p)), key=lambda k: sum(abs(int(p[k][1][j:j+2], 16)-255) for j in (1, 3, 5)))
                sc = float(F.score(C.on_white(small), np.where(g >= 0, g, wi), p, blur=3))
                sp = speckle(g)
                if sp <= SPECKLE_MAX and sc >= FID_MIN:
                    best = dict(cols=cols, K=K, grid=g, pal=p, score=sc, sp=sp)
                    break
            if best:
                break
        if best is None:
            print(f"{i:02d} {name:10s} 不达标，跳过（保持高保真版）")
            continue

        d = os.path.join(PRE, f"{i:02d}_{name}")
        dn = os.path.join(PRE, "无LOGO版", f"{i:02d}_{name}")
        os.makedirs(d, exist_ok=True); os.makedirs(dn, exist_ok=True)

        M.to_card(cut).save(os.path.join(d, "01_原图.png"))
        plain = BR.paper(*M.CARD)
        s2 = min((M.CARD[0]*0.66)/cut.width, (M.CARD[1]*0.72)/cut.height)
        t = cut.resize((int(cut.width*s2), int(cut.height*s2)), Image.LANCZOS)
        plain.paste(t, ((M.CARD[0]-t.width)//2, int(M.CARD[1]*0.45)-t.height//2), t)
        plain.save(os.path.join(dn, "01_原图_无标.png"))

        g, p = best["grid"], best["pal"]
        if r["no"] >= 40:
            BR.render_card(g, p).save(os.path.join(d, "02_成品图.png"))
            BR.render_card(g, p, mark=False).save(os.path.join(dn, "02_成品图_无标.png"))
        else:
            FC.float_card(g, p).save(os.path.join(d, "02_成品图.png"))
            FC.float_card(g, p, mark=False).save(os.path.join(dn, "02_成品图_无标.png"))
        BR.render_chart(g, p, name).save(os.path.join(d, "03_色彩图.png"))
        BR.render_chart(g, p, name, mark=False).save(os.path.join(dn, "03_色彩图_无标.png"))
        BR.render_compare(cut, BR.mosaic(g, p, 14), name).save(os.path.join(d, "04_对比图.png"))
        BR.render_compare(cut, BR.mosaic(g, p, 14), name, mark=False).save(os.path.join(dn, "04_对比图_无标.png"))

        NR, NC = g.shape
        prem.append(dict(no=i, name=name, cols=int(NC), rows=int(NR),
                         beads=int((g >= 0).sum()), colors=len(p),
                         fidelity=round(best["score"], 4), speckle=round(best["sp"], 3)))
        print(f"{i:02d} {name:10s} {NC}x{NR} {len(p):2d}色 {int((g>=0).sum()):5d}颗 还原={best['score']:.4f} 碎={best['sp']:.3f}")
    except Exception as e:
        print(f"{i:02d} {name:10s} FAIL {e}")

dedup = {}
for x in prem:
    dedup[x["no"]] = x
prem = sorted(dedup.values(), key=lambda x: x["no"])
json.dump(prem, open(os.path.join(OUT, "台账数据_精品版.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("DONE", len(prem), "/", len(rows))
