// Renderiza video/motions.html quadro a quadro (Chromium) e monta o MP4 com ffmpeg.
// Uso: node video/render.mjs [saida.mp4] [--preview]
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const require = createRequire(process.env.NODE_TOOLS || '/opt/node-tools/node_modules/');
const { chromium } = require('playwright');

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.resolve(process.argv[2] && !process.argv[2].startsWith('--') ? process.argv[2] : path.join(root, 'video/jubartech-motions.mp4'));
const preview = process.argv.includes('--preview');

const types = { '.html': 'text/html', '.png': 'image/png', '.jpg': 'image/jpeg', '.js': 'text/javascript' };
const server = http.createServer((req, res) => {
  const f = path.join(root, decodeURIComponent(req.url.split('?')[0]));
  if (!f.startsWith(root) || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': types[path.extname(f)] || 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
}).listen(0);
const port = server.address().port;

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
await page.goto(`http://localhost:${port}/video/motions.html`);
await page.evaluate(() => window.__ready);
await page.evaluate(() => document.fonts.ready);

const { duration, fps } = await page.evaluate(() => ({ duration: window.DURATION, fps: window.FPS }));
const frames = Math.round(duration * fps);

const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-i', '-',
  '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });

const stills = [3.5, 7, 11.5, 14.6, 15.5, 16.8, 20.5, 25.5];
for (let i = 0; i < frames; i++) {
  await page.evaluate(t => window.renderAt(t), i / fps);
  const buf = await page.locator('#c').screenshot({ type: 'jpeg', quality: 95 });
  if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
  if (preview && stills.some(s => Math.round(s * fps) === i)) fs.writeFileSync(path.join(root, `video/preview-${(i / fps).toFixed(1)}s.jpg`), buf);
  if (i % 60 === 0) console.log(`frame ${i}/${frames}`);
}
ff.stdin.end();
await new Promise(r => ff.on('close', r));
await browser.close(); server.close();
console.log('ok ->', out);
