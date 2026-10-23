# -*- coding: utf-8 -*-
"""config.py —— 所有可配置项集中在这里，不再改代码

优先级：环境变量 > 技能目录下的 config.json > 内置默认值

用法：
    from config import CFG
    CFG["brand"]["name"]      # 品牌名
    CFG["paths"]["out"]       # 输出目录（已展开 ~）
"""
import json, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
CONFIG_PATH = Path(os.environ.get("PINDOU_CONFIG", SKILL_DIR / "config.json"))

DEFAULTS = {
    "brand": {
        "name": "你的品牌名",
        "en": "YOUR BRAND",
        "color": "#C6705C",
        "watermark": "@你的品牌名",
        "footer": True
    },
    "paths": {
        "src": "~/Downloads/拼豆素材",
        "out": "~/Downloads/拼豆成品"
    },
    "bead": {
        "diameter_mm": 5.0
    },
    "render": {
        "card_w": 1080,
        "card_h": 1440,
        "chart_min_cell": 20,
        "chart_max_cell": 26,
        "shadow_strength": 0.34,
        "paper_style": "linen",
        "wm_angle": 28,
        "wm_alpha": 155,
        "wm_ratio": 15,
        "badge_cm": True
    },
    "pipeline": {
        "hi_cols": [128, 160, 192, 224, 256],
        "lo_cols": [96, 112, 128, 160],
        "lo_k": [10, 12, 14, 16, 20, 24],
        "speckle_max": 0.048,
        "fidelity_min": 0.90,
        "scene_flat_ratio": 0.40,
        "vivid": 0.20,
        "outline_lum": 0.32,
        "outline_ratio": 0.38,
        "feather": 1.6,
        "prune_fidelity": 0.975,
        "preprocess_max": 2400
    },
    "excel": {"price": True, "grade": True, "csv": True, "auto_width": True}
}


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path=None):
    cfg = json.loads(json.dumps(DEFAULTS))
    p = Path(path) if path else CONFIG_PATH
    if p.exists():
        try:
            cfg = _merge(cfg, json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[config] 读取 {p} 失败，用默认值：{e}")
    # 个人配置：config.local.json 覆盖 config.json（已在 .gitignore 里）
    local = p.parent / "config.local.json"
    if local.exists():
        try:
            cfg = _merge(cfg, json.loads(local.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[config] 读取 {local} 失败：{e}")
    # 环境变量覆盖（适合 CI / 临时改）
    for env, keys in (("PINDOU_SRC", ("paths", "src")),
                      ("PINDOU_OUT", ("paths", "out")),
                      ("PINDOU_BRAND", ("brand", "name"))):
        v = os.environ.get(env)
        if v:
            cfg[keys[0]][keys[1]] = v
    # 展开 ~
    for k in ("src", "out"):
        cfg["paths"][k] = str(Path(cfg["paths"][k]).expanduser())
    if cfg["brand"].get("watermark") in (None, ""):
        cfg["brand"]["watermark"] = "@" + cfg["brand"]["name"]
    return cfg


def validate(cfg):
    """配置体检：类型/范围不对就纠正并警告，不让脏配置跑坏一整批"""
    warns = []
    b = cfg["brand"]
    if not isinstance(b.get("name"), str) or not b["name"].strip():
        b["name"] = "我的品牌"; warns.append("brand.name 为空，用默认值")
    c = str(b.get("color", "")).lstrip("#")
    if len(c) != 6:
        b["color"] = "#C6705C"; warns.append("brand.color 格式不对（要 #RRGGBB），用默认色")
    try:
        mm = float(cfg["bead"]["diameter_mm"])
        if not (1.0 <= mm <= 10.0):
            raise ValueError
    except Exception:
        cfg["bead"]["diameter_mm"] = 5.0; warns.append("bead.diameter_mm 不在 1-10，用 5.0")
    for k in ("card_w", "card_h"):
        v = cfg["render"].get(k)
        if not isinstance(v, int) or v < 400:
            cfg["render"][k] = 1080 if k == "card_w" else 1440
            warns.append(f"render.{k} 不合理，用默认")
    pl = cfg["pipeline"]
    for k in ("speckle_max", "fidelity_min", "scene_flat_ratio"):
        v = pl.get(k)
        if not isinstance(v, (int, float)) or not (0 < v < 1):
            pl[k] = DEFAULTS["pipeline"][k]; warns.append(f"pipeline.{k} 不在 0-1，用默认")
    for k in ("hi_cols", "lo_cols", "lo_k"):
        v = pl.get(k)
        if not isinstance(v, list) or not v or not all(isinstance(x, int) and x > 0 for x in v):
            pl[k] = DEFAULTS["pipeline"][k]; warns.append(f"pipeline.{k} 不是正整数列表，用默认")
    return cfg, warns


CFG, _warns = validate(load())
if _warns and os.environ.get("PINDOU_VERBOSE"):
    for w in _warns:
        print(f"[config] {w}")

if __name__ == "__main__":
    print(json.dumps(CFG, ensure_ascii=False, indent=2))
    print("\n配置文件：", CONFIG_PATH, "存在" if CONFIG_PATH.exists() else "不存在（用默认值）")
