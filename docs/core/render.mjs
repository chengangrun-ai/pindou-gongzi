// 豆莉塔渲染核心：网格 -> RGBA 像素缓冲（纯函数，无 DOM / Canvas / fs）。
// 图纸版式几何复刻原版 imageDownloader.ts（cellSize/边距/标题栏/坐标轴/统计区公式一致），
// 品牌视觉与文字为豆莉塔原创；文字用内置 5x7 点阵字体栅格化，保证 Node 与浏览器逐像素一致。
// 水印引擎为新增量功能（原版只有硬编码作者标识，无可配置水印）。

import { getDisplayColorKey, getContrastColor, sortColorKeys, hexToRgb } from './bead-core.mjs';
import { encodeQrMatrix } from './qr.mjs';
import { glyphOf, normalizeText, measureText, textHeight, unsupportedChars, FONT_W, FONT_H } from './font5x7.mjs';
import { GLYPH_BASE_H, GLYPH_GAP, glyphEntry, glyphRowAlphas, measureGlyph, glyphLineHeight } from './font-glyph.mjs';

// ---- 灰度字形栅格缓存：把基准档位图按目标尺寸做「区域平均」重采样 ----
// 直接最近邻缩放会让笔画粗细忽粗忽细、边缘发毛；区域平均等价于真实字形的抗锯齿覆盖度。
const BASE_GRID_CACHE = new Map();
const TEXT_BMP_CACHE = new Map();
const SS = 4; // 每目标像素 4x4 超采样

function baseGrid(ch, weight) {
  const ck = weight + '|' + ch;
  let g = BASE_GRID_CACHE.get(ck);
  if (g) return g;
  const [gw, gh, rows] = glyphEntry(ch, weight);
  const a = new Float32Array(gw * gh);
  for (let y = 0; y < gh; y++) {
    const al = glyphRowAlphas(rows[y] || '', gw);
    for (let x = 0; x < gw; x++) a[y * gw + x] = al[x] || 0;
  }
  g = { gw, gh, a };
  BASE_GRID_CACHE.set(ck, g);
  return g;
}

function sampleBilinear(grid, sx, sy) {
  const { gw, gh, a } = grid;
  const cx = Math.min(gw - 1, Math.max(0, sx - 0.5));
  const cy = Math.min(gh - 1, Math.max(0, sy - 0.5));
  const x0 = Math.floor(cx), y0 = Math.floor(cy);
  const x1 = Math.min(gw - 1, x0 + 1), y1 = Math.min(gh - 1, y0 + 1);
  const fx = cx - x0, fy = cy - y0;
  const v00 = a[y0 * gw + x0], v10 = a[y0 * gw + x1];
  const v01 = a[y1 * gw + x0], v11 = a[y1 * gw + x1];
  return (v00 * (1 - fx) + v10 * fx) * (1 - fy) + (v01 * (1 - fx) + v11 * fx) * fy;
}

function buildTextBitmap(text, weight, px) {
  const s = px / GLYPH_BASE_H;
  const gap = Math.max(0, Math.round(GLYPH_GAP * s));
  const cps = Array.from(text);
  const items = [];
  let w = 0;
  for (let i = 0; i < cps.length; i++) {
    const [gw, gh] = glyphEntry(cps[i], weight);
    const dw = Math.max(1, Math.round(gw * s));
    const dh = Math.max(1, Math.round(gh * s));
    items.push({ ch: cps[i], gw, gh, dw, dh, x: w });
    w += dw + (i < cps.length - 1 ? gap : 0);
  }
  const lineH = glyphLineHeight(px);
  let h = lineH;
  for (const it of items) h = Math.max(h, it.dh);
  const acc = new Float32Array(w * h);
  for (const it of items) {
    const grid = baseGrid(it.ch, weight);
    const yOff = Math.max(0, lineH - it.dh); // 底部对齐行高（与旧行为一致）
    for (let dy = 0; dy < it.dh; dy++) {
      const y = yOff + dy;
      if (y >= h) continue;
      for (let dx = 0; dx < it.dw; dx++) {
        let sum = 0;
        for (let v = 0; v < SS; v++) {
          const sy = (dy + (v + 0.5) / SS) * it.gh / it.dh;
          for (let u = 0; u < SS; u++) {
            const sx = (dx + (u + 0.5) / SS) * it.gw / it.dw;
            sum += sampleBilinear(grid, sx, sy);
          }
        }
        const k = y * w + dx + it.x;
        acc[k] = Math.min(1, acc[k] + sum / (SS * SS) / 15);
      }
    }
  }
  const a = new Uint8Array(w * h);
  for (let i = 0; i < a.length; i++) a[i] = Math.round(acc[i] * 255);
  return { w, h, a };
}

function textBitmap(text, weight, px) {
  const ck = weight + '|' + px + '|' + text;
  let bm = TEXT_BMP_CACHE.get(ck);
  if (!bm) { bm = buildTextBitmap(text, weight, px); TEXT_BMP_CACHE.set(ck, bm); }
  return bm;
}

