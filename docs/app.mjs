// 豆莉塔工作台 · 架构师核心代码
// 铁律：图片解码只走 core/image-io（与 CLI 同一份代码），禁止用 canvas 解码，否则破坏逐像素等价。
import {
  DEFAULTS, buildFullPalette, convertImage, excludeColorFromGrid,
  recalculateColorStats, getDisplayColorKey, sortColorKeys,
  buildManifest, transparentColorData, TRANSPARENT_KEY,
} from './core/bead-core.mjs';
import { BRANDS } from './core/palettes.mjs';
import { decodeImage, encodeImagePNG } from './core/image-io.mjs';
import { renderPreview, renderSheet, applyWatermark, WATERMARK_POSITIONS } from './core/render.mjs';
import { platform } from './core/platform-browser.mjs';

const $ = id => document.getElementById(id);
const fullPalette = buildFullPalette();
const paletteByHex = new Map(fullPalette.map(p => [p.hex.toUpperCase(), p]));

const state = {
  file: null, sourceImage: null,
  opts: { width: DEFAULTS.width, threshold: DEFAULTS.threshold, mode: DEFAULTS.mode, brand: DEFAULTS.brand, removeBackground: false },
  baseResult: null, result: null, excluded: new Set(),
  logoImage: null,
  wm: { enabled: false, type: 'text', text: '@DOLITA', scale: 2, color: '#16211B', opacity: 70, position: 'br', margin: 16, tile: false, shadow: true, logoWidth: 160 },
  donate: null, donateTab: 'wechat', donateAmount: null,
  cell: null, previewCell: 12,
  siteUrl: '',
};

/* ================= 工具 ================= */
const ERR_MSG = {
  BAD_IMAGE: '图片数据无效或已损坏', BAD_WIDTH: '格数必须是 1 到 2000 的整数',
  GRID_TOO_LARGE: '网格太大（极端比例保护），请减小格数', UNSUPPORTED_PNG: '暂不支持 16 位 PNG，请转成 8 位 PNG',
  UNSUPPORTED_BMP: '暂不支持压缩 BMP，请转成 PNG', UNSUPPORTED_FORMAT: '只收 PNG / JPEG / BMP，WebP 和 GIF 请先转 PNG',
  BAD_WATERMARK_TEXT: '文字水印只支持英文和数字，中文请改用 Logo 图片', BAD_WATERMARK_LOGO: '请先选择一张 Logo 图片',
  BAD_WATERMARK_POS: '水印位置无效', BAD_SHEET_TEXT: '左上角标只支持英文和数字，中文请写进标题/副标题',
  NO_REMAP_TARGET: '其余颜色也都被排除了，先恢复几个再试', BODY_TOO_LARGE: '文件太大',
};
function friendly(err) { return ERR_MSG[err?.code] || err?.message || '出了点问题，请重试'; }
function toast(msg, isError = false) {
  const el = document.createElement('div');
  el.className = 'toast' + (isError ? ' error' : '');
  el.textContent = msg;
  $('toastRegion').appendChild(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 400); }, 3200);
}
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
function download(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}
function baseName() { return (state.file?.name || 'pattern').replace(/\.[^.]+$/, ''); }
function rasterToCanvas(raster, canvas) {
  canvas.width = raster.width; canvas.height = raster.height;
  const ctx = canvas.getContext('2d');
  const data = raster.data instanceof Uint8ClampedArray ? raster.data : new Uint8ClampedArray(raster.data);
  ctx.putImageData(new ImageData(data, raster.width, raster.height), 0, 0);
}

