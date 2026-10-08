// Test-only static allowlist: never serve uploaded documents, credentials or DBs.
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.wasm': 'application/wasm', '.png': 'image/png', '.svg': 'image/svg+xml' };
http.createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    const relative = pathname === '/' ? 'frontend/index.html' : pathname.replace(/^\//, '').replace(/\/$/, '/index.html');
    const full = path.resolve(root, relative);
    if (req.method !== 'GET' || (!relative.startsWith('assets/') && relative !== 'frontend/index.html') || !full.startsWith(root + path.sep)) {
      res.writeHead(404).end(); return;
    }
    const body = await fs.readFile(full);
    res.writeHead(200, { 'Content-Type': mime[path.extname(full)] || 'application/octet-stream', 'Cache-Control': 'no-store' }).end(body);
  } catch { res.writeHead(404).end(); }
}).listen(8317, '127.0.0.1');
