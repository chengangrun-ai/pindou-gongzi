# -*- coding: utf-8 -*-
"""doctor.py —— 装完先跑这个，检查环境能不能用

    python doctor.py
"""
import os, sys, platform
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OK, WARN, BAD = "✓", "!", "✗"
issues = []


def line(sym, label, msg=""):
    print(f"  {sym} {label:22s} {msg}")


def main():
    print(f"\n环境检查  |  {platform.system()} {platform.release()}  |  Python {sys.version.split()[0]}\n")

    # 1) 依赖
    print("依赖包：")
    need = {"PIL": "pillow", "numpy": "numpy", "scipy": "scipy", "openpyxl": "openpyxl", "cv2": "opencv-python-headless"}
    missing = []
    for mod, pkg in need.items():
        try:
            __import__(mod)
            line(OK, mod)
        except Exception:
            line(BAD, mod, f"缺 → pip install {pkg}")
            missing.append(pkg)
    if missing:
        issues.append("缺依赖：" + " ".join(missing))

    # 2) 字体
    print("\n中文字体：")
    import brand
    if brand.FONT and os.path.exists(brand.FONT):
        line(OK, "常规体", os.path.basename(brand.FONT))
    else:
        line(BAD, "常规体", "没找到，中文会变方块 → 设环境变量 PINDOU_FONT=<字体路径>")
        issues.append("缺中文字体")
    if brand.FONTB and os.path.exists(brand.FONTB):
        line(OK, "粗体", os.path.basename(brand.FONTB))
    else:
        line(WARN, "粗体", "用常规体代替")

    # 3) 路径
    print("\n路径：")
    from config import CFG, CONFIG_PATH
    line(OK if CONFIG_PATH.exists() else WARN, "config.json",
         str(CONFIG_PATH) if CONFIG_PATH.exists() else "不存在（用默认值）")
    src, out = CFG["paths"]["src"], CFG["paths"]["out"]
    line(OK if os.path.isdir(src) else WARN, "素材目录", src + ("" if os.path.isdir(src) else "  （还没建，会自动创建）"))
    line(OK if os.path.isdir(out) else WARN, "输出目录", out + ("" if os.path.isdir(out) else "  （还没建，会自动创建）"))
    try:
        os.makedirs(out, exist_ok=True)
        t = os.path.join(out, ".__w")
        open(t, "w").close(); os.remove(t)
        line(OK, "可写", "")
    except Exception as e:
        line(BAD, "可写", str(e))
        issues.append("输出目录不可写")

    # 4) 品牌
    print("\n品牌：")
    b = CFG["brand"]
    line(OK, "名称", b["name"])
    line(OK, "水印", b.get("watermark") or "@" + b["name"])
    line(OK, "豆径", f'{CFG["bead"]["diameter_mm"]} mm')

    # 5) 模块自检
    print("\n模块：")
    for m in ("config", "brand", "cutout", "lowcolor", "fastgrid", "fidelity", "floatcard", "beadify"):
        try:
            __import__(m)
            line(OK, m)
        except Exception as e:
            line(BAD, m, str(e)[:60])
            issues.append(f"模块 {m} 导入失败")

    print()
    if issues:
        print("发现问题：")
        for i in issues:
            print("  -", i)
        print("\n修好后再跑一次 doctor.py")
        return 1
    print("全部通过。下一步：python selftest.py（出一张测试图，验证全流程）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
