# -*- coding: utf-8 -*-
"""auto_run.py —— 一键入口：丢图进来，出全套

    python auto_run.py                        # 扫默认素材目录，处理所有新图
    python auto_run.py --src D:\\图            # 指定素材目录
    python auto_run.py --jobs 4               # 4 张并行（默认按 CPU）
    python auto_run.py --name 小猫            # 单张时指定作品名
    python auto_run.py --limit 3              # 只做前 3 张
    python auto_run.py --only 小猫,小狗        # 只做指定作品名
    python auto_run.py --dry                  # 只检测判断，不出图
    python auto_run.py --no-premium           # 只出高保真版
    python auto_run.py --pdf                  # 顺带出 A4 打印分页 PDF
    python auto_run.py --bead-mm 2.6          # 豆径 mm
    python auto_run.py --force                # 重复图也照做
"""
import os, sys, json, argparse, glob, time, traceback, logging, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PIL import Image
from scipy import ndimage

from config import CFG, dp
import batch34 as M
import cutout as C
import fidelity as F
import fastgrid as FG
import brand as BR
import floatcard as FC
import lowcolor as L
import extras as X
import palettes as PAL
import categorize as CAT
import ledger as LEDGER
import simplify as SIMP

HERE = os.path.dirname(os.path.abspath(__file__))
EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".ico", ".jfif")

P = CFG["pipeline"]
HI_LADDER = tuple(P["hi_cols"])
MAX_COLS = int((CFG.get("grid") or {}).get("max_cols", 160))
LOW_COLS = tuple(P["lo_cols"])
LOW_K = tuple(P["lo_k"])
SPECKLE_MAX = P["speckle_max"]
FID_MIN = P["fidelity_min"]
SCENE_FLAT = P["scene_flat_ratio"]


# ---------------- 判断 ----------------
def flat_ratio(im, w=400):
    h = max(8, int(w * im.height / im.width))
    a = np.asarray(im.convert("L").resize((w, h)), np.float32)
    mag = np.hypot(ndimage.sobel(a, 0), ndimage.sobel(a, 1))
    return float((mag < 12).mean())


def border_variance(im, w=0.06):
    """四条边带的颜色标准差：平色背景接近 0，满幅照片很大"""
    a = np.asarray(im.convert("RGB"), np.int16)
    h, wd = a.shape[:2]
    b = max(2, int(min(h, wd) * w))
    strips = [a[:b], a[-b:], a[:, :b], a[:, -b:]]
    return float(np.mean([s.reshape(-1, 3).std(0).mean() for s in strips]))


def is_scene(im):
    """判定是否整幅做豆板（不抠图）

    顺序很重要：
    1. 线稿 → 不是场景（走线稿模式）
    2. 四条边都不干净（色差 > 12）→ 场景，满幅照片没有可分离的主体
    3. 其余看平整度
    """
    if L.is_lineart(im):
        return False
    if border_variance(im) > 12:
        return True
    return flat_ratio(im) < SCENE_FLAT


def border_is_flat(im, thr=14):
    A = np.asarray(im.convert("RGB")).astype(np.float32)
    ring = np.concatenate([A[0, :], A[-1, :], A[:, 0], A[:, -1]])
    return float(ring.std(0).mean()) < thr


def auto_cut(im):
    if im.mode == "RGBA":
        a = np.asarray(im.split()[3])
        if (a < 250).mean() > 0.02:          # 透明 PNG 已经抠好了
            return C.square_pad(C.trim(im)), "透明底"
    if border_is_flat(im):
        cut = C.square_pad(C.trim(C.cutout(im)))
        cut = C.clean_alpha(cut)
        cov = np.asarray(cut.split()[3]).mean() / 255
        if 0.04 < cov < 0.92:
            return cut, "平色判据"
    cut = C.square_pad(C.trim(C.cutout_photo(im, rect_ratio=(0.08, 0.02, 0.84, 0.96))))
    return C.clean_alpha(cut), "grabCut"


def speckle(g):
    """统一走 lowcolor 的向量化版本（同一口径，避免两处算法漂移）"""
    return L.speckle_vec(g)


