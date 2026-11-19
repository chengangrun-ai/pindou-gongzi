// 豆莉塔取色桥 · 零依赖 node，直接调用 docs/core，不需要任何服务器
//   node scripts/dolita_convert.mjs <图片路径> [width] [threshold] [brand]
// 输出 JSON: { ok, manifest, grid, width, height }
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { convertImage, buildManifest } from '../docs/core/bead-core.mjs';
import { decodeImage } from '../docs/core/image-io.mjs';
import { platform } from '../docs/core/platform-node.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));

async function main() {
  const [src, width = '100', threshold = '30', brand = 'MARD'] = process.argv.slice(2);
  if (!src) {
    console.log(JSON.stringify({ ok: false, error: 'usage: dolita_convert.mjs <image> [width] [threshold] [brand]' }));
    process.exit(1);
  }
  const bytes = await readFile(src);
  const image = await decodeImage(bytes, platform);
  const result = convertImage(image, {
    width: Number(width), threshold: Number(threshold), brand,
  });
  const manifest = buildManifest(result, {
    name: path.basename(src, path.extname(src)),
    createdAt: new Date().toISOString(),
  });
  process.stdout.write(JSON.stringify({
    ok: true, manifest, grid: result.grid,
    width: result.width, height: result.height,
  }));
}

main().catch(e => {
  process.stdout.write(JSON.stringify({ ok: false, error: String(e && e.message || e) }));
  process.exit(1);
});
