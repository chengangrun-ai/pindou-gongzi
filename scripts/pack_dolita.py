# -*- coding: utf-8 -*-
"""pack-dolita.py —— 豆莉塔色号 + 公子 skill 装包

色号/配色一律走豆莉塔（MARD 291 色，与线上 2.0 逐格一致），
视觉层（高级纸背景、豆板成品图、水印、对比图、交付包、台账、zip）复用 pindou-gongzi。

    python tools/pack-dolita.py --src "图片目录" [--out 输出目录]

产出（每件）：
    XX_作品名/
        01_原图.png        亚麻纸背景 + 页脚署名（不铺水印）
        02_成品图.png      豆板浮纸 + skill 水印
        03_色号图.png      豆莉塔图纸（每格 MARD 色号/坐标/用料清单）+ skill 水印
        04_对比图.png      原图 / 成品并排 + skill 水印
        交付包/            交付_色号图.pdf / 交付_成品图.jpg / 交付_说明.txt
    无标版/XX_作品名/      02/03/04 无水印版（给客户）
"""
import argparse, base64, json, os, sys, urllib.request, io, zipfile
import numpy as np
from PIL import Image, ImageDraw, ImageChops, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import brand as BR          # noqa: E402
import extras as X          # noqa: E402
import chart_hq as HQ       # noqa: E402  色号矩阵 → 原生排版（PNG 高清 + 矢量 PDF）

SITE = 'https://perlerbeads.zippland.com/'

# 取色引擎 = 豆莉塔平台（MARD 291）。默认走公网，本地开发可设 DOLITA_API
API = os.environ.get('DOLITA_API') or 'http://127.0.0.1:5173'
IMG_EXT = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')

NOTE = """【拼豆图纸使用说明】

一、先看色号图
   打开「交付_色号图.pdf」，这是完整图纸。
   每格写着色号（如 A23、R20），照着摆豆就行。
   图纸底部有用料清单：每个色号几颗。

二、怎么放大看
   「交付_色号图.pdf」是矢量文件，放大到 800% 也不糊。
   手机上用 PDF 阅读器（微信/夸克/系统自带都行），双指放大。

三、要打印的话
   PDF 可以按任意尺寸打印（建议 A3 或更大幅面），
   也可让我另出分块打印版（每块 64×64 格，A4 拼贴）。

四、买豆
   用料清单上的色号是 MARD 标准色号，直接照着色号买。
   每种色号多买 15% 备用（拼的时候会掉、会错）。

五、拼的时候
   从左上角开始，按行推进，别跳着拼。

原创图纸，商用需要授权，请勿二次传播。
"""


def api_convert(path, width, threshold, brand, cell_size=36):
    """取色 = 豆莉塔引擎。默认走零依赖 node 桥（不需要服务器）；
    设了 DOLITA_API 才走 HTTP。两条路用的是同一份 core，结果逐格一致。"""
    if os.environ.get('DOLITA_API'):
        b64 = base64.b64encode(open(path, 'rb').read()).decode()
        body = {'image': b64, 'name': os.path.splitext(os.path.basename(path))[0],
                'options': {'width': width, 'threshold': threshold, 'brand': brand},
                'sheet': {'cellSize': cell_size, 'markText': ''},
                'includeGrid': True}
        req = urllib.request.Request(API + '/api/convert', data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)

    import subprocess, tempfile
    bridge = os.path.join(HERE, 'dolita_convert.mjs')
    # node 读中文路径没问题，但 stdout 走文件避免 PowerShell 重编码
    with tempfile.NamedTemporaryFile('w+', suffix='.json', delete=False, encoding='utf-8') as tf:
        tmp = tf.name
    try:
        with open(tmp, 'wb') as fo:
            p = subprocess.run(['node', bridge, os.path.abspath(path),
                                str(width), str(threshold), brand],
                               stdout=fo, stderr=subprocess.PIPE, timeout=300)
        data = json.load(open(tmp, encoding='utf-8'))
        if not data.get('ok'):
            raise RuntimeError('取色失败：' + str(data.get('error') or p.stderr.decode('utf-8', 'ignore')))
        return data
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def grid_to_idx(grid, colors):
    """grid -> (idx 矩阵, pal[(色号, hex)])，色号一律用豆莉塔的 MARD 编号"""
    order = {c['hex'].upper(): i for i, c in enumerate(colors)}
    idx = []
    miss = 0
    for row in grid:
        r = []
        for cell in row:
            h = (cell.get('color') or cell.get('key') or '').upper()
            if h in order:
                r.append(order[h])
            else:
                order[h] = len(colors); colors.append({'hex': h, 'code': '-', 'count': 1}); r.append(order[h])
                miss += 1
        idx.append(r)
    pal = [(c['code'], c['hex']) for c in colors]
    return np.array(idx, dtype=np.int32), pal, miss