function colorRGB(hex) {
  const rgb = hexToRgb(hex) || { r: 0, g: 0, b: 0 };
  return [rgb.r, rgb.g, rgb.b];
}

// 向白色提亮（料卡/格子描边用：线上格线是「提亮后的格色」，不是中性灰）
function lightenHex(hex, t) {
  const { r, g, b } = hexToRgb(hex) || { r: 255, g: 255, b: 255 };
  const k = (v) => Math.round(v + (255 - v) * t);
  return '#' + [k(r), k(g), k(b)].map((v) => v.toString(16).padStart(2, '0')).join('');
}

// 向指定色混合（格线实测为「去饱和 + 微提亮」，和线上观感一致）
function mixHex(hex, targetHex, t) {
  const a = hexToRgb(hex) || { r: 255, g: 255, b: 255 };
  const b2 = hexToRgb(targetHex) || { r: 255, g: 255, b: 255 };
  const k = (x, y) => Math.round(x + (y - x) * t);
  return '#' + [k(a.r, b2.r), k(a.g, b2.g), k(a.b, b2.b)].map((v) => v.toString(16).padStart(2, '0')).join('');
}

// 单颗豆的描边：外圈「降饱和压暗」做分隔线，内圈「微提亮」做方块高光 → 方块方正清晰
function beadEdgeHexes(hex) {
  const { r, g, b } = hexToRgb(hex) || { r: 255, g: 255, b: 255 };
  const lum = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
  const gray = `#${[lum, lum, lum].map((v) => v.toString(16).padStart(2, '0')).join('')}`;
  const core = mixHex(hex, gray, 0.42);
  const light = lightenHex(hex, 0.16);
  return [core, light];
}

export class Raster {
  constructor(width, height, fill = '#FFFFFF') {
    this.width = width;
    this.height = height;
    this.data = new Uint8ClampedArray(width * height * 4);
    if (fill) this.fillRect(0, 0, width, height, fill, 1);
  }

  blendPx(x, y, r, g, b, a) {
    if (x < 0 || y < 0 || x >= this.width || y >= this.height || a <= 0) return;
    const i = (y * this.width + x) * 4;
    const d = this.data;
    if (a >= 255) { d[i] = r; d[i + 1] = g; d[i + 2] = b; d[i + 3] = 255; return; }
    const ia = 255 - a;
    const da = d[i + 3];
    // 标准 source-over（两端同一整数公式，结果确定）
    const outA = a + Math.round(da * ia / 255);
    if (outA === 0) { d[i] = 0; d[i + 1] = 0; d[i + 2] = 0; d[i + 3] = 0; return; }
    d[i] = Math.round((r * a + d[i] * da * ia / 255) / outA);
    d[i + 1] = Math.round((g * a + d[i + 1] * da * ia / 255) / outA);
    d[i + 2] = Math.round((b * a + d[i + 2] * da * ia / 255) / outA);
    d[i + 3] = outA;
  }

  fillRect(x, y, w, h, color, alpha = 1) {
    const [r, g, b] = colorRGB(color);
    const a = Math.round(alpha * 255);
    const x0 = Math.max(0, Math.floor(x)), y0 = Math.max(0, Math.floor(y));
    const x1 = Math.min(this.width, Math.floor(x + w)), y1 = Math.min(this.height, Math.floor(y + h));
    for (let yy = y0; yy < y1; yy++) for (let xx = x0; xx < x1; xx++) this.blendPx(xx, yy, r, g, b, a);
  }

  // 矩形描边（thickness 为整数像素；原版 0.5/1.5 线宽用 alpha 近似，两端一致）
  strokeRect(x, y, w, h, color, thickness = 1, alpha = 1) {
    this.fillRect(x, y, w, thickness, color, alpha);
    this.fillRect(x, y + h - thickness, w, thickness, color, alpha);
    this.fillRect(x, y, thickness, h, color, alpha);
    this.fillRect(x + w - thickness, y, thickness, h, color, alpha);
  }

  hLine(x, y, w, color, thickness = 1, alpha = 1) { this.fillRect(x, y, w, thickness, color, alpha); }
  vLine(x, y, h, color, thickness = 1, alpha = 1) { this.fillRect(x, y, thickness, h, color, alpha); }

  fillCircle(cx, cy, radius, color, alpha = 1) {
    const [r, g, b] = colorRGB(color);
    const a = Math.round(alpha * 255);
    const r2 = radius * radius;
    const x0 = Math.max(0, Math.floor(cx - radius)), x1 = Math.min(this.width - 1, Math.ceil(cx + radius));
    const y0 = Math.max(0, Math.floor(cy - radius)), y1 = Math.min(this.height - 1, Math.ceil(cy + radius));
    for (let yy = y0; yy <= y1; yy++) for (let xx = x0; xx <= x1; xx++) {
      const dx = xx + 0.5 - cx, dy = yy + 0.5 - cy;
      if (dx * dx + dy * dy <= r2) this.blendPx(xx, yy, r, g, b, a);
    }
  }

