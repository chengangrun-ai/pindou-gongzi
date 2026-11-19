// 纯 JS PNG 编解码（无平台依赖，inflate/deflate 由外部注入）。
// Node 用 node:zlib，浏览器用 DecompressionStream/CompressionStream —— 解压结果按规范逐字节一致。
// 支持：8bit 灰度/RGB/调色板/灰度A/RGBA，tRNS，Adam7 隔行。16bit 明确报错。

const SIG = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const out = new Uint8Array(12 + data.length);
  const dv = new DataView(out.buffer);
  dv.setUint32(0, data.length);
  for (let i = 0; i < 4; i++) out[4 + i] = type.charCodeAt(i);
  out.set(data, 8);
  dv.setUint32(8 + data.length, crc32(out.subarray(4, 8 + data.length)));
  return out;
}

function concat(arrays) {
  let len = 0;
  for (const a of arrays) len += a.length;
  const out = new Uint8Array(len);
  let off = 0;
  for (const a of arrays) { out.set(a, off); off += a.length; }
  return out;
}

// ---------- 编码 ----------

export async function encodePNG(width, height, rgba, deflate) {
  if (rgba.length !== width * height * 4) throw Object.assign(new Error('RGBA 长度与尺寸不符'), { code: 'BAD_IMAGE' });
  const stride = width * 4;
  const raw = new Uint8Array((stride + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (stride + 1)] = 0; // filter: None
    raw.set(rgba.subarray(y * stride, (y + 1) * stride), y * (stride + 1) + 1);
  }
  const ihdr = new Uint8Array(13);
  const dv = new DataView(ihdr.buffer);
  dv.setUint32(0, width); dv.setUint32(4, height);
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  const idat = await deflate(raw);
  return concat([new Uint8Array(SIG), chunk('IHDR', ihdr), chunk('IDAT', idat), chunk('IEND', new Uint8Array(0))]);
}

// ---------- 解码 ----------

function paeth(a, b, c) {
  const p = a + b - c;
  const pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  if (pb <= pc) return b;
  return c;
}

function unfilter(raw, height, stride, bpp) {
  const out = new Uint8Array(height * stride);
  let pos = 0;
  for (let y = 0; y < height; y++) {
    const filter = raw[pos++];
    const rowStart = y * stride;
    for (let x = 0; x < stride; x++) {
      const cur = raw[pos + x];
      const left = x >= bpp ? out[rowStart + x - bpp] : 0;
      const up = y > 0 ? out[rowStart - stride + x] : 0;
      const ul = (x >= bpp && y > 0) ? out[rowStart - stride + x - bpp] : 0;
      let v;
      switch (filter) {
        case 0: v = cur; break;
        case 1: v = cur + left; break;
        case 2: v = cur + up; break;
        case 3: v = cur + ((left + up) >> 1); break;
        case 4: v = cur + paeth(left, up, ul); break;
        default: throw Object.assign(new Error(`未知 PNG 滤波器 ${filter}`), { code: 'BAD_IMAGE' });
      }
      out[rowStart + x] = v & 0xff;
    }
    pos += stride;
  }
  return out;
}

const ADAM7 = [
  { x: 0, y: 0, dx: 8, dy: 8 }, { x: 4, y: 0, dx: 8, dy: 8 },
  { x: 0, y: 4, dx: 4, dy: 8 }, { x: 2, y: 0, dx: 4, dy: 4 },
  { x: 0, y: 2, dx: 2, dy: 4 }, { x: 1, y: 0, dx: 2, dy: 2 },
  { x: 0, y: 1, dx: 1, dy: 2 },
];