# ---------------- 品牌色板吸附 ----------------
def save_ledger(out, rows, name="台账数据_高保真.json"):
    """写台账前先备份，防止一次误操作把历史记录冲掉"""
    import time as _t
    path = os.path.join(out, name)
    if os.path.exists(path):
        bak = dp(out, "台账备份")
        os.makedirs(bak, exist_ok=True)
        try:
            n = len(json.load(open(path, encoding="utf-8")))
            shutil.copy2(path, os.path.join(bak, f"{_t.strftime('%Y%m%d_%H%M%S')}_{n}条_{name}"))
            # 只留最近 20 份
            olds = sorted(os.listdir(bak))[:-20]
            for f in olds:
                try:
                    os.remove(os.path.join(bak, f))
                except Exception:
                    pass
        except Exception:
            pass
    json.dump(rows, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def _fit_exact(im, cols, rows):
    """把图裁成精确的 cols:rows 比例，保证出来的格数一个不差"""
    from PIL import Image as _I
    tw, th = cols, rows
    w, h = im.size
    if w * th > h * tw:                 # 太宽，裁两边
        nw = int(h * tw / th)
        x = (w - nw) // 2
        return im.crop((x, 0, x + nw, h))
    nh = int(w * th / tw)               # 太高，裁上下
    y = (h - nh) // 2
    return im.crop((0, y, w, y + nh))


def _simplify(g, p, ref):
    """合并近似色：在还原度还够的前提下把色号压到最少"""
    oc = CFG.get("output") or {}
    if not oc.get("single", False):
        return g, p, None
    try:
        g2, p2, info = SIMP.reduce_palette(
            g, p, ref,
            floor=float(oc.get("fidelity_floor", 0.965)),
            min_colors=int(oc.get("min_colors", 4)),
            max_delta=float(oc.get("max_delta", 10.0)))
        return g2, p2, info
    except Exception as e:
        print(f"  ! 合并色号失败（{e}），保留原调色板")
        return g, p, None


def _snap(g, p):
    """把自编色号吸附到品牌色板（MARD 等），拿不到就原样返回"""
    pc = CFG.get("palette", {})
    if not pc.get("enabled", False):
        return g, p
    try:
        return PAL.snap(g, p, pc.get("name", "mard"))
    except Exception as e:
        print(f"  ! 色板吸附失败（{e}），保留原色号")
        return g, p


# ---------------- 出图 ----------------
def _save_all(d, dn, name, cut, g, p, scene, cell=12, idx=None, cat=None):
    """社媒版：一套四张（发笔记用）；交付版：色号图 + 成品图

    d   = 社媒版目录
    dn  = 交付版下这一件的目录
    idx = 编号
    """
    pre = f"{idx:02d}_" if idx is not None else ""
    sd = os.path.join(d, cat or "", f"{pre}{name}")   # 社媒版/<分类>/<作品>/
    dn = os.path.join(os.path.dirname(dn), cat or "", os.path.basename(dn)) if cat else dn
    os.makedirs(sd, exist_ok=True)
    os.makedirs(dn, exist_ok=True)

    card = BR.render_card if scene else FC.float_card

    # 社媒版四张：原图 → 成品图 → 色号图 → 对比图
    M.to_card(cut).save(os.path.join(sd, "01_原图.png"), optimize=True)
    card(g, p).save(os.path.join(sd, "02_成品图.png"), optimize=True)
    BR.render_chart(g, p, name).save(os.path.join(sd, "03_色号图.png"), optimize=True)
    BR.render_compare(cut, BR.mosaic(g, p, cell), name).save(os.path.join(sd, "04_对比图.png"), optimize=True)

    # 交付版：色号图（无标）+ 成品图（无标）
    BR.render_chart(g, p, name, mark=False).save(os.path.join(dn, "色号图.png"), optimize=True)
    im = card(g, p, mark=False).convert("RGB")
    im.thumbnail((1400, 1400), Image.LANCZOS)
    im.save(os.path.join(dn, "成品图.jpg"), quality=92, optimize=True)


def do_high(cut, name, idx, scene, out, lineart=False):
    if lineart:
        c = HI_LADDER[-1] if max(cut.size) >= 900 else HI_LADDER[-2]
        _rf = int((CFG.get("grid") or {}).get("rows") or 0)
        _b = _fit_exact(cut, c, _rf) if _rf else cut
        small = _b.resize((c*3, max(3, int(_b.height*c*3/_b.width))), Image.LANCZOS)
        g, p = L.beadify_line(C.on_white(small), c, levels=4)
        g = np.where(FC.grid_alpha(small, c) > 0.35, g, -1) if small.mode == "RGBA" else g
        g, p = _snap(g, p)
        g, p, _info = _simplify(g, p, C.on_white(small))
        cat = CAT.classify(name, scene=scene, lineart=True)
        d = os.path.join(out, "社媒版")
        dn = os.path.join(out, "交付版", f"{idx:02d}_{name}")
        _save_all(d, dn, name, cut, g, p, scene, cell=12, idx=idx, cat=cat)
        NR, NC = g.shape
        return dict(no=idx, name=name, cols=int(NC), rows=int(NR),
                    beads=int((g >= 0).sum()), colors=len(p),
                    fidelity=0.99, path=d, thumb=os.path.join(d, "01_原图.png")), p
    best = None
    _fix = int((CFG.get("grid") or {}).get("cols") or 0)
    _ladder = [_fix] if _fix else [x for x in HI_LADDER if x <= MAX_COLS] or [MAX_COLS]
    for c in _ladder:
        _rf = int((CFG.get("grid") or {}).get("rows") or 0)
        _b = _fit_exact(cut, c, _rf) if _rf else cut
        small = _b.resize((c*3, max(3, int(_b.height*c*3/_b.width))), Image.LANCZOS)
        white = C.on_white(small)
        g, p = FG.beadify_fast(white, c, K=int(min(64, 20 + c/5)))
        if small.mode == "RGBA":
            g = np.where(FC.grid_alpha(small, c) > 0.35, g, -1)
        wi = min(range(len(p)), key=lambda k: sum(abs(int(p[k][1][j:j+2], 16)-255) for j in (1, 3, 5)))
        s = float(F.score(white, np.where(g >= 0, g, wi), p, blur=3))
        if best is None or s > best["score"]:
            best = dict(cols=c, grid=g, pal=p, score=s)
        if s >= P.get("prune_fidelity", 0.975):   # 已经够好，不再往上试
            break
    g, p = best["grid"], best["pal"]
    g, p = _snap(g, p)
    g, p, _info = _simplify(g, p, C.on_white(small))
    if _info:
        print(f"      色号 {_info['before']} → {_info['after']}"
              f"（还原 {_info['fidelity_before']:.4f} → {_info['fidelity']:.4f}）")
    cat = CAT.classify(name, scene=scene, lineart=lineart)
    d = os.path.join(out, "社媒版")
    dn = os.path.join(out, "交付版", f"{idx:02d}_{name}")
    _save_all(d, dn, name, cut, g, p, scene, cell=12, idx=idx, cat=cat)
    NR, NC = g.shape
    return dict(no=idx, name=name, cols=int(NC), rows=int(NR),
                beads=int((g >= 0).sum()), colors=len(p),
                fidelity=round(best["score"], 4), path=d,
                thumb=os.path.join(d, "01_原图.png")), p


def do_premium(cut, name, idx, scene, out, lineart=False):
    if lineart:
        c = 160 if max(cut.size) >= 900 else 128
        _rf = int((CFG.get("grid") or {}).get("rows") or 0)
        _b = _fit_exact(cut, c, _rf) if _rf else cut
        small = _b.resize((c*3, max(3, int(_b.height*c*3/_b.width))), Image.LANCZOS)
        g, p = L.beadify_line(C.on_white(small), c, levels=3)
        g = np.where(FC.grid_alpha(small, c) > 0.35, g, -1) if small.mode == "RGBA" else g
        g, p = _snap(g, p)
        d = os.path.join(out, "精品版", f"{idx:02d}_{name}")
        dn = os.path.join(out, "精品版", "无LOGO版", f"{idx:02d}_{name}")
        _save_all(d, dn, name, cut, g, p, scene, cell=14)
        for q in (os.path.join(d, "01_原图.png"), os.path.join(dn, "01_原图_无标.png")):
            if os.path.exists(q):
                os.remove(q)
        NR, NC = g.shape
        return dict(no=idx, name=name, cols=int(NC), rows=int(NR),
                    beads=int((g >= 0).sum()), colors=len(p),
                    fidelity=0.97, speckle=0.0), p
    best = None
    for cols in LOW_COLS:
        for K in LOW_K:
            small = cut.resize((cols*3, max(3, int(cut.height*cols*3/cut.width))), Image.LANCZOS)
            g, p = L.beadify_low(small, cols, K)
            if small.mode == "RGBA":
                g = np.where(FC.grid_alpha(small, cols) > 0.35, g, -1)
            wi = min(range(len(p)), key=lambda k: sum(abs(int(p[k][1][j:j+2], 16)-255) for j in (1, 3, 5)))
            sc = float(F.score(C.on_white(small), np.where(g >= 0, g, wi), p, blur=3))
            sp = speckle(g)
            if sp <= SPECKLE_MAX and sc >= FID_MIN:
                best = dict(cols=cols, grid=g, pal=p, score=sc, sp=sp)
                break
        if best:
            break
    if not best:
        return None
    g, p = best["grid"], best["pal"]
    g, p = _snap(g, p)
    d = os.path.join(out, "精品版", f"{idx:02d}_{name}")
    dn = os.path.join(out, "精品版", "无LOGO版", f"{idx:02d}_{name}")
    _save_all(d, dn, name, cut, g, p, scene, cell=14)
    for q in (os.path.join(d, "01_原图.png"), os.path.join(dn, "01_原图_无标.png")):
        if os.path.exists(q):
            os.remove(q)
    NR, NC = g.shape
    return dict(no=idx, name=name, cols=int(NC), rows=int(NR),
                beads=int((g >= 0).sum()), colors=len(p),
                fidelity=round(best["score"], 4), speckle=round(best["sp"], 3)), p


def process_one(task):
    """worker：处理单张，返回 (row, prem, pal, info)。异常在内部捕获。"""
    path, name, idx, out, bead_mm, no_premium, force_scene = task
    try:
        im, notes = X.preprocess(path)
        scene = True if force_scene else is_scene(im)
        lineart = L.is_lineart(im) and not force_scene
        cut, how = (im.convert("RGBA"), "场景") if scene else auto_cut(im)
        if lineart:
            how = "线稿"
        qscore, qnotes, qcov = C.quality(cut) if not scene else (100, [], 1.0)
        r, pal = do_high(cut, name, idx, scene, out, lineart)
        r["cut_score"] = qscore
        r["cut_notes"] = qnotes
        r["cut_cov"] = qcov
        r["cat"] = CAT.classify(name, scene=scene, lineart=lineart)
        r["file"] = os.path.basename(path)
        r["bead_mm"] = bead_mm
        r["cm"] = round(r["cols"] * bead_mm / 10, 1)
        r["notes"] = notes
        single = (CFG.get("output") or {}).get("single", False)
        q = None if (no_premium or single) else do_premium(cut, name, idx, scene, out, lineart)
        if q:
            q = q[0]
        r["grade"] = X.grade(r["fidelity"], q["speckle"] if q else 0.0, r["colors"])
        return r, q, pal, dict(scene=scene, how=how, notes=notes, err=None)
    except Exception as e:
        return None, None, None, dict(err=f"{e}", tb=traceback.format_exc(limit=2))


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser(description="拼豆图纸一键出图")
    ap.add_argument("--src", default=CFG["paths"]["src"])
    ap.add_argument("--out", default=CFG["paths"]["out"])
    ap.add_argument("--name", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default=None)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--no-premium", action="store_true")
    ap.add_argument("--pdf", action="store_true", help="顺带出 A4 打印分页 PDF")
    ap.add_argument("--bead-mm", type=float, default=None)
    ap.add_argument("--jobs", type=int, default=0, help="并行数，默认按 CPU 自动")
    ap.add_argument("--force", action="store_true", help="重复图也照做")
    ap.add_argument("--scene-all", action="store_true", help="全部按场景处理（整幅做豆板，不抠图）")
    ap.add_argument("--no-cat", action="store_true", help="不自动分类（保持平铺）")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--version", action="version", version="pindou-pattern 2.0")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    ap.add_argument("--check", action="store_true", help="全量体检已有产物，不出图")
    a = ap.parse_args()

    # 磁盘空间检查（小于 500MB 直接劝退）
    try:
        import shutil as _sh
        free = _sh.disk_usage(os.path.abspath(a.out) if os.path.isdir(a.out) else os.path.dirname(os.path.abspath(a.out))).free
        if free < 500 * 1024 * 1024:
            print(f"!! 磁盘只剩 {free/1048576:.0f} MB，可能不够出图。先清理再跑。")
    except Exception:
        pass

    # 品牌没改就警告——不然图上会印着别人的名字
    _bn = CFG["brand"]["name"]
    if _bn in ("你的品牌名", "我的品牌", "") or _bn.startswith("你的"):
        print("=" * 62)
        print("⚠️  还没设置你的品牌名")
        print(f"   现在出的图会印「{CFG['brand'].get('watermark')}」")
        print("   改 config.json 里的 brand.name 和 brand.watermark，再重跑")
        print("=" * 62)
        print()

    bead_mm = a.bead_mm or CFG["bead"]["diameter_mm"]
    out = a.out
    os.makedirs(out, exist_ok=True)
    rows_json = dp(out, "台账数据_高保真.json")
    prem_json = dp(out, "台账数据_精品版.json")
    rows = json.load(open(rows_json, encoding="utf-8")) if os.path.exists(rows_json) else []
    prem = json.load(open(prem_json, encoding="utf-8")) if os.path.exists(prem_json) else []

    if a.check:
        return run_check(out, rows, prem)

    log = logging.getLogger("pindou")
    log.setLevel(logging.INFO)
    if not log.handlers:
        fh = logging.FileHandler(dp(out, "运行日志.txt"), encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(fh)

    done = {r.get("file") for r in rows}
    files = [p for p in sorted(glob.glob(os.path.join(a.src, "*"))) if p.lower().endswith(EXTS)]
    todo = [p for p in files if os.path.basename(p) not in done]
    if a.only:
        want = {x.strip() for x in a.only.split(",")}
        todo = [p for p in todo if os.path.splitext(os.path.basename(p))[0] in want]
    if a.limit:
        todo = todo[:a.limit]

    if not a.quiet:
        print(f"素材 {len(files)} 张 | 已做 {len(done)} 张 | 待处理 {len(todo)} 张")
    if not todo:
        if not a.quiet:
            print("没有新图。")
        return 0

    # 查重
    known = [(r["name"], X.ahash(Image.open(r["thumb"]))) for r in rows
             if os.path.exists(r.get("thumb", ""))]
    dupes = []
    if not a.force:
        keep = []
        for p in todo:
            try:
                im0, _ = X.preprocess(p)
                who, dist = X.find_dup(im0, known)
            except Exception:
                who, dist = None, 0
            if who:
                dupes.append((os.path.basename(p), who, dist))
                log.info("跳过重复：%s ≈ %s (距离%d)", os.path.basename(p), who, dist)
            else:
                keep.append(p)
        todo = keep
        if dupes and not a.quiet:
            print(f"检测到 {len(dupes)} 张重复，已跳过（--force 可强制做）")
            for f, w, d in dupes[:5]:
                print(f"  {f} ≈ {w}")

    if not todo:
        if not a.quiet:
            print("没有需要处理的图。")
        return 0

    if not a.quiet:
        print()
    ok, fail = [], []
    t0 = time.time()
    jobs = a.jobs or min(4, (os.cpu_count() or 2))
    tasks = []
    for p in todo:
        name = a.name if (a.name and len(todo) == 1) else X.safe_name(os.path.splitext(os.path.basename(p))[0])
        idx = max([r["no"] for r in rows], default=0) + len(tasks) + 1
        tasks.append((p, name, idx, out, bead_mm, a.no_premium, a.scene_all))

    if a.dry:
        for p, name, idx, *_ in tasks:
            im, notes = X.preprocess(p)
            scene = is_scene(im)
            how = "场景" if scene else ("透明底" if "透明底" in notes else "待抠")
            if not a.quiet:
                print(f"[{idx:02d}] {name}  {im.size}  场景={scene}  预处理={notes or '—'}  (dry)")
        return 0

    def handle(res, task):
        r, q, pal, info = res
        if info.get("err"):
            fail.append((task[1], info["err"]))
            log.error("失败 %s: %s", task[1], info["err"])
            if not a.quiet:
                print(f"[{task[2]:02d}] {task[1]}  失败：{info['err']}")
            return
        rows.append(r)
        if q:
            prem[:] = [x for x in prem if x["no"] != r["no"]] + [q]
        ok.append((r, q, pal, info))
        log.info("完成 %s %sx%s %s色 %s颗 还原%.1f%% 评级%s",
                 r["name"], r["cols"], r["rows"], r["colors"], r["beads"],
                 r["fidelity"]*100, r["grade"])
        if not a.quiet:
            tail = f"  精品 {q['colors']}色/{q['beads']}颗" if q else "  精品 压不下"
            print(f"[{r['no']:02d}] {r['name']}  {info['how']}  评级{r['grade']}")
            print(f"      高保真 {r['cols']}×{r['rows']} {r['colors']}色 {r['beads']}颗 "
                  f"还原{r['fidelity']*100:.1f}% 约{r['cm']}cm{tail}")

    if jobs <= 1 or len(tasks) == 1:
        for t in tasks:
            handle(process_one(t), t)
    else:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            futs = {ex.submit(process_one, t): t for t in tasks}
            for fu in as_completed(futs):
                handle(fu.result(), futs[fu])

    rows.sort(key=lambda x: x["no"]); prem.sort(key=lambda x: x["no"])
    json.dump(rows, open(rows_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(prem, open(prem_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # PDF 分页
    pdfs = []
    if a.pdf:
        for r, q, pal, info in ok:
            try:
                src = os.path.join(r["path"], "03_色彩图.png")
                dst = os.path.join(r["path"], "05_打印版A4.pdf")
                _, n = X.chart_to_pdf(src, dst)
                pdfs.append((r["name"], n))
            except Exception as e:
                log.error("PDF 失败 %s: %s", r["name"], e)

    # 台账（带缩略图，按分类分 sheet）
    try:
        LEDGER.build(out)
    except Exception as e:
        log.error("台账失败: %s", e)
        if not a.quiet:
            print(f"  !! 台账生成失败：{e}")

    # 清理重复的原图
    import subprocess
    rr = subprocess.run([sys.executable, os.path.join(HERE, "cleanup.py")],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if rr.returncode != 0 and not a.quiet:
        print(f"  !! cleanup 失败：{(rr.stderr or '')[-200:]}")

    dt = time.time() - t0

    if fail:
        bad = os.path.join(out, "内部数据", "失败记录.txt")
        os.makedirs(os.path.dirname(bad), exist_ok=True)
        with open(bad, "w", encoding="utf-8") as f:
            for n, e in fail:
                f.write(f"{n}: {e}\n")


    if not a.quiet:
        print(f"\n完成 {len(ok)} 件，失败 {len(fail)} 件，跳过重复 {len(dupes)} 件，用时 {dt:.0f} 秒")
        print(f"清单：{os.path.join(out, '作品清单.xlsx')}")
        print(f"社媒版：{os.path.join(out, '社媒版')}")
        print(f"交付版：{os.path.join(out, '交付版')}")
    return 0 if not fail else 2


def run_check(out, rows, prem):
    """全量体检：文件齐全 / 尺寸对 / 图纸格子够大 / 有评级"""
    import json as _j
    bad = []
    for r in rows:
        d = os.path.join(out, f'{r["no"]:02d}_{r["name"]}')
        for f in ("01_原图.png", "02_成品图.png", "03_色彩图.png", "04_对比图.png"):
            p = os.path.join(d, f)
            if not os.path.exists(p):
                bad.append(f'{r["name"]}: 缺 {f}')
            elif os.path.getsize(p) < 5000:
                bad.append(f'{r["name"]}: {f} 过小')
        ch = os.path.join(d, "03_色彩图.png")
        if os.path.exists(ch):
            w, _ = Image.open(ch).size
            cell = (w - 192) / max(r["cols"], 1)
            if cell < 19.5:
                bad.append(f'{r["name"]}: 图纸格子 {cell:.0f}px < 20，色号可能看不清')
        if not r.get("grade"):
            bad.append(f'{r["name"]}: 缺评级')
    print(f"体检 {len(rows)} 件，问题 {len(bad)} 处")
    for b in bad[:20]:
        print("  !", b)
    if not bad:
        print("✓ 全部通过")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