  roundRectFill(x, y, w, h, radius, color, alpha = 1) {
    const [r, g, b] = colorRGB(color);
    const a = Math.round(alpha * 255);
    const rad = Math.min(radius, w / 2, h / 2);
    const x0 = Math.max(0, Math.floor(x)), y0 = Math.max(0, Math.floor(y));
    const x1 = Math.min(this.width, Math.ceil(x + w)), y1 = Math.min(this.height, Math.ceil(y + h));
    for (let yy = y0; yy < y1; yy++) for (let xx = x0; xx < x1; xx++) {
      const px = xx + 0.5, py = yy + 0.5;
      if (px < x || px > x + w || py < y || py > y + h) continue;
      let inside = true;
      const cx = px < x + rad ? x + rad : (px > x + w - rad ? x + w - rad : null);
      const cy = py < y + rad ? y + rad : (py > y + h - rad ? y + h - rad : null);
      if (cx !== null && cy !== null) {
        const dx = px - cx, dy = py - cy;
        inside = dx * dx + dy * dy <= rad * rad;
      }
      if (inside) this.blendPx(xx, yy, r, g, b, a);
    }
  }

  // 仅顶部两角圆角、底部两角直角的矩形（料卡上部色块用，对齐线上 2.0）
  roundRectTopFill(x, y, w, h, radius, color, alpha = 1) {
    const [r, g, b] = colorRGB(color);
    const a = Math.round(alpha * 255);
    const rad = Math.min(radius, w / 2, h / 2);
    const x0 = Math.max(0, Math.floor(x)), y0 = Math.max(0, Math.floor(y));
    const x1 = Math.min(this.width, Math.ceil(x + w)), y1 = Math.min(this.height, Math.ceil(y + h));
    for (let yy = y0; yy < y1; yy++) for (let xx = x0; xx < x1; xx++) {
      const px = xx + 0.5, py = yy + 0.5;
      if (px < x || px > x + w || py < y || py > y + h) continue;
      let inside = true;
      const cx = px < x + rad ? x + rad : (px > x + w - rad ? x + w - rad : null);
      if (cx !== null && py < y + rad) {
        const cy = y + rad;
        const dx = px - cx, dy = py - cy;
        inside = dx * dx + dy * dy <= rad * rad;
      }
      if (inside) this.blendPx(xx, yy, r, g, b, a);
    }
  }

  // 最近邻缩放贴图（logo / 二维码），确定性采样
  blit(src, sw, sh, dx, dy, dw, dh, alpha = 1) {
    const ga = Math.round(alpha * 255);
    for (let yy = 0; yy < dh; yy++) {
      const sy = Math.min(sh - 1, Math.floor(yy * sh / dh));
      const ty = Math.floor(dy) + yy;
      if (ty < 0 || ty >= this.height) continue;
      for (let xx = 0; xx < dw; xx++) {
        const sx = Math.min(sw - 1, Math.floor(xx * sw / dw));
        const tx = Math.floor(dx) + xx;
        if (tx < 0 || tx >= this.width) continue;
        const si = (sy * sw + sx) * 4;
        const sa = src[si + 3];
        if (sa === 0) continue;
        this.blendPx(tx, ty, src[si], src[si + 1], src[si + 2], Math.round(sa * ga / 255));
      }
    }
  }

  // 点阵文字。px 为目标字高，内部取整数倍率 scale=floor(px/7)（>=1）。y 为文字顶部。
  text(str, x, y, px, color, { align = 'left', bold = false, alpha = 1 } = {}) {
    const t = normalizeText(str);
    if (!t) return;
    const scale = Math.max(1, Math.floor(px / FONT_H));
    const w = measureText(t, scale);
    let startX = Math.floor(x);
    if (align === 'center') startX = Math.floor(x - w / 2);
    else if (align === 'right') startX = Math.floor(x - w);
    const [r, g, b] = colorRGB(color);
    const a = Math.round(alpha * 255);
    const boldShift = bold ? Math.max(1, Math.floor(scale / 2)) : 0;
    let cursor = startX;
    for (const ch of t) {
      const rows = glyphOf(ch);
      for (let ry = 0; ry < FONT_H; ry++) {
        const bits = rows[ry];
        for (let rx = 0; rx < FONT_W; rx++) {
          if (bits & (1 << (FONT_W - 1 - rx))) {
            const px0 = cursor + rx * scale, py0 = Math.floor(y) + ry * scale;
            this.fillRect(px0, py0, scale + boldShift, scale, color, alpha);
          }
        }
      }
      cursor += (FONT_W + 1) * scale;
    }
    return { x: startX, y: Math.floor(y), w, h: textHeight(scale), scale };
  }

