# -*- coding: utf-8 -*-
"""categorize.py —— 按风格自动分类

规则按优先级：
1. config.json 的 categories.rules 里配置的关键词（名字命中即归）
2. 线稿 → 墨纹
3. 场景 → 风景
4. 其余 → 动漫人物

新增分类只改 config.json，不动代码。
"""
import json
import os

from config import CFG

DEFAULTS = {
    "order": ["动漫人物", "风景", "墨纹"],
    "fallback": "动漫人物",
    "rules": {
        "动漫人物": ["Q版", "Kitty", "kitty", "路飞", "索隆", "山治", "乔巴", "艾斯",
                    "猫猫", "人物", "角色", "头像", "宝宝", "小妹"],
        "墨纹": ["飞龙", "章鱼", "曼陀罗", "阴阳", "狼头", "浪", "锦鲤", "星球",
                 "死神", "蛛网", "面具", "虎纹", "羽毛", "火焰", "龙", "弓箭",
                 "狮", "水母", "时钟", "星际"],
        "风景": ["光之树", "云下", "云端", "云", "山丘", "山峰", "浪尖", "红裙", "雨夜", "雨窗", "花海", "绿野",
                 "落雪", "车流", "麦田", "树下", "树荫", "咖啡", "白墙", "奔跑",
                 "阶梯", "蕉叶", "花田", "冲浪", "白车", "红车", "晾衣", "洗衣",
                 "赶羊", "仙人掌", "水鸟", "条纹", "树屋"],
    },
}


def _rules():
    c = CFG.get("categories") or {}
    return {
        "order": c.get("order", DEFAULTS["order"]),
        "fallback": c.get("fallback", DEFAULTS["fallback"]),
        "rules": {**DEFAULTS["rules"], **(c.get("rules") or {})},
    }


def by_name(name):
    """只看名字，返回命中的分类或 None

    单词关键词（如「浪」「山」）只做完全匹配，避免「冲浪」「山治」被误伤；
    多字关键词才做包含匹配。
    """
    r = _rules()
    # 先精确匹配（名字本身就是一个关键词）
    for cat, words in r["rules"].items():
        if name in words:
            return cat
    for cat, words in r["rules"].items():
        if any(len(w) >= 2 and w in name for w in words):
            return cat
    return None


def classify(name, scene=False, lineart=False):
    """综合判定：名字优先，其次看图像特征"""
    hit = by_name(name)
    if hit:
        return hit
    if lineart:
        return "墨纹"
    if scene:
        return "风景"
    return _rules()["fallback"]


def order_of(cat):
    o = _rules()["order"]
    return o.index(cat) if cat in o else len(o)


def organize(out_dir, rows, dry=False):
    """把 out_dir 下的 NN_名字 目录移动到 分类/<分类>/ 下

    rows: 台账（dict 列表），会用 r["cat"] 决定目标目录；缺 cat 就现算
    """
    moved = []
    for r in rows:
        cat = r.get("cat") or classify(r["name"])
        r["cat"] = cat
        src = os.path.join(out_dir, f'{r["no"]:02d}_{r["name"]}')
        if not os.path.isdir(src):
            continue
        dst_dir = os.path.join(out_dir, "分类", cat)
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, os.path.basename(src))
        if dry:
            moved.append((src, dst))
            continue
        if not os.path.exists(dst):
            import shutil
            shutil.move(src, dst)
            moved.append((src, dst))
    return moved


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    r = _rules()
    print("分类顺序:", " → ".join(r["order"]))
    print("兜底:", r["fallback"])
    for cat, words in r["rules"].items():
        print(f"  {cat}: {len(words)} 个关键词  {words[:6]}…")
    for t in sys.argv[1:]:
        print(f"  「{t}」→ {classify(t)}")
