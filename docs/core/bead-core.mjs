// 豆莉塔核心算法 —— 从 Zippland/perler-beads (AGPL-3.0, (c) Zippland) 抽离的无副作用纯函数。
// 来源文件：src/utils/pixelation.ts、src/utils/pixelEditingUtils.ts、src/app/page.tsx
//   (pixelateImage 全局合并 / handleAutoRemoveBackground / handleToggleExcludeColor)、
//   src/utils/colorSystemUtils.ts、src/utils/imageDownloader.ts (CSV/排序/对比色)。
// 原则：算法行为与原版一致，仅去除 console / DOM / Canvas 依赖。禁止在此文件引入平台 API。

import { COLOR_SYSTEM_MAPPING, BRANDS } from './palettes.mjs';

export { COLOR_SYSTEM_MAPPING, BRANDS };

export const TRANSPARENT_KEY = 'ERASE';
export const transparentColorData = Object.freeze({ key: TRANSPARENT_KEY, color: '#FFFFFF', isExternal: true });

export const DEFAULTS = Object.freeze({
  width: 100,           // 线上 2.0 部署版默认 100 格（开源 1.x 源码 granularity 为 50）
  threshold: 30,        // 原版 similarityThreshold 默认 30
  mode: 'dominant',     // dominant | average
  brand: 'MARD',
  metric: 'rgb',        // rgb（线上部署版实际行为，默认）| oklab（开源 HEAD 源码度量，可选）
  maxCells: 1000000,    // 批量安全护栏（新增，不改算法本身）
});

// ---------- 基础 ----------

export function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? { r: parseInt(result[1], 16), g: parseInt(result[2], 16), b: parseInt(result[3], 16) } : null;
}

function srgbChannelToLinear(channel) {
  const normalized = channel / 255;
  return normalized <= 0.04045 ? normalized / 12.92 : Math.pow((normalized + 0.055) / 1.055, 2.4);
}

function rgbToOklab(rgb) {
  const r = srgbChannelToLinear(rgb.r);
  const g = srgbChannelToLinear(rgb.g);
  const b = srgbChannelToLinear(rgb.b);
  const l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b;
  const m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b;
  const s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b;
  const lRoot = Math.cbrt(l), mRoot = Math.cbrt(m), sRoot = Math.cbrt(s);
  return {
    l: 0.2104542553 * lRoot + 0.7936177850 * mRoot - 0.0040720468 * sRoot,
    a: 1.9779984951 * lRoot - 2.4285922050 * mRoot + 0.4505937099 * sRoot,
    b: 0.0259040371 * lRoot + 0.7827717662 * mRoot - 0.8086757660 * sRoot,
  };
}

const oklabCache = new Map();
function getOklabColor(rgb) {
  const cacheKey = `${rgb.r},${rgb.g},${rgb.b}`;
  const cached = oklabCache.get(cacheKey);
  if (cached) return cached;
  const oklab = rgbToOklab(rgb);
  oklabCache.set(cacheKey, oklab);
  return oklab;
}

// Oklab 距离 ×100（开源 HEAD 源码使用；保留为可选度量 metric=oklab）
export function colorDistanceOklab(rgb1, rgb2) {
  const a = getOklabColor(rgb1), b = getOklabColor(rgb2);
  const dl = a.l - b.l, da = a.a - b.a, db = a.b - b.b;
  return Math.sqrt(dl * dl + da * da + db * db) * 100;
}

// RGB 欧氏距离（线上 2.0 部署版实际行为；默认度量 metric=rgb，与线上导出逐格对齐）
export function colorDistanceRgb(rgb1, rgb2) {
  return Math.sqrt((rgb1.r - rgb2.r) ** 2 + (rgb1.g - rgb2.g) ** 2 + (rgb1.b - rgb2.b) ** 2);
}

export const DISTANCE_METRICS = ['rgb', 'oklab'];
export function pickDistance(metric) { return metric === 'oklab' ? colorDistanceOklab : colorDistanceRgb; }
// 向后兼容别名（等价 Oklab 度量）
export const colorDistance = colorDistanceOklab;

