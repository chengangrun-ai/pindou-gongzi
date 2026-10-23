# 拼豆公子 · Pindou Gongzi

把任何图片变成能照着拼的拼豆图纸——四张成品图、带色号的图纸、可直接发布的文案台账，一条命令跑完。

不依赖任何特定平台。Python 3.9+，命令行。

## 📺 看看效果

[![拼豆公子 — 一张图变成四张成品图](screenshots/halloween-kitty-compare.png)](screenshots/halloween-kitty-compare.png)

> ▶️ **[看完整画廊 →](#gallery)** — 67 件真实作品，从纹身手稿到艺术摄影

## What This Does

丢一个文件夹进来，出来的是可以直接卖的整套素材。

### Key Features

- **四张成品图** — 原图 / 成品图 / 色彩图（带色号）/ 对比图，一次生成
- **双版本** — 带水印（发社交）+ 无标（卖客户）
- **双轨取色** — 高保真版（128–256 格）+ 精品版（3–17 色）
- **自动分流** — 角色浮空 / 场景豆板 / 线稿灰阶 / 照片分割，任何图都能处理
- **文案台账** — Excel 里标题、正文、标签直接复制，规格自动填
- **质量评级** — 每件自动打 A/B/C，不达标的低色号版直接不出

## Installation

### WorkBuddy

```bash
git clone https://github.com/<you>/pindou-gongzi.git ~/.workbuddy-ai/skills/pindou-gongzi
pip install -r ~/.workbuddy-ai/skills/pindou-gongzi/requirements.txt
```

### Claude Code / 其他 Agent

```bash
mkdir -p ~/.claude/skills/pindou-gongzi
cp -R SKILL.md README.md config.json requirements.txt scripts references screenshots \
      ~/.claude/skills/pindou-gongzi/
```

然后把仓库链接丢给 agent，它会按 `SKILL.md` 的指引加载所需文件。

### 手动验证

```bash
python scripts/doctor.py      # 依赖 / 字体 / 路径
python scripts/selftest.py    # 自造一张图跑通全流程
```

`selftest.py` 打印 `✓ 自检通过` 就说明环境没问题。

## Usage

### 批量出图

```bash
python scripts/auto_run.py --src ~/Downloads/拼豆素材
```

扫描目录 → 判断类型 → 抠图 → 双轨取色 → 四图输出 → 台账 → 清理 → 报告。

> 图片放进素材目录就行，文件名就是作品名。

### 先看看它怎么判断

```bash
python scripts/auto_run.py --dry
```

只打印每张图的分类和预处理动作，不出图。适合大批量前先确认。

### 其他常用

```bash
python scripts/auto_run.py --jobs 4          # 4 张并行
python scripts/auto_run.py --limit 3         # 先做 3 张试水
python scripts/auto_run.py --pdf             # 顺带出 A4 打印分页
python scripts/auto_run.py --check           # 已有产物体检
python scripts/wm_hint.py                    # 扫疑似水印位置
```

## 四种处理模式

任何图片进来，都会被分到其中一条路。

### 角色

抠图后浮空贴在亚麻纸上，投影跟着轮廓走。适合有明确主体的插画、动漫角色。

### 场景

整幅做成豆板，带厚度和投影，像拼好放在桌上。适合风景、街拍、艺术摄影。

### 线稿

4 档灰阶，每格取暗分位保住细线。适合纹身手稿、素描、漫画线稿、文档截图。

> 线稿模式是唯一能做到 4 色的路径——因为线稿本来就只有黑白。

### 照片

grabCut 前景分割 + 覆盖率自检，抠不干净自动换方法。适合真人、实拍。

## Gallery

### 万圣 Kitty

[![万圣Kitty 成品图](screenshots/halloween-kitty-product.png)](screenshots/halloween-kitty-product.png) [![万圣Kitty 色彩图](screenshots/halloween-kitty-chart.png)](screenshots/halloween-kitty-chart.png) [![万圣Kitty 对比图](screenshots/halloween-kitty-compare.png)](screenshots/halloween-kitty-compare.png)

> 224 格 55 色 → 精品版 96 格 7 色 4613 颗。幽灵的轮廓、南瓜桶、蝴蝶结全在。

### 飞龙（纹身手稿）

[![飞龙 成品图](screenshots/dragon-product.png)](screenshots/dragon-product.png) [![飞龙 色彩图](screenshots/dragon-chart.png)](screenshots/dragon-chart.png) [![飞龙 对比图](screenshots/dragon-compare.png)](screenshots/dragon-compare.png)

> 256 格 **4 色** 16198 颗。线稿模式的典型输出——两档黑、一档灰、一档白。

### 弓箭手（纹身手稿）

[![弓箭手 成品图](screenshots/archer-product.png)](screenshots/archer-product.png) [![弓箭手 色彩图](screenshots/archer-chart.png)](screenshots/archer-chart.png) [![弓箭手 对比图](screenshots/archer-compare.png)](screenshots/archer-compare.png)

> 256 格 4 色 8035 颗。细线全部连续，没有断成点阵。

### 曼陀罗

[![曼陀罗 成品图](screenshots/mandala-product.png)](screenshots/mandala-product.png) [![曼陀罗 色彩图](screenshots/mandala-chart.png)](screenshots/mandala-chart.png) [![曼陀罗 对比图](screenshots/mandala-compare.png)](screenshots/mandala-compare.png)

> 256 格 4 色 17513 颗。同心花纹在高格数下保住了。

### 完整路飞

[![完整路飞 成品图](screenshots/luffy-product.png)](screenshots/luffy-product.png) [![完整路飞 色彩图](screenshots/luffy-chart.png)](screenshots/luffy-chart.png) [![完整路飞 对比图](screenshots/luffy-compare.png)](screenshots/luffy-compare.png)

> 128 格 45 色。这张压不到低色号——细节太多，硬压会碎，所以只出高保真版。

### 龙首

[![龙首 成品图](screenshots/dragon-head-product.png)](screenshots/dragon-head-product.png) [![龙首 色彩图](screenshots/dragon-head-chart.png)](screenshots/dragon-head-chart.png) [![龙首 对比图](screenshots/dragon-head-compare.png)](screenshots/dragon-head-compare.png)

> 256 格 32 色 7928 颗。grabCut 分割，背景干净。

## Architecture

| 文件 | 作用 | 何时加载 |
|---|---|---|
| `SKILL.md` | 触发条件、流程、10 条红线 | 每次会话 |
| `README.md` | 人类和 Agent 的入口文档 | 需要安装/理解时 |
| `config.json` | 品牌、路径、豆径、阈值 | 启动时 |
| `scripts/auto_run.py` | 主流程，一条命令跑完 | 出图时 |
| `scripts/cutout.py` | 抠图（平色判据 / grabCut） | 抠图时 |
| `scripts/lowcolor.py` | 低色号取色、线稿模式 | 降色号时 |
| `scripts/brand.py` | 亚麻纸、水印、四张成品图 | 渲染时 |
| `scripts/extras.py` | 预处理、查重、采购单、画廊、PDF | 按需 |
| `references/制作规范.md` | 748 行完整规范，含全部参数与踩坑 | 改参数前 |

## Philosophy

1. **不做模型，只做算法。** 取色是 k-means + 众数，不是神经网络。同样输入永远同样输出，不需要训练，也不需要 GPU。
2. **分辨率优先于色数。** 宁可 256 格 4 色，也不要 96 格 20 色——格数决定「看不看得出形状」，色数只决定「像不像」。
3. **碎点率是一等指标。** `speckle ≤ 0.048` 是硬门槛。低于这个值图才干净，客户才拼得动。
4. **宁可不出，不出次品。** 低色号版达不到标准就跳过，只留高保真版，不硬凑。
5. **配置驱动，不写死。** 品牌、路径、豆径、阈值全在 `config.json`。代码里出现魔法数字就是 bug。

## Requirements

- Python 3.9+
- `pip install -r requirements.txt`（pillow / numpy / scipy / openpyxl / opencv-python-headless）
- 中文字体：Windows 自带微软雅黑；macOS 用苹方；Linux 需装 Noto Sans CJK 或文泉驿

## Credits

Created by 公子 · [@你的GitHub](https://github.com/).

## License

MIT — Use it, modify it, share it.