  // 灰度平滑文字（Noto Sans SC 预栅格化查表，比例宽度）。px 为目标字高，y 为顶部。
  textGlyph(str, x, y, px, color, { align = 'left', bold = false, alpha = 1 } = {}) {
    const t = String(str);
    if (!t) return { x: Math.floor(x), y: Math.floor(y), w: 0, h: 0 };
    const weight = bold ? 'bold' : 'regular';
    const bm = textBitmap(t, weight, px);
    const w = bm.w;
    let startX = Math.floor(x);
    if (align === 'center') startX = Math.floor(x - w / 2);
    else if (align === 'right') startX = Math.floor(x - w);
    const [r, g, b] = colorRGB(color);
    const textA = Math.round(alpha * 255);
    const top = Math.floor(y) + Math.max(0, glyphLineHeight(px) - bm.h);
    for (let yy = 0; yy < bm.h; yy++) {
      const rowBase = yy * w;
      for (let xx = 0; xx < w; xx++) {
        const a8 = bm.a[rowBase + xx];
        if (!a8) continue;
        this.blendPx(startX + xx, top + yy, r, g, b, textA >= 255 ? a8 : Math.round(a8 * textA / 255));
      }
    }
    return { x: startX, y: Math.floor(y), w, h: glyphLineHeight(px) };
  }

  clone() {
    const r = new Raster(this.width, this.height, null);
    r.data.set(this.data);
    return r;
  }
}

// ---------- 预览图（纯色块网格） ----------

export function renderPreview(result, cellSize = 12) {
  const { grid, N, M } = result;
  const raster = new Raster(N * cellSize, M * cellSize, '#FFFFFF');
  for (let j = 0; j < M; j++) for (let i = 0; i < N; i++) {
    const cell = grid[j][i];
    if (cell && !cell.isExternal) raster.fillRect(i * cellSize, j * cellSize, cellSize, cellSize, cell.color || '#FFFFFF', 1);
  }
  return raster;
}

// ---------- 导出图纸（版式几何对齐原版 imageDownloader.ts） ----------

export const SHEET_DEFAULTS = Object.freeze({
  cellSize: 36,
  showGrid: true,
  gridInterval: 10,
  showCoordinates: true,
  showCellNumbers: true,
  gridLineColor: '#555555',
  includeStats: true,
  title: '豆莉塔',
  subtitle: '拼豆底稿生成器',
  brandColor: '#2F9E6E',
  titleBarColor: '#1F2937',
  markText: '@DOLITA',
  footerText: 'MADE WITH DOLITA (AGPL-3.0)',
  qrImage: null, // {data,width,height}
  qrUrl: '', // 图纸右上角二维码编码的网址；留空则显示 SCAN 占位
  author: '', // 作者署名（左下角，留空不显示）
  shareCode: '', // 画册分享码（署名下方小字，留空不显示）
});