export function findClosestPaletteColor(targetRgb, palette, metric = 'rgb') {
  if (!palette || palette.length === 0) {
    return { key: 'ERR', hex: '#000000', rgb: { r: 0, g: 0, b: 0 } };
  }
  const distance = pickDistance(metric);
  let minDistance = Infinity;
  let closestColor = palette[0];
  for (const paletteColor of palette) {
    const d = distance(targetRgb, paletteColor.rgb);
    if (d < minDistance) { minDistance = d; closestColor = paletteColor; }
    if (d === 0) break;
  }
  return closestColor;
}

// ---------- 色板 ----------

// 复刻原版 fullBeadPalette：getMardToHexMapping() -> {key:hex, hex, rgb}
export function buildFullPalette() {
  const mardToHex = {};
  for (const [hex, colorData] of Object.entries(COLOR_SYSTEM_MAPPING)) {
    if (colorData.MARD) mardToHex[colorData.MARD] = hex;
  }
  const palette = [];
  for (const [, hex] of Object.entries(mardToHex)) {
    const rgb = hexToRgb(hex);
    if (!rgb) continue;
    palette.push({ key: hex, hex, rgb });
  }
  return palette;
}

export function getDisplayColorKey(hexValue, colorSystem) {
  if (hexValue === 'ERASE' || hexValue.length === 0 || hexValue === '?') return hexValue;
  const normalizedHex = hexValue.toUpperCase();
  const colorMapping = COLOR_SYSTEM_MAPPING[normalizedHex];
  if (colorMapping && colorMapping[colorSystem]) return colorMapping[colorSystem];
  return '?';
}

export function convertPaletteToColorSystem(palette, colorSystem) {
  return palette.map(color => {
    const colorMapping = COLOR_SYSTEM_MAPPING[color.hex];
    if (colorMapping && colorMapping[colorSystem]) return { ...color, key: colorMapping[colorSystem] };
    return color;
  });
}

// ---------- 像素化（原版 calculatePixelGrid） ----------

function calculateCellRepresentativeColor(image, startX, startY, width, height, mode) {
  const data = image.data;
  const imgWidth = image.width;
  let rSum = 0, gSum = 0, bSum = 0, pixelCount = 0;
  const colorCountsInCell = {};
  let dominantColorRgb = null, maxCount = 0;
  const endX = startX + width, endY = startY + height;
  for (let y = startY; y < endY; y++) {
    for (let x = startX; x < endX; x++) {
      const index = (y * imgWidth + x) * 4;
      if (data[index + 3] < 128) continue; // 忽略半透明以下像素
      const r = data[index], g = data[index + 1], b = data[index + 2];
      pixelCount++;
      if (mode === 'average') {
        rSum += r; gSum += g; bSum += b;
      } else {
        const colorKey = `${r},${g},${b}`;
        colorCountsInCell[colorKey] = (colorCountsInCell[colorKey] || 0) + 1;
        if (colorCountsInCell[colorKey] > maxCount) {
          maxCount = colorCountsInCell[colorKey];
          dominantColorRgb = { r, g, b };
        }
      }
    }
  }
  if (pixelCount === 0) return null;
  if (mode === 'average') {
    return { r: Math.round(rSum / pixelCount), g: Math.round(gSum / pixelCount), b: Math.round(bSum / pixelCount) };
  }
  return dominantColorRgb;
}

export function calculatePixelGrid(image, N, M, palette, mode, t1FallbackColor, metric = 'rgb') {
  const imgWidth = image.width, imgHeight = image.height;
  const mappedData = Array(M).fill(null).map(() =>
    Array(N).fill({ key: t1FallbackColor.key, color: t1FallbackColor.hex }));
  const cellWidthOriginal = imgWidth / N;
  const cellHeightOriginal = imgHeight / M;
  for (let j = 0; j < M; j++) {
    for (let i = 0; i < N; i++) {
      const startXOriginal = Math.floor(i * cellWidthOriginal);
      const startYOriginal = Math.floor(j * cellHeightOriginal);
      const endXOriginal = Math.min(imgWidth, Math.ceil((i + 1) * cellWidthOriginal));
      const endYOriginal = Math.min(imgHeight, Math.ceil((j + 1) * cellHeightOriginal));
      const currentCellWidth = Math.max(1, endXOriginal - startXOriginal);
      const currentCellHeight = Math.max(1, endYOriginal - startYOriginal);
      const representativeRgb = calculateCellRepresentativeColor(
        image, startXOriginal, startYOriginal, currentCellWidth, currentCellHeight, mode);
      if (representativeRgb) {
        const closestBead = findClosestPaletteColor(representativeRgb, palette, metric);
        mappedData[j][i] = { key: closestBead.key, color: closestBead.hex };
      } else {
        mappedData[j][i] = { ...transparentColorData };
      }
    }
  }
  return mappedData;
}

