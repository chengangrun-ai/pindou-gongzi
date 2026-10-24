# -*- coding: utf-8 -*-
"""deliver.py —— 生成给客户的交付包

为什么不用 PNG：色号图 5000+ 像素宽，客户在手机上放大就糊，
从小红书/微信保存还会再压一次。PDF 放大不糊，打印也不糊。

每个作品产出：
    交付_色号图.pdf      A4 分页，带页码和对齐标记，打印后拼起来
    交付_成品图.jpg      无标成品图，发客户确认效果
    交付_说明.txt        怎么用、色号在哪看、买豆建议

用法：
    python scripts/deliver.py <作品目录>              # 单个
    python scripts/deliver.py --all                   # 全部（按分类）
    python scripts/deliver.py <目录> --zip            # 顺手打包 zip
"""
import argparse
import os
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PIL import Image

from config import CFG
import extras as X

NOTE = """【拼豆图纸使用说明】

一、先看色号图
   打开「交付_色号图.pdf」，这是完整图纸。
   每格写着色号（如 A23、R20），照着摆豆就行。
   图纸底部有色卡：每个色号对应多少颗、占比多少。

二、怎么放大看
   PDF 可以无限放大不糊。
   手机上用 PDF 阅读器（微信/夸克/系统自带都行），双指放大。

三、要打印的话
   PDF 已按 A4 分页，每页四角有对齐标记。
   打印出来按页码拼起来，重叠部分对齐即可。
   建议 A4 单面、实际大小（100%，不要选「适应页面」）。

四、买豆
   色卡上的色号是 {brand} 标准色号，直接照着色号买。
   每种色号多买 15% 备用（拼的时候会掉、会错）。

五、拼的时候
   从左上角开始，按行推进，别跳着拼。
   10 格有红线、5 格有虚线，用来定位。

原创图纸，商用需要授权，请勿二次传播。
"""


def _item_dirs(root):
    """支持传单个作品目录，或一个分类目录"""
    if os.path.exists(os.path.join(root, "03_色彩图.png")):
        return [root]
    out = []
    for d in sorted(os.listdir(root)):
        p = os.path.join(root, d)
        if os.path.isdir(p) and d[:2].isdigit() and os.path.exists(os.path.join(p, "03_色彩图.png")):
            out.append(p)
    return out


def pack(item, brand, do_zip=False):
    name = os.path.basename(item)
    out = os.path.join(item, "交付包")
    os.makedirs(out, exist_ok=True)
    made = []

    # 1) 色号图 → PDF
    chart = os.path.join(item, "03_色彩图.png")
    pdf = os.path.join(out, "交付_色号图.pdf")
    try:
        _, n = X.chart_to_pdf(chart, pdf)
        made.append(f"交付_色号图.pdf（{n} 页）")
    except Exception as e:
        print(f"  ! PDF 失败 {name}: {e}")

    # 2) 无标成品图
    for f in ("02_成品图.png", "02_成品图_无标.png"):
        p = os.path.join(item, f)
        if os.path.exists(p):
            im = Image.open(p).convert("RGB")
            im.thumbnail((1400, 1400), Image.LANCZOS)
            im.save(os.path.join(out, "交付_成品图.jpg"), quality=92, optimize=True)
            made.append("交付_成品图.jpg")
            break

    # 3) 说明
    with open(os.path.join(out, "交付_说明.txt"), "w", encoding="utf-8") as f:
        f.write(NOTE.format(brand=CFG.get("palette", {}).get("name", "MARD").upper()))
    made.append("交付_说明.txt")

    if do_zip:
        z = os.path.join(item, f"{name}_交付包.zip")
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(out):
                zf.write(os.path.join(out, f), f)
        made.append(f"{name}_交付包.zip")

    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="作品目录或分类目录")
    ap.add_argument("--all", action="store_true", help="处理 分类/ 下全部")
    ap.add_argument("--zip", action="store_true", help="每件单独打包 zip")
    ap.add_argument("--bundle", action="store_true",
                    help="按分类打成一个总包（推荐，网盘只传一个文件）")
    ap.add_argument("--out", default=CFG["paths"]["out"])
    a = ap.parse_args()

    brand = CFG.get("palette", {}).get("name", "mard")
    targets = []
    if a.all:
        base = os.path.join(a.out, "分类")
        for c in os.listdir(base) if os.path.isdir(base) else []:
            p = os.path.join(base, c)
            if os.path.isdir(p):
                targets += _item_dirs(p)
    elif a.path:
        targets = _item_dirs(a.path)
    else:
        print("给个目录，或者用 --all")
        return 1

    print(f"共 {len(targets)} 件")
    for t in targets:
        made = pack(t, brand, a.zip and not a.bundle)
        print(f"  ✓ {os.path.basename(t)}: {', '.join(made)}")

    if a.bundle:
        # 按分类打成一个总包：网盘只传一个文件
        from collections import defaultdict
        groups = defaultdict(list)
        for t in targets:
            cat = os.path.basename(os.path.dirname(t)) or "全部"
            groups[cat].append(t)
        for cat, items in groups.items():
            z = os.path.join(a.out, f"交付包_{cat}.zip")
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                for t in items:
                    pk = os.path.join(t, "交付包")
                    if not os.path.isdir(pk):
                        continue
                    for f in os.listdir(pk):
                        zf.write(os.path.join(pk, f),
                                 os.path.join(os.path.basename(t), f))
            mb = os.path.getsize(z) / 1048576
            print(f"  📦 交付包_{cat}.zip  {mb:.0f} MB  （{len(items)} 件）")

    print("\n完成。微信发「文件」也行，网盘传 zip 也行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
