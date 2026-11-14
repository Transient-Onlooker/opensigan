import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

const source = await readFile(new URL('../src/allergens.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const exports = {};
runInNewContext(compiled, { exports });
const { allergenMatches } = exports;

test('match allergens by complete numeric token, not substring', () => {
  assert.deepEqual(Array.from(allergenMatches('복숭아(11)', [1])), []);
  assert.deepEqual(Array.from(allergenMatches('달걀(1)', [11])), []);
  assert.deepEqual(Array.from(allergenMatches('메뉴(1.11.13.)', [13, 1, 11]), (entry) => `${entry.id} ${entry.name}`), [
    '1 난류', '11 복숭아', '13 아황산류',
  ]);
});

test('ignore unrelated numbers, invalid codes and unmarked text', () => {
  assert.deepEqual(Array.from(allergenMatches('2026년 메뉴 11 / 5,000원 (20.0)', [11, 5])), []);
  assert.deepEqual(Array.from(allergenMatches('비빔밥 (5, 6) + 김치(5.6)', [6, 5, 5]), (entry) => entry.id), [5, 6]);
});
