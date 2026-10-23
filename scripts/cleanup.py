# -*- coding: utf-8 -*-
"""cleanup.py —— 每次更新完跑一遍：只留最新的，清掉临时和重复"""
import os, glob, hashlib, shutil

OUT = r"C:/Users/Administrator/Downloads/拼豆成品"
WORK = r"C:/Users/Administrator/WorkBuddy AI/2026-10-20-21-45-53"
freed = 0
log = []


def size(p):
    try:
        return os.path.getsize(p) if os.path.isfile(p) else 0
    except OSError:
        return 0


def rm(p, why):
    global freed
    if os.path.isdir(p):
        s = sum(size(os.path.join(r, f)) for r, _, fs in os.walk(p) for f in fs)
        shutil.rmtree(p, ignore_errors=True)
    elif os.path.exists(p):
        s = size(p); os.remove(p)
    else:
        return
    freed += s
    log.append(f"  - {why}  ({s/1048576:.1f} MB)")


# 1) 工作区临时图（测试 / 预览 / 对比草稿）
rm(os.path.join(WORK, "拼豆", "out"), "工作区 out/ 临时图")

# 2) 台账的旧版本
for p in glob.glob(os.path.join(OUT, "作品清单_新版.xlsx")):
    rm(p, "台账旧版本 作品清单_新版.xlsx")

# 3) 临时图（_ 开头的 png，_rows.json/_premium.json 要留）
for p in glob.glob(os.path.join(OUT, "_*.png")):
    rm(p, f"临时图 {os.path.basename(p)}")

# 4) 精品版里和主版完全重复的原图
def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()

for p in glob.glob(os.path.join(OUT, "精品版", "[0-9][0-9]_*", "01_原图.png")):
    main = p.replace(os.sep + "精品版", "")
    if os.path.exists(main) and md5(p) == md5(main):
        rm(p, f"重复原图 {os.path.basename(os.path.dirname(p))}")
for p in glob.glob(os.path.join(OUT, "精品版", "无LOGO版", "[0-9][0-9]_*", "01_原图_无标.png")):
    main = p.replace(os.sep + "精品版" + os.sep + "无LOGO版", os.sep + "无LOGO版")
    if os.path.exists(main) and md5(p) == md5(main):
        rm(p, f"重复无标原图 {os.path.basename(os.path.dirname(p))}")

# 5) 制作规范只留 Downloads 里那一份
rm(os.path.join(WORK, "拼豆", "制作规范.md"), "工作区重复的制作规范")

print("清理完成：")
print("\n".join(log) if log else "  （没有可清理的）")
print(f"\n共释放 {freed/1048576:.0f} MB")
print(f"当前 拼豆成品: {sum(size(os.path.join(r,f)) for r,_,fs in os.walk(OUT) for f in fs)/1073741824:.2f} GB")