export async function decodePNG(bytes, inflate) {
  for (let i = 0; i < 8; i++) if (bytes[i] !== SIG[i]) throw Object.assign(new Error('不是 PNG 文件'), { code: 'BAD_IMAGE' });
  let pos = 8;
  let ihdr = null, plte = null, trns = null;
  const idats = [];
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  while (pos + 8 <= bytes.length) {
    const len = dv.getUint32(pos);
    const type = String.fromCharCode(bytes[pos + 4], bytes[pos + 5], bytes[pos + 6], bytes[pos + 7]);
    const data = bytes.subarray(pos + 8, pos + 8 + len);
    const crcStored = dv.getUint32(pos + 8 + len);
    if (crc32(bytes.subarray(pos + 4, pos + 8 + len)) !== crcStored) {
      throw Object.assign(new Error(`PNG ${type} 块 CRC 校验失败（文件损坏）`), { code: 'BAD_IMAGE' });
    }
    if (type === 'IHDR') ihdr = data;
    else if (type === 'PLTE') plte = data;
    else if (type === 'tRNS') trns = data;
    else if (type === 'IDAT') idats.push(data);
    else if (type === 'IEND') break;
    pos += 12 + len;
  }
  if (!ihdr || idats.length === 0) throw Object.assign(new Error('PNG 缺少 IHDR/IDAT'), { code: 'BAD_IMAGE' });
  const width = (ihdr[0] << 24) | (ihdr[1] << 16) | (ihdr[2] << 8) | ihdr[3];
  const height = (ihdr[4] << 24) | (ihdr[5] << 16) | (ihdr[6] << 8) | ihdr[7];
  const bitDepth = ihdr[8], colorType = ihdr[9], interlace = ihdr[12];
  if (!(width > 0) || !(height > 0)) throw Object.assign(new Error('PNG 尺寸无效'), { code: 'BAD_IMAGE' });
  if (bitDepth !== 8) throw Object.assign(new Error(`暂不支持 ${bitDepth}bit PNG（仅 8bit），请先转换`), { code: 'UNSUPPORTED_PNG' });
  const channels = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 }[colorType];
  if (!channels) throw Object.assign(new Error(`未知 PNG 颜色类型 ${colorType}`), { code: 'BAD_IMAGE' });
  if (colorType === 3 && !plte) throw Object.assign(new Error('调色板 PNG 缺少 PLTE'), { code: 'BAD_IMAGE' });

  const raw = await inflate(concat(idats));
  const out = new Uint8ClampedArray(width * height * 4);

  const putPixel = (x, y, src, si) => {
    const di = (y * width + x) * 4;
    if (colorType === 0) { const g = src[si]; out[di] = g; out[di + 1] = g; out[di + 2] = g; out[di + 3] = (trns && trns.length >= 2 && g === ((trns[0] << 8) | trns[1])) ? 0 : 255; }
    else if (colorType === 2) {
      out[di] = src[si]; out[di + 1] = src[si + 1]; out[di + 2] = src[si + 2];
      let a = 255;
      if (trns && trns.length >= 6) {
        const kr = (trns[0] << 8) | trns[1], kg = (trns[2] << 8) | trns[3], kb = (trns[4] << 8) | trns[5];
        if (src[si] === kr && src[si + 1] === kg && src[si + 2] === kb) a = 0;
      }
      out[di + 3] = a;
    }
    else if (colorType === 3) { const idx = src[si]; out[di] = plte[idx * 3]; out[di + 1] = plte[idx * 3 + 1]; out[di + 2] = plte[idx * 3 + 2]; out[di + 3] = trns && idx < trns.length ? trns[idx] : 255; }
    else if (colorType === 4) { const g = src[si]; out[di] = g; out[di + 1] = g; out[di + 2] = g; out[di + 3] = src[si + 1]; }
    else { out[di] = src[si]; out[di + 1] = src[si + 1]; out[di + 2] = src[si + 2]; out[di + 3] = src[si + 3]; }
  };

  if (interlace === 0) {
    const stride = width * channels;
    if (raw.length < (stride + 1) * height) throw Object.assign(new Error('PNG 数据截断'), { code: 'BAD_IMAGE' });
    const pixels = unfilter(raw, height, stride, channels);
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) putPixel(x, y, pixels, (y * width + x) * channels);
  } else if (interlace === 1) {
    let offset = 0;
    for (const pass of ADAM7) {
      const pw = Math.ceil((width - pass.x) / pass.dx);
      const ph = Math.ceil((height - pass.y) / pass.dy);
      if (pw <= 0 || ph <= 0) continue;
      const stride = pw * channels;
      const passRaw = raw.subarray(offset, offset + (stride + 1) * ph);
      if (passRaw.length < (stride + 1) * ph) throw Object.assign(new Error('PNG 隔行数据截断'), { code: 'BAD_IMAGE' });
      const pixels = unfilter(passRaw, ph, stride, channels);
      for (let py = 0; py < ph; py++) for (let px = 0; px < pw; px++) {
        putPixel(pass.x + px * pass.dx, pass.y + py * pass.dy, pixels, (py * pw + px) * channels);
      }
      offset += (stride + 1) * ph;
    }
  } else {
    throw Object.assign(new Error(`未知 PNG 隔行方式 ${interlace}`), { code: 'BAD_IMAGE' });
  }
  return { width, height, data: out };
}