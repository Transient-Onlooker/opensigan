import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';

const dist = new URL('../dist/', import.meta.url);
const html = await readFile(new URL('index.html', dist), 'utf8');
const assets = [...new Set([...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((match) => match[1]))];
const template = await readFile(new URL('./offline-shell.js', import.meta.url), 'utf8');
const version = createHash('sha256').update(html).update(template).digest('hex').slice(0, 16);
await writeFile(new URL('service-worker.js', dist), `const CACHE = 'opencigan-shell-${version}';\nconst ASSETS = ${JSON.stringify(assets)};\n${template}`);
