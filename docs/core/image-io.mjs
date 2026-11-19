// 图片解码统一入口：PNG / JPEG / BMP。
// 关键设计：浏览器与 Node 走同一份解码代码（PNG 自研、JPEG 用 vendor 化的 jpeg-js、BMP 自研），
// 从源头保证两端输入 RGBA 逐像素一致，而不是依赖浏览器 canvas 解码（不同浏览器 JPEG IDCT 有差异）。
import jpegModule from '../vendor/jpeg-decoder.mjs';
import { decodePNG, encodePNG } from './png.mjs';

const decodeJpeg = typeof jpegModule === 'function' ? jpegModule : (jpegModule.decode || jpegModule.default);

export const SUPPORTED_FORMATS = ['PNG', 'JPEG', 'BMP'];

export function sniffFormat(bytes) {
  if (bytes.length >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) return 'PNG';
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return 'JPEG';
  if (bytes.length >= 2 && bytes[0] === 0x42 && bytes[1] === 0x4d) return 'BMP';
  if (bytes.length >= 12 && bytes[8] === 0x57 && bytes[9] === 0x45 && bytes[10] === 0x42 && bytes[11] === 0x50) return 'WEBP';
  if (bytes.length >= 6 && bytes[0] === 0x47 && bytes[1] === 0x49 && bytes[2] === 0x46) return 'GIF';
  return 'UNKNOWN';
}

function toU8(bytes) {
  if (bytes instanceof Uint8Array) return bytes;
  if (bytes instanceof ArrayBuffer) return new Uint8Array(bytes);
  if (ArrayBuffer.isView(bytes)) return new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  throw Object.assign(new Error('图像数据必须是 Uint8Array / ArrayBuffer'), { code: 'BAD_IMAGE' });
}

function decodeBMP(bytes) {
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.length < 54) throw Object.assign(new Error('BMP 文件过短'), { code: 'BAD_IMAGE' });
  const dataOffset = dv.getUint32(10, true);
  const width = dv.getInt32(18, true);
  const rawHeight = dv.getInt32(22, true);
  const bpp = dv.getUint16(28, true);
  const compression = dv.getUint32(30, true);
  const height = Math.abs(rawHeight);
  if (!(width > 0) || !(height > 0)) throw Object.assign(new Error('BMP 尺寸无效'), { code: 'BAD_IMAGE' });
  if (compression !== 0 || (bpp !== 24 && bpp !== 32)) {
    throw Object.assign(new Error(`暂不支持压缩 BMP（compression=${compression}, bpp=${bpp}），请转 PNG`), { code: 'UNSUPPORTED_BMP' });
  }
  const topDown = rawHeight < 0;
  const rowSize = Math.floor((bpp * width + 31) / 32) * 4;
  if (dataOffset + rowSize * height > bytes.length) throw Object.assign(new Error('BMP 数据截断'), { code: 'BAD_IMAGE' });
  const out = new Uint8ClampedArray(width * height * 4);
  let anyAlpha = false;
  for (let y = 0; y < height; y++) {
    const srcY = topDown ? y : height - 1 - y;
    const rowOff = dataOffset + srcY * rowSize;
    for (let x = 0; x < width; x++) {
      const si = rowOff + x * (bpp / 8);
      const di = (y * width + x) * 4;
      out[di] = bytes[si + 2]; out[di + 1] = bytes[si + 1]; out[di + 2] = bytes[si];
      const a = bpp === 32 ? bytes[si + 3] : 255;
      out[di + 3] = a;
      if (a !== 0) anyAlpha = true;
    }
  }
  // 32bpp BMP 常见全 0 alpha（实际不透明），统一视为不透明，保证两端一致
  if (bpp === 32 && !anyAlpha) for (let i = 3; i < out.length; i += 4) out[i] = 255;
  return { width, height, data: out };
}

export async function decodeImage(bytes, platform) {
  const u8 = toU8(bytes);
  if (u8.length === 0) throw Object.assign(new Error('空文件'), { code: 'BAD_IMAGE' });
  const fmt = sniffFormat(u8);
  if (fmt === 'PNG') {
    try { return await decodePNG(u8, platform.inflate); }
    catch (e) { if (e && e.code) throw e; throw Object.assign(new Error(`PNG 解码失败（文件可能截断或损坏）：${e.message}`), { code: 'BAD_IMAGE' }); }
  }
  if (fmt === 'JPEG') {
    try {
      const img = decodeJpeg(u8, {
        useTArray: true, formatAsRGBA: true, tolerantDecoding: true,
        maxResolutionInMP: 200, maxMemoryUsageInMB: 1024,
      });
      return { width: img.width, height: img.height, data: new Uint8ClampedArray(img.data) };
    } catch (e) {
      throw Object.assign(new Error(`JPEG 解码失败：${e.message}`), { code: 'BAD_IMAGE' });
    }
  }
  if (fmt === 'BMP') {
    try { return decodeBMP(u8); }
    catch (e) { if (e && e.code) throw e; throw Object.assign(new Error(`BMP 解码失败（文件可能截断或损坏）：${e.message}`), { code: 'BAD_IMAGE' }); }
  }
  if (fmt === 'WEBP' || fmt === 'GIF') {
    throw Object.assign(new Error(`${fmt} 暂不支持（为保证桌面/网页逐像素一致，仅收 PNG/JPEG/BMP）。请先转成 PNG。`), { code: 'UNSUPPORTED_FORMAT' });
  }
  throw Object.assign(new Error('无法识别的图片格式（支持 PNG/JPEG/BMP）'), { code: 'BAD_IMAGE' });
}

export async function encodeImagePNG(image, platform) {
  return encodePNG(image.width, image.height, image.data, platform.deflate);
}