// ---------- 全局颜色合并（原版 pixelateImage 内联逻辑） ----------

export function mergeSimilarColors(initialMappedData, palette, threshold, metric = 'rgb') {
  const M = initialMappedData.length, N = initialMappedData[0].length;
  const keyToRgbMap = new Map(), keyToColorDataMap = new Map();
  palette.forEach(p => { keyToRgbMap.set(p.key, p.rgb); keyToColorDataMap.set(p.key, p); });
  const distance = pickDistance(metric);

  const initialColorCounts = {};
  initialMappedData.flat().forEach(cell => {
    if (cell && cell.key && !cell.isExternal && cell.key !== TRANSPARENT_KEY) {
      initialColorCounts[cell.key] = (initialColorCounts[cell.key] || 0) + 1;
    }
  });
  const colorsByFrequency = Object.entries(initialColorCounts)
    .sort((a, b) => b[1] - a[1])
    .map(entry => entry[0]);

  const mergedData = initialMappedData.map(row =>
    row.map(cell => ({ ...cell, isExternal: cell.isExternal ?? false })));

  const replacedColors = new Set();
  for (let i = 0; i < colorsByFrequency.length; i++) {
    const currentKey = colorsByFrequency[i];
    if (replacedColors.has(currentKey)) continue;
    const currentRgb = keyToRgbMap.get(currentKey);
    if (!currentRgb) continue;
    for (let j = i + 1; j < colorsByFrequency.length; j++) {
      const lowerFreqKey = colorsByFrequency[j];
      if (replacedColors.has(lowerFreqKey)) continue;
      const lowerFreqRgb = keyToRgbMap.get(lowerFreqKey);
      if (!lowerFreqRgb) continue;
      const dist = distance(currentRgb, lowerFreqRgb);
      if (dist < threshold) {
        replacedColors.add(lowerFreqKey);
        const colorData = keyToColorDataMap.get(currentKey);
        if (colorData) {
          for (let r = 0; r < M; r++) {
            for (let c = 0; c < N; c++) {
              if (mergedData[r][c].key === lowerFreqKey) {
                mergedData[r][c] = { key: currentKey, color: colorData.hex, isExternal: false };
              }
            }
          }
        }
      }
    }
  }
  return { grid: mergedData, mergedColorCount: replacedColors.size };
}

// ---------- 一键去背景（原版 handleAutoRemoveBackground） ----------

export function removeBackground(mappedPixelData) {
  const M = mappedPixelData.length, N = mappedPixelData[0].length;
  const borderCounts = new Map();
  const countBorderCell = (row, col) => {
    const cell = mappedPixelData[row]?.[col];
    if (!cell || cell.isExternal || cell.key === TRANSPARENT_KEY) return;
    borderCounts.set(cell.key, (borderCounts.get(cell.key) || 0) + 1);
  };
  for (let col = 0; col < N; col++) { countBorderCell(0, col); if (M > 1) countBorderCell(M - 1, col); }
  for (let row = 1; row < M - 1; row++) { countBorderCell(row, 0); if (N > 1) countBorderCell(row, N - 1); }
  if (borderCounts.size === 0) return { grid: mappedPixelData, removed: 0, reason: 'NO_BORDER_COLOR' };

  let targetKey = '', maxCount = -1;
  borderCounts.forEach((count, key) => { if (count > maxCount) { maxCount = count; targetKey = key; } });

  const newPixelData = mappedPixelData.map(row => row.map(cell => ({ ...cell })));
  const visited = Array(M).fill(null).map(() => Array(N).fill(false));
  const stack = [];
  const pushIfTarget = (row, col) => {
    if (row < 0 || row >= M || col < 0 || col >= N || visited[row][col]) return;
    const cell = newPixelData[row][col];
    if (!cell || cell.isExternal || cell.key !== targetKey) return;
    visited[row][col] = true;
    stack.push({ row, col });
  };
  for (let col = 0; col < N; col++) { pushIfTarget(0, col); if (M > 1) pushIfTarget(M - 1, col); }
  for (let row = 1; row < M - 1; row++) { pushIfTarget(row, 0); if (N > 1) pushIfTarget(row, N - 1); }
  if (stack.length === 0) return { grid: mappedPixelData, removed: 0, reason: 'NO_REGION' };

  let removed = 0;
  while (stack.length > 0) {
    const { row, col } = stack.pop();
    newPixelData[row][col] = { ...transparentColorData };
    removed++;
    pushIfTarget(row - 1, col); pushIfTarget(row + 1, col);
    pushIfTarget(row, col - 1); pushIfTarget(row, col + 1);
  }
  return { grid: newPixelData, removed, targetKey };
}

