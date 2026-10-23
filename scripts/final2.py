# -*- coding: utf-8 -*-
"""final2.py —— 抠图 → 角色浮在亚麻纸上（无白板）"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
import batch34 as M, cutout as C, fidelity as F, fastgrid as FG, brand as BR
import floatcard as FC

LADDER = (128, 160, 192, 224, 256)
Kof = lambda c: int(min(64, 20 + c / 5))
rows = []

for i, (fn, (name, _c, crop, wms)) in enumerate(sorted(M.CFG.items()), 1):
    im = Image.open(os.path.join(M.SRC, fn)).convert("RGB")
    for r in wms:
        im = M.median_fill(im, r) if isinstance(r, str) else M.clone_fill(im, r)
    if fn in M.HARD:
        im = im.crop(M.HARD[fn])
    if crop:
        im = im.crop(crop)
    cut = C.square_pad(C.trim(C.cutout(im)))

    best = None
    for c in LADDER:
        W = c * 3
        small = cut.resize((W, W), Image.LANCZOS)
        white = C.on_white(small)
        g, p = FG.beadify_fast(white, c, K=Kof(c))
        g = np.where(FC.grid_alpha(small, c) > 0.35, g, -1)
        s = F.score(white, g, p, blur=3)
        if best is None or s > best[3]:
            best = (c, small, white, s, g, p)
    cols, small, white, sc, grid, pal = best
    NR, NC = grid.shape

    d = os.path.join(M.OUT, f"{i:02d}_{name}")
    dn = os.path.join(M.OUT, "无LOGO版", f"{i:02d}_{name}")
    os.makedirs(d, exist_ok=True); os.makedirs(dn, exist_ok=True)

    M.to_card(cut).save(os.path.join(d, "01_原图.png"))
    plain = BR.paper(*M.CARD)
    s2 = min((M.CARD[0]*0.66)/cut.width, (M.CARD[1]*0.72)/cut.height)
    t = cut.resize((int(cut.width*s2), int(cut.height*s2)), Image.LANCZOS)
    plain.paste(t, ((M.CARD[0]-t.width)//2, int(M.CARD[1]*0.45)-t.height//2), t)
    plain.save(os.path.join(dn, "01_原图_无标.png"))

    FC.float_card(grid, pal).save(os.path.join(d, "02_成品图.png"))
    BR.render_chart(grid, pal, name).save(os.path.join(d, "03_色彩图.png"))
    BR.render_compare(cut, BR.mosaic(grid, pal, 12), name).save(os.path.join(d, "04_对比图.png"))
    FC.float_card(grid, pal, mark=False).save(os.path.join(dn, "02_成品图_无标.png"))
    BR.render_chart(grid, pal, name, mark=False).save(os.path.join(dn, "03_色彩图_无标.png"))
    BR.render_compare(cut, BR.mosaic(grid, pal, 12), name, mark=False).save(os.path.join(dn, "04_对比图_无标.png"))

    rows.append(dict(no=i, name=name, file=fn, cols=int(NC), rows=int(NR),
                     beads=int((grid >= 0).sum()), colors=len(pal),
                     fidelity=round(float(sc), 4), path=d,
                     thumb=os.path.join(d, "01_原图.png")))
    print(f"{i:02d} {name:10s} {NC}x{NR} {len(pal):2d}色 {int((grid>=0).sum()):6d}颗 还原={sc:.4f}")

json.dump(rows, open(os.path.join(M.OUT, "_rows.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("DONE", len(rows))