def original_card(img, size=None):
    """01 原图 → 高级亚麻纸背景卡（纸纹/阴影/品牌页脚，不铺水印）"""
    W, H = size or (1620, 2160)
    canvas = BR.paper(W, H)
    s = min((W * 0.66) / img.width, (H * 0.72) / img.height)
    w, h = int(img.width * s), int(img.height * s)
    t = img.resize((w, h), Image.LANCZOS)
    x, y = (W - w) // 2, int(H * 0.45) - h // 2

    mask = Image.new('L', (W, H), 0)
    if t.mode == 'RGBA':
        mask.paste(t.split()[3], (x, y))
    else:
        ImageDraw.Draw(mask).rectangle([x, y, x + w, y + h], fill=255)
    sh = ImageChops.offset(mask.filter(ImageFilter.GaussianBlur(18)), 0, 10)
    canvas.paste((120, 112, 102), (0, 0), sh.point(lambda v: int(v * 0.34)))
    canvas.paste(t, (x, y), t if t.mode == 'RGBA' else None)
    BR.brand_footer(canvas, scale=1.0)
    return canvas


def mark_sheet(sheet, cols, rows):
    """03 色号图：按 skill 的色号图规则铺水印（浅、只铺网格区域，不糊色号）"""
    W, H = sheet.size
    x0 = int(W * 0.0253)
    y0 = int(H * 0.0416)
    cell_px = (W - 2 * x0) / cols
    BR.watermark(sheet, BR.WM, (x0, y0, x0 + cols * cell_px, y0 + rows * cell_px),
                 size=max(56, int(cell_px * 2.6)), alpha=150, spacing=1.45)
    return sheet


def safe_name(s, maxlen=32):
    bad = '\\/:*?"<>|'
    s = ''.join('_' if ch in bad else ch for ch in s).strip()
    return s[:maxlen] or 'untitled'