/* ================= 上传 ================= */
// 浏览器原生解码：与线上站同一份像素（img 解码 → canvas drawImage → getImageData）
// 这样 JPEG/WebP/GIF/带 ICC 的 PNG 的解码结果都和线上逐像素一致，不再取决于自研解码器
async function decodeImageNative(file) {
  const dataUrl = await new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(fr.result);
    fr.onerror = () => rej(Object.assign(new Error('读取文件失败'), { code: 'BAD_IMAGE' }));
    fr.readAsDataURL(file);
  });
  const img = new Image();
  await new Promise((res, rej) => {
    img.onload = () => res();
    img.onerror = () => rej(Object.assign(new Error('图片解码失败，请换一张图或转成 PNG'), { code: 'BAD_IMAGE' }));
    img.src = dataUrl;
  });
  const w = img.naturalWidth, h = img.naturalHeight;
  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, w, h);
  return { width: w, height: h, data: ctx.getImageData(0, 0, w, h).data };
}

async function handleFile(file) {
  if (!file) return;
  $('uploadError').hidden = true;
  try {
    const image = await decodeImageNative(file);
    state.file = file; state.sourceImage = image;
    state.excluded = new Set(); state.cell = null;
    $('fileMeta').hidden = false;
    $('fileMeta').innerHTML = '';
    const thumb = document.createElement('img');
    thumb.src = URL.createObjectURL(file); thumb.alt = '原图缩略图';
    const info = document.createElement('div');
    const nm = document.createElement('div'); nm.className = 'fm-name'; nm.textContent = file.name;
    const sub = document.createElement('div'); sub.className = 'fm-sub';
    sub.textContent = `${image.width} × ${image.height} px · ${(file.size / 1024).toFixed(0)} KB`;
    info.append(nm, sub); $('fileMeta').append(thumb, info);
    ['controlsCard', 'paletteCard', 'exportCard', 'wmCard'].forEach(id => { $(id).hidden = false; });
    recompute();
    toast('图片已在本地解码，开始拼豆');
  } catch (err) {
    $('uploadError').textContent = friendly(err);
    $('uploadError').hidden = false;
    toast(friendly(err), true);
  }
}
const dz = $('dropzone'), fi = $('fileInput');
dz.addEventListener('click', () => fi.click());
dz.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fi.click(); } });
fi.addEventListener('change', () => handleFile(fi.files[0]));
['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('drag'); }));
['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('drag'); }));
dz.addEventListener('drop', e => handleFile(e.dataTransfer.files[0]));
window.addEventListener('paste', e => { const f = e.clipboardData?.files?.[0]; if (f) handleFile(f); });

/* ================= 参数与重算 ================= */
const brandSel = $('brandSelect');
BRANDS.forEach(b => { const o = document.createElement('option'); o.value = b; o.textContent = b; brandSel.appendChild(o); });
brandSel.value = state.opts.brand;

function recompute() {
  if (!state.sourceImage) return;
  try {
    state.baseResult = convertImage(state.sourceImage, state.opts);
    state.result = state.baseResult;
    state.excluded = new Set();
    renderAll();
  } catch (err) { toast(friendly(err), true); }
}
const recomputeDebounced = debounce(recompute, 200);
$('widthRange').addEventListener('input', e => { state.opts.width = +e.target.value; $('widthOut').textContent = e.target.value; recomputeDebounced(); });
$('thresholdRange').addEventListener('input', e => { state.opts.threshold = +e.target.value; $('thresholdOut').textContent = e.target.value; recomputeDebounced(); });
document.querySelectorAll('[data-preset]').forEach(b => b.addEventListener('click', () => {
  if (b.dataset.preset !== 'reference') return;
  state.opts.width = 100; state.opts.threshold = 0;
  $('widthRange').value = 100; $('widthOut').textContent = 100;
  $('thresholdRange').value = 0; $('thresholdOut').textContent = 0;
  $('optNumbers').checked = false;
  recompute();
  toast('已切到复刻参考图：100 格、不合并、格内不印色号');
}));
$('modeSelect').addEventListener('change', e => { state.opts.mode = e.target.value; recompute(); });
document.querySelectorAll('[data-threshold]').forEach(b => b.addEventListener('click', () => {
  const v = +b.dataset.threshold;
  state.opts.threshold = v;
  $('thresholdRange').value = v; $('thresholdOut').textContent = v;
  recompute();
  toast(v === 10 ? '已切到成品风格（阈值 10，颜色更丰富）' : '已切回原版默认（阈值 30）');
}));
brandSel.addEventListener('change', e => { state.opts.brand = e.target.value; recompute(); });
$('bgRemoveBtn').addEventListener('click', () => {
  state.opts.removeBackground = !state.opts.removeBackground;
  $('bgRemoveBtn').setAttribute('aria-pressed', String(state.opts.removeBackground));
  recompute();
  if (state.opts.removeBackground && state.result) toast(`已剥离背景 ${state.result.backgroundRemoved} 格`);
});
$('resetBtn').addEventListener('click', () => {
  state.opts = { width: DEFAULTS.width, threshold: DEFAULTS.threshold, mode: DEFAULTS.mode, brand: DEFAULTS.brand, removeBackground: false };
  $('widthRange').value = state.opts.width; $('widthOut').textContent = state.opts.width;
  $('thresholdRange').value = state.opts.threshold; $('thresholdOut').textContent = state.opts.threshold;
  $('modeSelect').value = state.opts.mode; brandSel.value = state.opts.brand;
  $('bgRemoveBtn').setAttribute('aria-pressed', 'false');
  recompute(); toast('参数已重置');
});

/* ================= 渲染 ================= */
function renderAll() { renderPreviewStage(); renderPalette(); renderStats(); scheduleWmPreview(); }
function renderPreviewStage() {
  const r = state.result; if (!r) return;
  $('stageEmpty').hidden = true; $('stageWrap').hidden = false; $('statsBar').hidden = false;
  state.previewCell = Math.max(3, Math.min(14, Math.floor(1000 / r.N)));
  rasterToCanvas(renderPreview(r, state.previewCell), $('previewCanvas'));
}
function renderStats() {
  const r = state.result; if (!r) return;
  $('statGrid').textContent = `${r.N} × ${r.M}`;
  $('statBeads').textContent = r.totalBeads.toLocaleString();
  $('statColors').textContent = Object.keys(r.colorCounts).length;
  $('statSize').textContent = `${(r.N * 0.5).toFixed(1)} × ${(r.M * 0.5).toFixed(1)} cm`;
}
function renderPalette() {
  const r = state.result; if (!r) return;
  const list = $('paletteList'); list.innerHTML = '';
  const entries = Object.entries(r.colorCounts).sort((a, b) => sortColorKeys(getDisplayColorKey(a[0], r.brand), getDisplayColorKey(b[0], r.brand)));
  $('paletteSummary').textContent = `${entries.length} 色 · ${r.totalBeads.toLocaleString()} 颗`;
  for (const [hex, v] of entries) {
    const li = document.createElement('li');
    const sw = document.createElement('span'); sw.className = 'swatch'; sw.style.background = hex;
    const code = document.createElement('span'); code.className = 'pal-code'; code.textContent = getDisplayColorKey(hex, r.brand);
    const hx = document.createElement('span'); hx.className = 'pal-hex'; hx.textContent = hex;
    const ct = document.createElement('span'); ct.className = 'pal-count'; ct.textContent = v.count.toLocaleString();
    const ex = document.createElement('button'); ex.className = 'pal-exclude'; ex.type = 'button'; ex.textContent = '排除';
    ex.addEventListener('click', () => excludeColor(hex));
    li.append(sw, code, hx, ct, ex); list.appendChild(li);
  }
  $('restoreColorsBtn').hidden = state.excluded.size === 0;
}
function excludeColor(hex) {
  const r = state.result;
  const res = excludeColorFromGrid(r.grid, state.baseResult.initialGridColorKeys, state.excluded, hex, fullPalette);
  if (!res.ok) { toast(res.message || friendly({ code: res.error }), true); return; }
  r.grid = res.grid; r.colorCounts = res.colorCounts; r.totalBeads = res.totalCount;
  state.excluded = res.excluded;
  renderAll(); toast(`已排除 ${hex}，重新映射 ${res.remappedCount} 格`);
}
$('restoreColorsBtn').addEventListener('click', () => {
  state.result = state.baseResult; state.excluded = new Set();
  renderAll(); toast('已恢复全部颜色');
});

/* ================= 单格改色 ================= */
const pop = $('cellPop'), cellSel = $('cellColorSelect');
fullPalette.slice().sort((a, b) => sortColorKeys(getDisplayColorKey(a.hex, 'MARD'), getDisplayColorKey(b.hex, 'MARD')))
  .forEach(p => { const o = document.createElement('option'); o.value = p.hex; o.textContent = `${getDisplayColorKey(p.hex, 'MARD')} · ${p.hex}`; cellSel.appendChild(o); });
const eraseOpt = document.createElement('option'); eraseOpt.value = TRANSPARENT_KEY; eraseOpt.textContent = '空白（不拼）'; cellSel.appendChild(eraseOpt);

$('previewCanvas').addEventListener('click', e => {
  const r = state.result; if (!r) return;
  const rect = e.target.getBoundingClientRect();
  const col = Math.floor((e.clientX - rect.left) / state.previewCell);
  const row = Math.floor((e.clientY - rect.top) / state.previewCell);
  if (row < 0 || row >= r.M || col < 0 || col >= r.N) return;
  state.cell = { row, col };
  $('cellCoord').textContent = `(${col + 1}, ${row + 1})`;
  const cur = r.grid[row][col];
  cellSel.value = cur && !cur.isExternal ? cur.color.toUpperCase() : TRANSPARENT_KEY;
  const wrap = $('stageWrap');
  pop.hidden = false;
  const px = Math.min(e.clientX - wrap.getBoundingClientRect().left + wrap.scrollLeft + 12, wrap.scrollWidth - 240);
  const py = Math.min(e.clientY - wrap.getBoundingClientRect().top + wrap.scrollTop + 12, wrap.scrollHeight - 160);
  pop.style.left = Math.max(8, px) + 'px'; pop.style.top = Math.max(8, py) + 'px';
  cellSel.focus();
});
$('cellCancelBtn').addEventListener('click', () => { pop.hidden = true; state.cell = null; });
$('cellApplyBtn').addEventListener('click', () => {
  const r = state.result; if (!r || !state.cell) return;
  const { row, col } = state.cell; const val = cellSel.value;
  r.grid[row][col] = val === TRANSPARENT_KEY ? { ...transparentColorData } : { ...paletteByHex.get(val) };
  const s = recalculateColorStats(r.grid);
  r.colorCounts = s.colorCounts; r.totalBeads = s.totalCount;
  pop.hidden = true; state.cell = null;
  renderAll(); toast('已改色');
});

/* ================= 导出 ================= */
function sheetOpts() {
  return {
    showGrid: $('optGrid').checked,
    gridInterval: Math.max(1, +$('optInterval').value || 10),
    gridLineColor: $('optGridColor').value,
    showCoordinates: $('optCoords').checked,
    showCellNumbers: $('optNumbers').checked,
    includeStats: $('optStats').checked,
    markText: $('optMark').checked ? '@DOLITA' : null,
    author: ($('dlAuthor').value || '').trim(),
    shareCode: ($('dlCode').value || '').trim(),
    qrUrl: state.siteUrl,
  };
}
function wmOpts() {
  return { ...state.wm, logo: state.wm.type === 'logo' ? state.logoImage : null };
}
async function exportPng() {
  const r = state.result; if (!r) return;
  const btn = $('exportPngBtn'); btn.disabled = true; btn.textContent = '渲染中…';
  await new Promise(res => setTimeout(res, 30));
  try {
    const raster = renderSheet(r, sheetOpts());
    applyWatermark(raster, wmOpts());
    const png = await encodeImagePNG(raster, platform);
    download(new Blob([png], { type: 'image/png' }), `${baseName()}-图纸.png`);
    $('exportHint').textContent = `图纸 ${raster.width} × ${raster.height} px，与命令行输出逐像素一致。`;
    toast('图纸已导出');
    closeDl();
  } catch (err) { toast(friendly(err), true); }
  finally { btn.disabled = false; btn.textContent = '生成图纸'; }
}
$('exportPngBtn').addEventListener('click', exportPng);

/* ===== 下载设置抽屉 ===== */
const dlOverlay = $('dlOverlay');
const dlCard = dlOverlay.querySelector('.dl-card');
function openDl() {
  if (!state.result) return;
  dlOverlay.hidden = false;
  dlOverlay.classList.add('show');
  dlOverlay.style.opacity = '1';
  dlCard.style.opacity = '1';
  dlCard.style.transform = 'translateY(0)';
}
function closeDl() {
  dlOverlay.classList.remove('show');
  dlOverlay.style.opacity = '0';
  dlCard.style.opacity = '0';
  dlCard.style.transform = 'translateY(24px)';
  setTimeout(() => { dlOverlay.hidden = true; }, 220);
}
$('openDownloadBtn').addEventListener('click', openDl);
$('dlClose').addEventListener('click', closeDl);
dlOverlay.addEventListener('click', e => { if (e.target === dlOverlay) closeDl(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !dlOverlay.hidden) closeDl(); });

// 网格线颜色圆点
const SWATCHES = ['#555555', '#FF0000', '#0000FF', '#008000', '#800080', '#FFA500'];
const swWrap = $('dlSwatches'), gridColorSel = $('optGridColor');
SWATCHES.forEach(c => {
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'swatch'; b.dataset.color = c;
  b.style.background = c; b.title = c;
  b.setAttribute('role', 'radio');
  b.setAttribute('aria-checked', String(c === gridColorSel.value));
  b.addEventListener('click', () => {
    gridColorSel.value = c;
    swWrap.querySelectorAll('.swatch').forEach(x => x.setAttribute('aria-checked', String(x.dataset.color === c)));
    scheduleWmPreview();
  });
  swWrap.appendChild(b);
});

$('optInterval').addEventListener('input', e => { $('dlIntervalOut').textContent = e.target.value; });
$('optGrid').addEventListener('change', e => { $('dlGridSub').style.opacity = e.target.checked ? '1' : '0.45'; });

$('exportSourceBtn').addEventListener('click', () => {
  const r = state.result; if (!r) return;
  const src = {
    name: state.file?.name || null,
    width: r.N, height: r.M,
    brand: r.brand,
    palette: Object.entries(r.colorCounts).map(([hex, v]) => ({ hex, code: getDisplayColorKey(hex, r.brand), count: v.count })),
    grid: r.grid.map(row => row.map(c => (c && c.isExternal ? null : (c?.key || c?.color || null)))),
  };
  download(new Blob([JSON.stringify(src, null, 2)], { type: 'application/json' }), `${baseName()}-源数据.json`);
  toast('源数据已导出');
});

$('exportCsvBtn').addEventListener('click', () => {
  const r = state.result; if (!r) return;
  const rows = [['色号', 'HEX', '颗数']];
  Object.entries(r.colorCounts)
    .sort((a, b) => sortColorKeys(getDisplayColorKey(a[0], r.brand), getDisplayColorKey(b[0], r.brand)))
    .forEach(([hex, v]) => rows.push([getDisplayColorKey(hex, r.brand), hex, v.count]));
  rows.push(['合计', '', r.totalBeads]);
  download(new Blob(['\uFEFF' + rows.map(x => x.join(',')).join('\r\n')], { type: 'text/csv' }), `${baseName()}-采购清单.csv`);
  toast('采购清单已导出');
});
$('exportJsonBtn').addEventListener('click', () => {
  const r = state.result; if (!r) return;
  const manifest = buildManifest(r, { name: state.file?.name, createdAt: new Date().toISOString() });
  download(new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' }), `${baseName()}-manifest.json`);
  toast('清单 JSON 已导出');
});
['optGrid', 'optInterval', 'optGridColor', 'optCoords', 'optNumbers', 'optStats', 'optMark'].forEach(id => $(id).addEventListener('change', scheduleWmPreview));

/* ================= 水印面板 ================= */
const posGrid = $('wmPosGrid');
const POS_LABEL = { tl: '左上', tc: '上中', tr: '右上', ml: '左中', mc: '正中', mr: '右中', bl: '左下', bc: '下中', br: '右下' };
WATERMARK_POSITIONS.forEach(p => {
  const b = document.createElement('button'); b.type = 'button'; b.dataset.pos = p;
  b.setAttribute('role', 'radio'); b.setAttribute('aria-checked', String(p === state.wm.position));
  b.setAttribute('aria-label', POS_LABEL[p]); b.title = POS_LABEL[p];
  b.addEventListener('click', () => {
    state.wm.position = p;
    posGrid.querySelectorAll('button').forEach(x => x.setAttribute('aria-checked', String(x.dataset.pos === p)));
    scheduleWmPreview();
  });
  posGrid.appendChild(b);
});
$('wmEnable').addEventListener('change', e => { state.wm.enabled = e.target.checked; $('wmBody').hidden = !e.target.checked; scheduleWmPreview(); });
document.querySelectorAll('input[name="wmType"]').forEach(r => r.addEventListener('change', e => {
  state.wm.type = e.target.value;
  $('wmTextField').hidden = state.wm.type !== 'text';
  $('wmColorField').hidden = state.wm.type !== 'text';
  $('wmLogoField').hidden = state.wm.type !== 'logo';
  scheduleWmPreview();
}));
$('wmText').addEventListener('input', e => { state.wm.text = e.target.value; scheduleWmPreview(); });
$('wmOpacity').addEventListener('input', e => { state.wm.opacity = +e.target.value; $('wmOpacityOut').textContent = e.target.value + '%'; scheduleWmPreview(); });
$('wmColor').addEventListener('input', e => { state.wm.color = e.target.value; scheduleWmPreview(); });
$('wmTile').addEventListener('change', e => { state.wm.tile = e.target.checked; scheduleWmPreview(); });
$('wmLogoWidth').addEventListener('input', e => { state.wm.logoWidth = +e.target.value; $('wmLogoWidthOut').textContent = e.target.value + ' px'; scheduleWmPreview(); });
$('wmLogoInput').addEventListener('change', async e => {
  const f = e.target.files[0]; if (!f) return;
  try { state.logoImage = await decodeImage(new Uint8Array(await f.arrayBuffer()), platform); scheduleWmPreview(); toast('Logo 已加载'); }
  catch (err) { toast(friendly(err), true); }
});
function scheduleWmPreview() { clearTimeout(scheduleWmPreview._t); scheduleWmPreview._t = setTimeout(renderWmPreview, 150); }
function renderWmPreview() {
  const r = state.result; if (!r || !state.wm.enabled) return;
  $('wmError').hidden = true;
  try {
    const small = renderSheet(r, { ...sheetOpts(), cellSize: 8 });
    applyWatermark(small, wmOpts());
    rasterToCanvas(small, $('wmPreview'));
  } catch (err) { $('wmError').textContent = friendly(err); $('wmError').hidden = false; }
}

/* ================= 打赏弹窗 ================= */
const DONATE_FALLBACK = {
  enabled: true,
  authorName: '豆莉塔作者',
  avatarText: '豆',
  avatar: null,
  message: '如果豆莉塔帮你省了时间，欢迎赞赏支持。完全自愿，不影响任何功能。',
  wechat: 'public/wechat-qr.png',
  alipay: 'public/alipay-qr.png',
  alipayByAmount: {
    1: 'public/alipay-1.png', 5: 'public/alipay-5.png', 10: 'public/alipay-10.png',
    20: 'public/alipay-20.png', 50: 'public/alipay-50.png', 100: 'public/alipay-100.png', 200: 'public/alipay-200.png',
  },
  alipayCustom: 'public/alipay-qr.png',
  customLabel: '自选金额',
  wechatLabel: '微信赞赏',
  alipayLabel: '支付宝',
  amounts: [1, 5, 10, 20, 50, 100, 200],
  defaultAmount: 10,
  wechatHint: '请使用微信扫码赞赏',
  alipayHint: '请使用支付宝扫码，支付金额：{amount} 元',
  alipayCustomHint: '请使用支付宝扫码，并手动输入金额',
  contact: '联系作者：微信 / 邮箱 待补充',
  note: '赞赏完全自愿，不影响任何功能。',
};
function donateCfg() { return state.donate || DONATE_FALLBACK; }
function amountLabel(n) { return `${n} 元`; }
function alipayQrFor(amount) {
  const d = donateCfg();
  if (amount === 'custom') return d.alipayCustom || d.alipay || DONATE_FALLBACK.alipayCustom;
  const map = d.alipayByAmount || {};
  return map[String(amount)] || d.alipay || DONATE_FALLBACK.alipay;
}
function refreshDonateQr() {
  const d = donateCfg();
  const tab = state.donateTab === 'alipay' ? 'alipay' : 'wechat';
  const src = tab === 'alipay' ? alipayQrFor(state.donateAmount) : d.wechat;
  $('donateQr').src = src;
  $('donateQr').alt = (tab === 'wechat' ? (d.wechatLabel || '微信赞赏') : (d.alipayLabel || '支付宝')) + '收款码';
  $('donateQuote').hidden = tab !== 'wechat';
  const wrap = $('donateQrWrap');
  wrap.classList.remove('swap');
  void wrap.offsetWidth;
  wrap.classList.add('swap');
}
function selectDonateAmount(value) {
  state.donateAmount = value;
  $('donateAmounts').querySelectorAll('.donate-amount').forEach((x) => {
    x.setAttribute('aria-checked', String(x.dataset.amount === String(value)));
  });
  refreshDonateQr();
  updateDonateHint();
}
function buildAmounts() {
  const d = donateCfg();
  const box = $('donateAmounts');
  const list = (Array.isArray(d.amounts) && d.amounts.length ? d.amounts : DONATE_FALLBACK.amounts)
    .map(Number).filter((n) => Number.isFinite(n) && n > 0);
  const preferred = Number(d.defaultAmount);
  state.donateAmount = list.includes(preferred) ? preferred : list[0];
  box.innerHTML = '';
  list.forEach((n) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'donate-amount';
    b.dataset.amount = String(n);
    b.setAttribute('role', 'radio');
    b.setAttribute('aria-checked', String(n === state.donateAmount));
    b.textContent = amountLabel(n);
    b.addEventListener('click', () => selectDonateAmount(n));
    box.appendChild(b);
  });
  const custom = document.createElement('button');
  custom.type = 'button';
  custom.className = 'donate-amount';
  custom.dataset.amount = 'custom';
  custom.setAttribute('role', 'radio');
  custom.setAttribute('aria-checked', 'false');
  custom.textContent = d.customLabel || DONATE_FALLBACK.customLabel;
  custom.addEventListener('click', () => selectDonateAmount('custom'));
  box.appendChild(custom);
}
function updateDonateHint() {
  const d = donateCfg();
  const hint = $('donateHint');
  if (state.donateTab === 'alipay') {
    const isCustom = state.donateAmount === 'custom';
    const text = isCustom
      ? (d.alipayCustomHint || DONATE_FALLBACK.alipayCustomHint)
      : String(d.alipayHint || DONATE_FALLBACK.alipayHint).replace(/\{amount\}/g, String(state.donateAmount ?? ''));
    hint.textContent = text;
    hint.classList.add('warn');
  } else {
    hint.textContent = d.wechatHint || DONATE_FALLBACK.wechatHint;
    hint.classList.remove('warn');
  }
}
async function loadBrand() {
  try {
    const res = await fetch('brand.config.json');
    const cfg = res.ok ? await res.json() : {};
    state.siteUrl = cfg.siteUrl || '';
  } catch { state.siteUrl = ''; }
}
async function loadDonate() {
  try {
    const res = await fetch('donate.config.json');
    state.donate = res.ok ? { ...DONATE_FALLBACK, ...(await res.json()) } : DONATE_FALLBACK;
  } catch {
    state.donate = DONATE_FALLBACK;
  }
  const d = donateCfg();
  $('donateTitle').textContent = d.authorName || DONATE_FALLBACK.authorName;
  $('donateMsg').textContent = d.message || '';
  $('donateAvatarText').textContent = d.avatarText || (d.authorName || '豆').slice(0, 1);
  const av = $('donateAvatar');
  if (d.avatar) { av.style.backgroundImage = `url("${d.avatar}")`; $('donateAvatarText').hidden = true; }
  $('tabWechat').textContent = d.wechatLabel || DONATE_FALLBACK.wechatLabel;
  $('tabAlipay').textContent = d.alipayLabel || DONATE_FALLBACK.alipayLabel;
  $('donateContact').textContent = d.contact || '';
  $('donateContact').hidden = !d.contact;
  $('donateNote').textContent = d.note || '';
  $('donateNote').hidden = !d.note;
  if (d.enabled === false) $('donateBtn').hidden = true;
  buildAmounts();
  updateDonateHint();
}
let lastFocus = null;
let donateHideTimer = null;
function setDonateTab(tab) {
  state.donateTab = tab;
  const d = donateCfg();
  $('donateTabs').dataset.active = tab;
  $('tabWechat').classList.toggle('active', tab === 'wechat');
  $('tabAlipay').classList.toggle('active', tab === 'alipay');
  $('tabWechat').setAttribute('aria-selected', String(tab === 'wechat'));
  $('tabAlipay').setAttribute('aria-selected', String(tab === 'alipay'));
  refreshDonateQr();
  updateDonateHint();
}
function openDonate() {
  if (!state.donate) return;
  if (donateHideTimer) { clearTimeout(donateHideTimer); donateHideTimer = null; }
  lastFocus = document.activeElement;
  const ov = $('donateOverlay'); ov.hidden = false;
  requestAnimationFrame(() => ov.classList.add('show'));
  setDonateTab(state.donateTab);
  $('donateClose').focus();
  document.body.style.overflow = 'hidden';
}
function closeDonate() {
  const ov = $('donateOverlay'); ov.classList.remove('show');
  document.body.style.overflow = '';
  donateHideTimer = setTimeout(() => { ov.hidden = true; donateHideTimer = null; }, 380);
  if (lastFocus) lastFocus.focus();
  if (location.hash === '#donate') history.replaceState(null, '', location.pathname);
}
$('donateBtn').addEventListener('click', openDonate);
$('donateClose').addEventListener('click', closeDonate);
$('donateOverlay').addEventListener('click', e => { if (e.target === e.currentTarget) closeDonate(); });
$('tabWechat').addEventListener('click', () => setDonateTab('wechat'));
$('tabAlipay').addEventListener('click', () => setDonateTab('alipay'));
document.addEventListener('keydown', e => {
  if ($('donateOverlay').hidden) return;
  if (e.key === 'Escape') { closeDonate(); return; }
  if (e.key === 'Tab') {
    const focusables = $('donateCard').querySelectorAll('button, [href], input, select, [tabindex]:not([tabindex="-1"])');
    const first = focusables[0], last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
});

/* ================= 启动 ================= */
loadBrand();
loadDonate().then(() => { if (location.hash === '#donate') openDonate(); });