export function renderSheet(result, opts = {}) {
  const o = { ...SHEET_DEFAULTS, ...opts };
  const { grid, N, M, colorCounts, totalBeads, brand } = result;
  const downloadCellSize = o.cellSize;

  // markText 走内置点阵（仅 ASCII）；title/subtitle/footerText 走灰度字形表，允许中文
  if (o.markText) {
    const bad = unsupportedChars(o.markText);
    if (bad.length) throw Object.assign(new Error(`图纸角标文字含不支持字符 ${JSON.stringify(bad)}（角标仅支持 ASCII，中文请用标题/副标题）`), { code: 'BAD_SHEET_TEXT' });
  }

  const gridWidth = N * downloadCellSize;
  const gridHeight = M * downloadCellSize;
  const footerAreaHeight = 35;

  const axisLabelSize = o.showCoordinates ? Math.max(30, Math.floor(downloadCellSize)) : 0;
  // 两侧留白：线上 3792 宽页面里网格左右各留 96px（= 坐标条 36 + 余白 60）
  const extraLeftMargin = o.showCoordinates ? Math.max(24, Math.round(gridWidth * 0.0167)) : 0;
  const extraRightMargin = o.showCoordinates ? Math.max(24, Math.round(gridWidth * 0.0167)) : 0;
  const extraTopMargin = o.showCoordinates ? Math.max(15, Math.round(downloadCellSize * 0.55)) : 0;
  const extraBottomMargin = o.showCoordinates ? Math.max(15, Math.round(downloadCellSize * 0.55)) : 0;

  // 页面宽度（= 网格 + 两侧坐标条 + 两侧留白）
  const sheetWidthCalc = gridWidth + axisLabelSize * 2 + extraLeftMargin + extraRightMargin;
  // 料卡左右内边距：线上 3792 宽 / 74px
  const statsPadding = Math.max(16, Math.round(sheetWidthCalc * 0.0195));
  const statsAvail = sheetWidthCalc - statsPadding * 2;
  // 正文字号按页宽等比：线上「用料清单」字面约 54px 高，对应 em ≈ 57px @ 3792 宽
  const statsFontSize = Math.max(13, Math.min(60, Math.round(sheetWidthCalc * 0.0152)));

  // 标题栏高度：线上 3792 宽页面上标题区约 270px（品牌大字 + 副标）
  const titleBarHeight = Math.max(80, Math.min(300, Math.round(gridWidth * 0.075)));
  const titleFontSize = Math.round(titleBarHeight * 0.46);

  // 底部品牌条（对齐线上部署版：网格与料卡之间，品牌名两行右对齐 + 二维码最右）
  const sheetWidth = sheetWidthCalc;
  const brandBarTopPad = Math.max(24, Math.round(sheetWidth * 0.0185));
  const qrSize = Math.max(90, Math.min(190, Math.round(sheetWidth * 0.046)));
  const brandBarHeight = qrSize + brandBarTopPad * 2;

  const colorKeys = o.includeStats ? Object.keys(colorCounts).sort(sortColorKeys) : [];
  const statsTopMargin = Math.round(sheetWidth * 0.0156);
  const headerH = Math.round(sheetWidth * 0.0243);
  let statCols = 1, statRows = 0, cardW = 0, cardH = 0, blockH = 0, gapX = 0, gapY = 0, statsHeight = 0;
  if (o.includeStats) {
    // 对齐线上部署版卡片网格：8 列等宽卡片，色块在上印色号、白底在下印颗数
    const avail = statsAvail;
    statCols = Math.max(1, Math.min(8, Math.floor(avail / 180)));
    gapX = Math.max(8, Math.round(avail * 0.007));
    cardW = Math.floor((avail - (statCols - 1) * gapX) / statCols);
    cardH = Math.round(cardW * (300 / 428));   // 线上卡片高宽比 300/428
    blockH = Math.round(cardH * (184 / 300));   // 线上色块占卡片 184/300
    gapY = Math.round(cardH * 0.14);
    statRows = Math.ceil(colorKeys.length / statCols);
    const footerH = 30;
    statsHeight = headerH + statRows * cardH + Math.max(0, statRows - 1) * gapY + footerH + statsPadding * 2 + statsTopMargin;
  }

  const downloadWidth = gridWidth + axisLabelSize * 2 + extraLeftMargin + extraRightMargin;
  const downloadHeight = titleBarHeight + extraTopMargin + gridHeight + axisLabelSize * 2 + brandBarHeight + statsHeight + extraBottomMargin + footerAreaHeight;

  const ctx = new Raster(downloadWidth, downloadHeight, '#FAF9F5');

  // --- 顶部色号标识（对齐线上：品牌大字 + 「色号」小标签；品牌已在底部二维码区，此处不重复品牌条） ---
  const brandLabelSize = Math.max(24, Math.round(sheetWidth * 0.0281));
  const brandLabelX = statsPadding;
  const brandLabelTop = Math.round(sheetWidth * 0.0088);
  const brandLabelColor = '#788C5D';
  ctx.textGlyph(brand, brandLabelX, brandLabelTop, brandLabelSize, brandLabelColor, { bold: true });
  const brandTextW = measureGlyph(brand, 'bold', brandLabelSize);
  const tagFontSize = Math.max(12, Math.round(brandLabelSize * 0.33));
  const tagH = Math.round(glyphLineHeight(tagFontSize) * 1.7);
  const tagPad = Math.round(tagFontSize * 0.6);
  const tagTextW = measureGlyph('色号', 'regular', tagFontSize);
  const tagX = brandLabelX + brandTextW + Math.round(brandLabelSize * 0.16);
  const tagY = brandLabelTop + Math.round((glyphLineHeight(brandLabelSize) - tagH) / 2);
  ctx.roundRectFill(tagX, tagY, tagTextW + tagPad * 2, tagH, Math.round(tagH * 0.2), '#E9EEDC', 1);
  ctx.textGlyph('色号', tagX + tagPad, tagY + Math.round((tagH - glyphLineHeight(tagFontSize)) / 2), tagFontSize, brandLabelColor);

  const gridX = extraLeftMargin + axisLabelSize;
  const gridY = titleBarHeight + extraTopMargin + axisLabelSize;

  // --- 坐标轴 ---
  if (o.showCoordinates) {
    ctx.fillRect(gridX, titleBarHeight + extraTopMargin, gridWidth, axisLabelSize, '#F5F5F5', 1);
    ctx.fillRect(gridX, gridY + gridHeight, gridWidth, axisLabelSize, '#F5F5F5', 1);
    ctx.fillRect(extraLeftMargin, gridY, axisLabelSize, gridHeight, '#F5F5F5', 1);
    ctx.fillRect(gridX + gridWidth, gridY, axisLabelSize, gridHeight, '#F5F5F5', 1);

    const axisPx = Math.max(12, Math.round(downloadCellSize * 0.66));
    const axisH = glyphLineHeight(axisPx);
    const clampX = (cx, tw) => Math.max(2, Math.min(downloadWidth - 2 - tw, cx - tw / 2));
    const label = (str, cx, cy) => {
      const tw = measureGlyph(str, 'regular', axisPx);
      ctx.textGlyph(str, clampX(cx, tw), cy - axisH / 2, axisPx, '#333333');
    };
    for (let i = 0; i < N; i++) {
      if ((i + 1) % o.gridInterval === 0 || i === 0 || i === N - 1) {
        const cx = gridX + i * downloadCellSize + downloadCellSize / 2;
        label(String(i + 1), cx, titleBarHeight + extraTopMargin + axisLabelSize / 2);
        label(String(i + 1), cx, gridY + gridHeight + axisLabelSize / 2);
      }
    }
    for (let j = 0; j < M; j++) {
      if ((j + 1) % o.gridInterval === 0 || j === 0 || j === M - 1) {
        const cy = gridY + j * downloadCellSize + downloadCellSize / 2;
        label(String(j + 1), extraLeftMargin + axisLabelSize / 2, cy);
        label(String(j + 1), gridX + gridWidth + axisLabelSize / 2, cy);
      }
    }
    ctx.hLine(gridX, gridY - 1, gridWidth, '#AAAAAA', 1);
    ctx.hLine(gridX, gridY + gridHeight, gridWidth, '#AAAAAA', 1);
    ctx.vLine(gridX - 1, gridY, gridHeight, '#AAAAAA', 1);
    ctx.vLine(gridX + gridWidth, gridY, gridHeight, '#AAAAAA', 1);
  }

  // --- 单元格 ---
  // 格内色号字号：逐格按格子像素自适应，选能放下的最大整数倍率；深色格白字、浅色格黑字（getContrastColor）
  const fitCodePx = (key, cellSize) => {
    const pad = Math.max(2, Math.round(cellSize * 0.1));
    const availW = cellSize - pad * 2, availH = cellSize - pad * 2;
    for (let px = Math.floor(cellSize * 0.36); px >= 8; px--) {
      if (measureGlyph(key, 'bold', px) <= availW && glyphLineHeight(px) <= availH) return px;
    }
    return 8;
  };
  for (let j = 0; j < M; j++) for (let i = 0; i < N; i++) {
    const cellData = grid[j][i];
    const drawX = gridX + i * downloadCellSize;
    const drawY = gridY + j * downloadCellSize;
    if (cellData && !cellData.isExternal) {
      const cellColor = cellData.color || '#FFFFFF';
      ctx.fillRect(drawX, drawY, downloadCellSize, downloadCellSize, cellColor, 1);
      if (o.showCellNumbers) {
        const cellKey = getDisplayColorKey(cellData.color || '#FFFFFF', brand);
        const codePx = fitCodePx(cellKey, downloadCellSize);
        const codeH = glyphLineHeight(codePx);
        ctx.textGlyph(cellKey, drawX + downloadCellSize / 2, drawY + downloadCellSize / 2 - codeH / 2, codePx, getContrastColor(cellColor), { align: 'center', bold: true });
      }
      // 每颗豆画成一块带描边的小方块：1px 深色缝 + 1px 内高光，对齐线上「方块清晰」的质感
      const [edgeCore, edgeLight] = beadEdgeHexes(cellColor);
      ctx.strokeRect(drawX + 1, drawY + 1, downloadCellSize - 2, downloadCellSize - 2, edgeLight, 1, 1);
      ctx.hLine(drawX, drawY, downloadCellSize, edgeCore, 1, 1);
      ctx.vLine(drawX, drawY, downloadCellSize, edgeCore, 1, 1);
    } else {
      ctx.fillRect(drawX, drawY, downloadCellSize, downloadCellSize, '#FFFFFF', 1);
      ctx.strokeRect(drawX, drawY, downloadCellSize, downloadCellSize, '#EDEAE2', 1, 1);
    }
  }

  // --- 分隔网格线 ---
  if (o.showGrid) {
    for (let i = o.gridInterval; i < N; i += o.gridInterval) {
      ctx.vLine(gridX + i * downloadCellSize - 1, gridY, gridHeight, o.gridLineColor, 2, 0.75);
    }
    for (let j = o.gridInterval; j < M; j += o.gridInterval) {
      ctx.hLine(gridX, gridY + j * downloadCellSize - 1, gridWidth, o.gridLineColor, 2, 0.75);
    }
  }
  ctx.strokeRect(gridX, gridY, gridWidth, gridHeight, '#000000', 2, 0.75);

  // --- 左上角品牌小标（对应原版副水印位置，文案为豆莉塔原创，可关） ---
  if (o.markText) {
    const markPx = Math.max(9, Math.round(downloadCellSize * 0.32));
    const markH = glyphLineHeight(markPx);
    const markW = measureGlyph(o.markText, 'regular', markPx);
    const markX = gridX + Math.round(downloadCellSize * 0.4);
    const markY = gridY + markH + Math.round(downloadCellSize * 0.4);
    ctx.roundRectFill(markX - 5, markY - markH - 5, markW + 10, markH + 10, 3, '#FFFFFF', 0.72);
    ctx.textGlyph(o.markText, markX, markY - markH, markPx, '#9CA3AF');
  }

  // --- 底部品牌条（网格与料卡之间：品牌名两行右对齐，二维码最右，对齐线上部署版） ---
  const barTop = gridY + gridHeight + axisLabelSize;
  const qrX = downloadWidth - extraRightMargin - qrSize;
  const qrY = barTop + Math.round((brandBarHeight - qrSize) / 2);
  const drawQrPlaceholder = () => {
    const phPx = Math.max(10, Math.round(qrSize * 0.16));
    const phH = glyphLineHeight(phPx);
    ctx.textGlyph('SCAN', qrX + qrSize / 2, qrY + qrSize / 2 - phH / 2, phPx, o.brandColor, { align: 'center', bold: true });
  };
  let qrDrawn = false;
  if (o.qrImage && o.qrImage.data) {
    ctx.blit(o.qrImage.data, o.qrImage.width, o.qrImage.height, qrX, qrY, qrSize, qrSize, 1);
    qrDrawn = true;
  } else if (o.qrUrl) {
    try {
      const { size, dark } = encodeQrMatrix(o.qrUrl, 'M');
      const quiet = 2; // 外围静区（模块），条底色为白，2 模块足够扫码
      const G = size + quiet * 2;
      const mod = Math.max(1, Math.floor(qrSize / G));
      const draw = mod * G;
      const offX = qrX + (qrSize - draw) / 2;
      const offY = qrY + (qrSize - draw) / 2;
      for (let r = 0; r < size; r++) {
        for (let c = 0; c < size; c++) {
          if (dark[r * size + c]) ctx.fillRect(offX + (quiet + c) * mod, offY + (quiet + r) * mod, mod, mod, '#111827', 1);
        }
      }
      qrDrawn = true;
    } catch {
      drawQrPlaceholder();
    }
  }
  if (!qrDrawn) drawQrPlaceholder();

  // 品牌名两行，右对齐到二维码左侧
  const brandRight = qrX - Math.round(qrSize * 0.18);
  const mainBrPx = Math.max(18, Math.round(qrSize * 0.42));
  const subBrPx = Math.max(11, Math.round(qrSize * 0.22));
  const mainBrH = glyphLineHeight(mainBrPx), subBrH = glyphLineHeight(subBrPx);
  const brandBlockH = mainBrH + Math.round(subBrH * 0.6) + subBrH;
  let brandY = qrY + (qrSize - brandBlockH) / 2;
  ctx.textGlyph(o.title, brandRight, brandY, mainBrPx, '#1F2937', { align: 'right', bold: true });
  brandY += mainBrH + Math.round(subBrH * 0.6);
  ctx.textGlyph(o.subtitle, brandRight, brandY, subBrPx, '#9CA3AF', { align: 'right' });

  // 作者署名 / 画册分享码（品牌条左侧，留空不画）
  if (o.author || o.shareCode) {
    try {
      const authPx = Math.max(14, Math.round(qrSize * 0.30));
      const codePx = Math.max(11, Math.round(qrSize * 0.20));
      const authH = o.author ? glyphLineHeight(authPx) : 0;
      const codeH = o.shareCode ? glyphLineHeight(codePx) : 0;
      const gapH = authH && codeH ? Math.round(codeH * 0.35) : 0;
      const blockH2 = authH + gapH + codeH;
      let textY = barTop + Math.round((brandBarHeight - blockH2) / 2);
      if (o.author) {
        ctx.textGlyph(o.author, statsPadding, textY, authPx, '#1F2937', { bold: true });
        textY += authH + gapH;
      }
      if (o.shareCode) ctx.textGlyph(`NO. ${o.shareCode}`, statsPadding, textY, codePx, '#9CA3AF');
    } catch { /* 含字形表外字符时静默跳过署名，不影响出图 */ }
  }

  // 品牌条下细分隔线
  const barSepY = barTop + brandBarHeight;  ctx.hLine(statsPadding, barSepY, downloadWidth - statsPadding * 2, '#E8E6DC', 1, 1);

  // --- 统计区（线上部署版卡片网格） ---
  if (o.includeStats) {
    const statsY = barSepY + statsTopMargin;
    const headH = glyphLineHeight(statsFontSize);
    const headY = statsY + Math.round((headerH - headH) / 2);
    ctx.textGlyph('用料清单', statsPadding, headY, statsFontSize, '#1F2937', { bold: true });
    ctx.textGlyph(`共 ${totalBeads.toLocaleString('en-US')} 颗`, downloadWidth - statsPadding, headY, statsFontSize, '#1F2937', { align: 'right', bold: true });
    const listTop = statsY + headerH;

    colorKeys.forEach((key, index) => {
      const rowIndex = Math.floor(index / statCols);
      const colIndex = index % statCols;
      const cardX = statsPadding + colIndex * (cardW + gapX);
      const cardY = listTop + rowIndex * (cardH + gapY);
      const cellData = colorCounts[key];

      // 卡片：暖浅灰描边层 + 白底圆角卡（描边 #E8E6DC 对齐线上）
      ctx.roundRectFill(cardX - 1, cardY - 1, cardW + 2, cardH + 2, 11, '#E8E6DC', 1);
      ctx.roundRectFill(cardX, cardY, cardW, cardH, 11, '#FFFFFF', 1);

      // 上部色块：仅上角圆角、下部直角平接白底（对齐线上 2.0）
      ctx.roundRectTopFill(cardX, cardY, cardW, blockH, 11, cellData.color, 1);
      const code = getDisplayColorKey(key, brand);
      let codePx = Math.max(10, Math.round(blockH * 0.26));
      while (codePx > 8 && (measureGlyph(code, 'bold', codePx) > cardW - 16 || glyphLineHeight(codePx) > blockH - 8)) codePx--;
      const codeH = glyphLineHeight(codePx);
      ctx.textGlyph(code, cardX + cardW / 2, cardY + blockH / 2 - codeH / 2, codePx, getContrastColor(cellData.color), { align: 'center', bold: true });

      // 下部白底 + 居中颗数
      const countText = String(cellData.count);
      let countPx = Math.max(9, Math.round(cardH * 0.15));
      while (countPx > 8 && measureGlyph(countText, 'bold', countPx) > cardW - 16) countPx--;
      const countH = glyphLineHeight(countPx);
      const countY = cardY + blockH + (cardH - blockH) / 2 - countH / 2;
      ctx.textGlyph(countText, cardX + cardW / 2, countY, countPx, '#1F2937', { align: 'center', bold: true });
    });

    // 统计区来源小标（文案原创，位置对应原版页脚左下）
    if (o.footerText) {
      const fPx = Math.max(10, Math.round(statsFontSize * 0.55));
      const fY = listTop + statRows * cardH + Math.max(0, statRows - 1) * gapY + 26;
      ctx.textGlyph(o.footerText, statsPadding, fY, fPx, '#64748B');
    }
  }

  return ctx;
}

