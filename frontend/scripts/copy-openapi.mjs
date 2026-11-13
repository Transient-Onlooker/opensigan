import { copyFile, mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const source = resolve(frontend, '..', 'docs', 'openapi.yaml');
const target = resolve(frontend, 'public', 'openapi.yaml');

await mkdir(dirname(target), { recursive: true });
await copyFile(source, target);
