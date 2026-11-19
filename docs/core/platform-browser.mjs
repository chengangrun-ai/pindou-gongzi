// 浏览器平台适配：DecompressionStream / CompressionStream（'deflate' 即 zlib 格式，与 PNG IDAT 匹配）。
// 解压输出按 RFC1951 规范与 Node zlib 逐字节一致，压缩字节允许不同（像素等价不受影响）。

async function streamBytes(u8, Ctor, format) {
  if (typeof Ctor === 'undefined') {
    throw Object.assign(new Error('当前浏览器不支持 DecompressionStream/CompressionStream，请用新版 Chrome/Edge/Firefox/Safari'), { code: 'PLATFORM_UNSUPPORTED' });
  }
  const stream = new Ctor(format);
  const writer = stream.writable.getWriter();
  const writePromise = writer.write(u8).then(() => writer.close());
  const reader = stream.readable.getReader();
  const chunks = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      total += value.length;
    }
  } catch (e) {
    throw Object.assign(new Error(`压缩流处理失败：${e.message}`), { code: 'BAD_IMAGE' });
  } finally {
    try { await writePromise; } catch { /* 写端错误已在读端体现 */ }
  }
  const out = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) { out.set(c, off); off += c.length; }
  return out;
}

export const platform = {
  name: 'browser',
  inflate: (u8) => streamBytes(u8, globalThis.DecompressionStream, 'deflate'),
  deflate: (u8) => streamBytes(u8, globalThis.CompressionStream, 'deflate'),
};