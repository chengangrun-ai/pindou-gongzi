// 豆莉塔图纸二维码：纯函数封装 vendor 的 MIT QR 编码器（qrcode-generator 2.0.4, Kazuhiko Arase）。
// 只输出黑白模块矩阵，不碰 DOM/Canvas/Node Buffer，Node 与浏览器同一份实现，保证四入口逐像素一致。
import qrcode from '../vendor/qr-generator.mjs';

/**
 * 把文本编成 QR 模块矩阵。
 * @param {string} text 要编码的内容（URL 等 ASCII 文本）
 * @param {'L'|'M'|'Q'|'H'} errorLevel 纠错级别，默认 M
 * @returns {{ size:number, dark:Uint8Array }} dark[r*size+c]=1 表示黑模块；矩阵不含外围静区（调用方自行加 4 模块白边）
 */
export function encodeQrMatrix(text, errorLevel = 'M') {
  const qr = qrcode(0, errorLevel); // typeNumber 0 = 按内容自动选版本
  qr.addData(String(text));
  qr.make();
  const size = qr.getModuleCount();
  const dark = new Uint8Array(size * size);
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      dark[r * size + c] = qr.isDark(r, c) ? 1 : 0;
    }
  }
  return { size, dark };
}