// ---------- 水印引擎（新增量功能） ----------

export const WATERMARK_DEFAULTS = Object.freeze({
  enabled: false,
  type: 'text',        // text | logo
  text: '@DOLITA',
  scale: 2,            // 点阵整数倍率（字高 = 7*scale）
  color: '#FFFFFF',
  opacity: 70,         // 0-100
  position: 'br',      // tl tc tr ml mc mr bl bc br
  margin: 16,
  tile: false,
  shadow: true,
  logo: null,          // {data,width,height}
  logoWidth: 160,
});

export const WATERMARK_POSITIONS = ['tl', 'tc', 'tr', 'ml', 'mc', 'mr', 'bl', 'bc', 'br'];

function buildTextStamp(wm) {
  const bad = unsupportedChars(wm.text);
  if (bad.length) throw Object.assign(new Error(`水印文字含不支持字符 ${JSON.stringify(bad)}（文字水印仅支持 ASCII，中文请改用 Logo 图片水印）`), { code: 'BAD_WATERMARK_TEXT' });
  const scale = Math.max(1, Math.min(12, Math.floor(wm.scale)));
  const t = normalizeText(wm.text);
  const tw = measureText(t, scale), th = textHeight(scale);
  const pad = scale * 2;
  const stamp = new Raster(tw + pad * 2 + scale, th + pad * 2 + scale, null);
  if (wm.shadow) stamp.text(t, pad + scale, pad + scale, FONT_H * scale, '#000000', { alpha: 0.55, bold: true });
  stamp.text(t, pad, pad, FONT_H * scale, wm.color, { bold: true });
  return stamp;
}

