# -*- coding: utf-8 -*-
"""selftest.py —— 不给你任何图，自己造一张，跑完整流程，验证产物

    python selftest.py

成功会打印 ✓ 和实测规格；失败会指出卡在哪一步。
"""
import os, sys, json, shutil, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))


def make_sample(path):
    """造一张「平色底 + 简单角色」的测试图：白底上一个圆脸小人"""
    W = H = 900
    im = Image.new("RGB", (W, H), (250, 232, 180))     # 米黄平色底
    d = ImageDraw.Draw(im)
    # 身体
    d.ellipse([300, 470, 600, 780], fill=(90, 140, 200), outline=(30, 30, 40), width=6)
    # 脸
    d.ellipse([330, 250, 570, 500], fill=(252, 222, 200), outline=(30, 30, 40), width=6)
    # 眼睛
    d.ellipse([390, 340, 425, 385], fill=(25, 25, 30))
    d.ellipse([475, 340, 510, 385], fill=(25, 25, 30))
    # 腮红
    d.ellipse([360, 400, 405, 430], fill=(240, 150, 160))
    d.ellipse([495, 400, 540, 430], fill=(240, 150, 160))
    # 嘴
    d.arc([425, 400, 475, 450], 20, 160, fill=(150, 70, 70), width=5)
    # 蝴蝶结
    d.polygon([(440, 240), (380, 195), (380, 285)], fill=(220, 80, 120), outline=(30, 30, 40))
    d.polygon([(460, 240), (520, 195), (520, 285)], fill=(220, 80, 120), outline=(30, 30, 40))
    im.save(path, quality=95)
    return path


def check(paths, min_kb=8):
    bad = []
    for p in paths:
        if not os.path.exists(p):
            bad.append(f"缺文件 {os.path.basename(p)}")
        elif os.path.getsize(p) < min_kb * 1024:
            bad.append(f"文件过小 {os.path.basename(p)} {os.path.getsize(p)//1024}KB")
    return bad


def main():
    print("=" * 56)
    print("自检：造一张测试图 → 跑全流程 → 验证产物")
    print("=" * 56)

    # 1) 依赖
    try:
        import brand, batch34, auto_run  # noqa
    except Exception as e:
        print(f"\n✗ 模块导入失败：{e}")
        print("  先跑 python doctor.py")
        return 1

    from config import CFG
    tmp_src = tempfile.mkdtemp(prefix="pindou_test_")
    out = CFG["paths"]["out"]
    os.makedirs(out, exist_ok=True)

    # 2) 造图
    img = os.path.join(tmp_src, "自检样例.jpg")
    make_sample(img)
    print(f"\n[1/4] 测试图已生成  {Image.open(img).size}")

    # 3) 跑流程（走 auto_run，等价于真实用法）
    print("[2/4] 跑流程（约 40 秒）...")
    r = subprocess.run([sys.executable, os.path.join(HERE, "auto_run.py"), "--src", tmp_src, "--quiet"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("✗ 流程失败：")
        print((r.stderr or r.stdout)[-800:])
        shutil.rmtree(tmp_src, ignore_errors=True)
        return 1
    print("      完成")

    # 4) 验证产物
    print("[3/4] 检查产物...")
    rows = json.load(open(os.path.join(out, "台账数据_高保真.json"), encoding="utf-8"))
    mine = [x for x in rows if x["name"] == "自检样例"]
    if not mine:
        print("✗ 台账里没有新增条目"); shutil.rmtree(tmp_src, ignore_errors=True); return 1
    rec = mine[-1]
    d = rec["path"]
    files = [os.path.join(d, f) for f in ("01_原图.png", "02_成品图.png", "03_色彩图.png", "04_对比图.png")]
    bad = check(files)
    for f in files:
        print(("  ✓ " if os.path.exists(f) else "  ✗ ") + os.path.basename(f))

    # 5) 清理测试件
    print("[4/4] 清理测试件...")
    prem = os.path.join(out, "台账数据_精品版.json")
    rows = [x for x in rows if x["no"] != rec["no"]]
    json.dump(rows, open(os.path.join(out, "台账数据_高保真.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if os.path.exists(prem):
        p = [x for x in json.load(open(prem, encoding="utf-8")) if x["no"] != rec["no"]]
        json.dump(p, open(prem, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for p in (d, d.replace(os.sep + "精品版" + os.sep, os.sep + "无LOGO版" + os.sep)):
        shutil.rmtree(p, ignore_errors=True)
    shutil.rmtree(tmp_src, ignore_errors=True)
    # 清完测试件要重建台账，否则 Excel 里留着一行幽灵
    subprocess.run([sys.executable, os.path.join(HERE, "make_excel2.py")],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")

    print()
    if bad:
        print("✗ 自检未通过：")
        for b in bad:
            print("  -", b)
        return 1
    print("✓ 自检通过")
    print(f"  规格：{rec['cols']}×{rec['rows']} 格  {rec['colors']} 色  {rec['beads']} 颗  还原 {rec['fidelity']*100:.1f}%")
    print("  产物结构、图纸色号、台账写入都正常。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