// ---------- 统计（原版 recalculateColorStats / pixelateImage 计数） ----------

export function recalculateColorStats(pixelData) {
  const colorCounts = {};
  let totalCount = 0;
  pixelData.flat().forEach(cell => {
    if (cell && !cell.isExternal && cell.key !== TRANSPARENT_KEY) {
      const cellHex = cell.color.toUpperCase();
      if (!colorCounts[cellHex]) colorCounts[cellHex] = { count: 0, color: cellHex };
      colorCounts[cellHex].count++;
      totalCount++;
    }
  });
  return { colorCounts, totalCount };
}

// ---------- 颜色排除与重映射（原版 handleToggleExcludeColor） ----------

export function excludeColorFromGrid(mappedPixelData, initialGridColorKeys, excludedColorKeys, hexKey, fullPalette, metric = 'rgb') {
  const nextExcludedKeys = new Set(excludedColorKeys);
  nextExcludedKeys.add(hexKey);
  const potentialRemapHexKeys = new Set(initialGridColorKeys);
  potentialRemapHexKeys.delete(hexKey);
  excludedColorKeys.forEach(k => potentialRemapHexKeys.delete(k));
  const remapTargetPalette = fullPalette.filter(color => potentialRemapHexKeys.has(color.hex.toUpperCase()));
  if (remapTargetPalette.length === 0) {
    return { ok: false, error: 'NO_REMAP_TARGET', message: `无法排除 ${hexKey}：图中其余初始颜色也已被排除，请先恢复部分颜色。` };
  }
  const excludedColorData = fullPalette.find(p => p.hex.toUpperCase() === hexKey);
  if (!excludedColorData) {
    return { ok: false, error: 'COLOR_NOT_FOUND', message: `色板中不存在 ${hexKey}。` };
  }
  const M = mappedPixelData.length, N = mappedPixelData[0].length;
  const newMappedData = mappedPixelData.map(row => row.map(cell => ({ ...cell })));
  let remappedCount = 0;
  for (let j = 0; j < M; j++) {
    for (let i = 0; i < N; i++) {
      const cell = newMappedData[j]?.[i];
      if (cell && !cell.isExternal && cell.color.toUpperCase() === hexKey) {
        const replacementColor = findClosestPaletteColor(excludedColorData.rgb, remapTargetPalette, metric);
        newMappedData[j][i] = { ...cell, key: replacementColor.key, color: replacementColor.hex };
        remappedCount++;
      }
    }
  }
  const { colorCounts, totalCount } = recalculateColorStats(newMappedData);
  return { ok: true, grid: newMappedData, excluded: nextExcludedKeys, colorCounts, totalCount, remappedCount };
}

// ---------- 排序 / 对比色（原版 imageDownloader / page.tsx） ----------

export function sortColorKeys(a, b) {
  const regex = /^([A-Z]+)(\d+)$/;
  const matchA = a.match(regex), matchB = b.match(regex);
  if (matchA && matchB) {
    const prefixA = matchA[1], numA = parseInt(matchA[2], 10);
    const prefixB = matchB[1], numB = parseInt(matchB[2], 10);
    if (prefixA !== prefixB) return prefixA.localeCompare(prefixB);
    return numA - numB;
  }
  return a.localeCompare(b);
}

export function getContrastColor(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return '#000000';
  const luma = (0.2126 * rgb.r + 0.7152 * rgb.g + 0.0722 * rgb.b) / 255;
  return luma > 0.5 ? '#000000' : '#FFFFFF';
}

// ---------- 主流水线（组合以上纯函数，行为对齐原版 pixelateImage） ----------

