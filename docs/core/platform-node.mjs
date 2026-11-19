// Node 平台适配：zlib 注入。仅供 CLI / HTTP / MCP 使用。
import zlib from 'node:zlib';

function buf(u8) { return Buffer.from(u8.buffer, u8.byteOffset, u8.byteLength); }

export const platform = {
  name: 'node',
  inflate: async (u8) => new Uint8Array(zlib.inflateSync(buf(u8))),
  deflate: async (u8) => new Uint8Array(zlib.deflateSync(buf(u8), { level: 9 })),
};