def overview(items, out_dir, cols=5, cell=(300, 400)):
    if not items:
        return
    W, H = cell
    rows_n = (len(items) + cols - 1) // cols
    canvas = Image.new('RGB', (cols * W + 40, rows_n * (H + 34) + 40), (247, 244, 238))
    d = ImageDraw.Draw(canvas)
    f = BR.fnt(18)
    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        x, y = 20 + c * W, 20 + r * (H + 34)
        th = Image.open(it['thumb']).convert('RGB')
        th.thumbnail((W - 10, H - 10))
        canvas.paste(th, (x + (W - th.width) // 2, y + (H - th.height) // 2))
        d.text((x + 4, y + H + 4), f"{it['no']:02d} {it['name']}", font=f, fill=(40, 40, 40))
    canvas.save(os.path.join(out_dir, '00_总览.png'), optimize=True)


def write_xlsx(items, out_dir):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment
    wb = Workbook(); ws = wb.active; ws.title = '作品清单'
    head = ['编号', '作品名', '源文件', '格数', '色数', '总豆数', '主要色号',
            '图纸尺寸', '评级', '已发社媒', '已交付']
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True); c.alignment = Alignment(horizontal='center')
    for it in items:
        ws.append([it['no'], it['name'], it['file'], f"{it['cols']}×{it['rows']}",
                   it['colors'], it['beads'], it['top_codes'],
                   f"{it['w']}×{it['h']}", it['grade'], '☐', '☐'])
    widths = [6, 24, 24, 12, 8, 10, 40, 14, 8, 10, 8]
    for i, wd in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = wd
    ws.freeze_panes = 'A2'
    wb.save(os.path.join(out_dir, '作品清单.xlsx'))


def grade_of(colors, beads):
    if colors >= 30 and beads >= 3000:
        return 'A'
    if colors >= 16:
        return 'B'
    return 'C'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', default=os.path.expanduser(r'~\Downloads\拼豆成品_豆莉塔'))
    ap.add_argument('--width', type=int, default=100, help='横向格数（默认 100，与线上 2.0 一致）')
    ap.add_argument('--threshold', type=int, default=30)
    ap.add_argument('--brand', default='MARD')
    ap.add_argument('--cell-size', type=int, default=36, help='图纸每格像素（36 = 与原作者完全同规格）')
    ap.add_argument('--card-w', type=int, default=1620)
    ap.add_argument('--card-h', type=int, default=2160)
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()

    files = [f for f in sorted(os.listdir(a.src)) if f.lower().endswith(IMG_EXT)]
    if a.limit:
        files = files[:a.limit]
    if not files:
        print('没有图片'); return 1
    os.makedirs(a.out, exist_ok=True)
    no_logo_root = os.path.join(a.out, '无标版')
    os.makedirs(no_logo_root, exist_ok=True)

    items = []
    card_size = (a.card_w, a.card_h)
    for i, fn in enumerate(files, 1):
        p = os.path.join(a.src, fn)
        name = safe_name(os.path.splitext(fn)[0])
        try:
            r = api_convert(p, a.width, a.threshold, a.brand, a.cell_size)
            cols, rows = r['manifest']['grid']['cols'], r['manifest']['grid']['rows']
            colors = r['manifest']['colors']
            idx, pal, miss = grid_to_idx(r['grid'], colors)
            beads = int((idx >= 0).sum())

            d = os.path.join(a.out, f"{i:02d}_{name}")
            dn = os.path.join(no_logo_root, f"{i:02d}_{name}")
            os.makedirs(d, exist_ok=True)
            os.makedirs(dn, exist_ok=True)

            orig = Image.open(p).convert('RGB')
            original_card(orig, card_size).save(os.path.join(d, '01_原图.png'))

            # 02 成品图：豆板浮纸 + skill 水印
            cell = max(8, int(card_size[0] * 0.84 / cols))
            BR.render_card(idx, pal, cell=cell, size=card_size, mark=True).save(
                os.path.join(d, '02_成品图.png'))
            BR.render_card(idx, pal, cell=cell, size=card_size, mark=False).save(
                os.path.join(dn, '02_成品图_无标.png'))

            # 03 色号图：从色号矩阵原生排版（不是把已渲染的 PNG 放大）
            counts = [c['count'] for c in colors]
            qr = os.path.join(os.environ.get('TEMP', '.'), 'qr_sheet.png')
            HQ.make_qr(SITE, qr)
            plain03 = os.path.join(dn, '03_色号图_无标.png')
            _, sheet_size = HQ.render_png(idx, pal, counts, cols, rows, a.cell_size,
                                          plain03, qr_png=qr, total=beads)
            marked = Image.open(plain03).convert('RGB')
            L = HQ.layout(cols, rows, a.cell_size, len(pal))
            BR.watermark(marked, BR.WM,
                         (L['margin'], L['top'],
                          L['margin'] + L['grid_w'], L['top'] + L['grid_h']),
                         size=max(56, int(a.cell_size * 1.8)), alpha=120, spacing=1.8)
            marked.save(os.path.join(d, '03_色号图.png'), optimize=True)

            # 03 矢量版（SVG）：浏览器打开可无限缩放，永远不糊
            HQ.render_svg(idx, pal, counts, cols, rows, a.cell_size,
                          os.path.join(d, '03_色号图.svg'),
                          total=beads, wm_text=BR.WM, wm_alpha=0.14)
            HQ.render_svg(idx, pal, counts, cols, rows, a.cell_size,
                          os.path.join(dn, '03_色号图_无标.svg'), total=beads, wm_text=None)

            # 04 对比图（skill 默认 1400×920 版式，留白才正常）
            ms = BR.mosaic(idx, pal, 18)
            BR.render_compare(orig, ms, name, mark=True).save(
                os.path.join(d, '04_对比图.png'))
            BR.render_compare(orig, ms, name, mark=False).save(
                os.path.join(dn, '04_对比图_无标.png'))

            # 交付包（每次必出）
            dp = os.path.join(d, '交付包')
            os.makedirs(dp, exist_ok=True)
            try:
                HQ.render_pdf(idx, pal, counts, cols, rows, a.cell_size,
                              os.path.join(dp, '交付_色号图.pdf'),
                              qr_png=qr, total=beads,
                              wm_text=BR.WM, wm_alpha=0.20)
                pages = 1
            except Exception as e:
                pages = 0
                print(f"  ! PDF 失败 {name}: {e}")
            im = Image.open(os.path.join(dn, '02_成品图_无标.png')).convert('RGB')
            im.thumbnail((1400, 1400), Image.LANCZOS)
            im.save(os.path.join(dp, '交付_成品图.jpg'), quality=92, optimize=True)
            with open(os.path.join(dp, '交付_说明.txt'), 'w', encoding='utf-8') as f:
                f.write(NOTE)

            top = sorted(colors, key=lambda c: -c['count'])[:6]
            items.append(dict(no=i, name=name, file=fn, cols=cols, rows=rows,
                              beads=beads, colors=len(colors),
                              top_codes=' '.join(f"{c['code']}({c['count']})" for c in top),
                              w=sheet_size[0], h=sheet_size[1],
                              thumb=os.path.join(d, '01_原图.png'),
                              path=d, nologo=dn, pages=pages,
                              grade=grade_of(len(colors), beads), miss=miss))
            print(f"[OK] {fn} -> {cols}x{rows} {len(colors)}色 {beads}颗 "
                  f"图纸{sheet_size[0]}x{sheet_size[1]} 矢量PDF 评级{items[-1]['grade']}")
        except Exception as e:
            print(f"[FAIL] {fn}: {e}")

    if not items:
        return 1
    overview(items, a.out)
    write_xlsx(items, a.out)
    json.dump(items, open(os.path.join(a.out, 'manifest.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    zp = os.path.join(a.out, f'豆莉塔_{len(items)}件_全套.zip')
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
        for it in items:
            base = os.path.basename(it['path'])
            for root, _, fs in os.walk(it['path']):
                for f in fs:
                    fp = os.path.join(root, f)
                    z.write(fp, arcname=os.path.relpath(fp, a.out))
            for root, _, fs in os.walk(it['nologo']):
                for f in fs:
                    fp = os.path.join(root, f)
                    z.write(fp, arcname=os.path.relpath(fp, a.out))
        z.write(os.path.join(a.out, '作品清单.xlsx'), arcname='作品清单.xlsx')
        z.write(os.path.join(a.out, '00_总览.png'), arcname='00_总览.png')
    print(f"\n完成 {len(items)} 件 -> {a.out}")
    print('包：', zp)
    return 0


if __name__ == '__main__':
    sys.exit(main())