export function convertImage(image, opts = {}) {
  if (!image || !image.data || !(image.width > 0) || !(image.height > 0)) {
    const e = new Error('无效图像数据'); e.code = 'BAD_IMAGE'; throw e;
  }
  const width = opts.width ?? DEFAULTS.width;
  const threshold = opts.threshold ?? DEFAULTS.threshold;
  const mode = opts.mode ?? DEFAULTS.mode;
  const brand = opts.brand ?? DEFAULTS.brand;
  if (!Number.isInteger(width) || width < 1 || width > 2000) {
    const e = new Error(`格数 width 必须是 1-2000 的整数，收到 ${width}`); e.code = 'BAD_WIDTH'; throw e;
  }
  if (!['dominant', 'average'].includes(mode)) {
    const e = new Error(`未知模式 ${mode}`); e.code = 'BAD_MODE'; throw e;
  }
  if (!BRANDS.includes(brand)) {
    const e = new Error(`未知品牌 ${brand}，可选：${BRANDS.join(' / ')}`); e.code = 'BAD_BRAND'; throw e;
  }
  const metric = opts.metric ?? DEFAULTS.metric;
  if (!DISTANCE_METRICS.includes(metric)) {
    const e = new Error(`未知色距度量 ${metric}，可选：${DISTANCE_METRICS.join(' / ')}`); e.code = 'BAD_METRIC'; throw e;
  }
  const fullPalette = buildFullPalette();
  let palette = fullPalette;
  if (Array.isArray(opts.hexList) && opts.hexList.length > 0) {
    const allow = new Set(opts.hexList.map(h => h.toUpperCase()));
    palette = fullPalette.filter(p => allow.has(p.hex.toUpperCase()));
    if (palette.length === 0) {
      const e = new Error('自定义色板为空'); e.code = 'EMPTY_PALETTE'; throw e;
    }
  }
  const N = width;
  const M = Math.max(1, Math.round(N * (image.height / image.width)));
  const maxCells = opts.maxCells ?? DEFAULTS.maxCells;
  if (N * M > maxCells) {
    const e = new Error(`网格 ${N}x${M} 超过上限 ${maxCells} 格（极端比例保护），请减小 width 或提高 maxCells`);
    e.code = 'GRID_TOO_LARGE'; throw e;
  }
  const t1FallbackColor = palette.find(p => p.key === 'T1')
    || palette.find(p => p.hex.toUpperCase() === '#FFFFFF')
    || palette[0];

  const initialGrid = calculatePixelGrid(image, N, M, palette, mode, t1FallbackColor, metric);
  const { grid: mergedGrid, mergedColorCount } = mergeSimilarColors(initialGrid, palette, threshold, metric);

  let grid = mergedGrid;
  let backgroundRemoved = 0;
  if (opts.removeBackground) {
    const r = removeBackground(mergedGrid);
    grid = r.grid;
    backgroundRemoved = r.removed;
  }
  const { colorCounts, totalCount } = recalculateColorStats(grid);
  return {
    grid, N, M, brand, mode, threshold, metric,
    colorCounts, totalBeads: totalCount,
    initialGridColorKeys: Object.keys(colorCounts),
    paletteSize: palette.length,
    mergedColorCount, backgroundRemoved,
  };
}

// ---------- 导出辅助（纯数据） ----------

export function exportCsvString(mappedPixelData) {
  const M = mappedPixelData.length, N = mappedPixelData[0].length;
  const csvLines = [];
  for (let row = 0; row < M; row++) {
    const rowData = [];
    for (let col = 0; col < N; col++) {
      const cellData = mappedPixelData[row][col];
      rowData.push(cellData && !cellData.isExternal ? cellData.color : 'TRANSPARENT');
    }
    csvLines.push(rowData.join(','));
  }
  return csvLines.join('\n');
}

export function buildManifest(result, meta = {}) {
  const items = Object.entries(result.colorCounts)
    .map(([hex, v]) => ({ hex, code: getDisplayColorKey(hex, result.brand), count: v.count }))
    .sort((a, b) => sortColorKeys(a.code, b.code));
  return {
    generator: 'DOLITA 0.1.0',
    source: meta.name ?? null,
    grid: { cols: result.N, rows: result.M },
    brand: result.brand,
    mode: result.mode,
    threshold: result.threshold,
    colorCount: items.length,
    totalBeads: result.totalBeads,
    backgroundRemoved: result.backgroundRemoved,
    mergedColorCount: result.mergedColorCount,
    colors: items,
    createdAt: meta.createdAt ?? null,
  };
}