function anchorXY(pos, W, H, sw, sh, margin) {
  const horiz = pos[1], vert = pos[0];
  let x = margin, y = margin;
  if (horiz === 'c') x = Math.floor((W - sw) / 2);
  else if (horiz === 'r') x = W - sw - margin;
  if (vert === 'm') y = Math.floor((H - sh) / 2);
  else if (vert === 'b') y = H - sh - margin;
  return [x, y];
}

// 在已渲染好的图纸上叠加水印（就地修改传入 raster 并返回；不依赖外部状态）
export function applyWatermark(raster, options = {}) {
  const wm = { ...WATERMARK_DEFAULTS, ...options };
  if (!wm.enabled) return raster;
  if (!WATERMARK_POSITIONS.includes(wm.position)) {
    throw Object.assign(new Error(`未知水印位置 ${wm.position}`), { code: 'BAD_WATERMARK_POS' });
  }
  const opacity = Math.max(0, Math.min(100, wm.opacity)) / 100;
  if (opacity === 0) return raster;

  let stamp;
  if (wm.type === 'logo') {
    if (!wm.logo || !wm.logo.data) throw Object.assign(new Error('Logo 水印缺少图片数据'), { code: 'BAD_WATERMARK_LOGO' });
    const lw = Math.max(8, Math.min(raster.width, Math.floor(wm.logoWidth)));
    const lh = Math.max(1, Math.round(lw * wm.logo.height / wm.logo.width));
    stamp = new Raster(lw, lh, null);
    stamp.blit(wm.logo.data, wm.logo.width, wm.logo.height, 0, 0, lw, lh, 1);
  } else {
    stamp = buildTextStamp(wm);
  }

  const W = raster.width, H = raster.height;
  const margin = Math.max(0, Math.floor(wm.margin));
  if (wm.tile) {
    const stepX = stamp.width + margin * 2;
    const stepY = stamp.height + margin * 2;
    for (let y = margin; y < H; y += stepY) {
      for (let x = margin; x < W; x += stepX) {
        raster.blit(stamp.data, stamp.width, stamp.height, x, y, stamp.width, stamp.height, opacity);
      }
    }
  } else {
    const [x, y] = anchorXY(wm.position, W, H, stamp.width, stamp.height, margin);
    raster.blit(stamp.data, stamp.width, stamp.height, x, y, stamp.width, stamp.height, opacity);
  }
  return raster;
}