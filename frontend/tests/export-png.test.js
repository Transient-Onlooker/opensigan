import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

const source = await readFile(new URL('../src/export-png.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const exports = {};
runInNewContext(compiled, { exports });
const { createExportGrid } = exports;

const lessons = [
  { grade: 1, class: 2, date: '2026-11-09', period: 1, subject: '긴 과목명', teacher: '김철수' },
  { grade: 1, class: 2, date: '2026-11-10', period: 3, subject: '수학Ⅱ', teacher: '이영희' },
  { grade: 1, class: 1, date: '2026-11-09', period: 1, subject: '과학', teacher: '김철수' },
  { grade: 1, class: 3, date: '2026-11-09', period: 1, subject: '미술', teacher: '김철수' },
];
const options = {
  view: 'week', schoolName: '보인고등학교', grade: 1, classroom: 2,
  selectedDay: '2026-11-09', week: '2026-11-09', teacherName: '', records: lessons, dark: false,
};

test('PNG layout uses the selected class and keeps empty intervening periods', () => {
  const grid = createExportGrid(options);
  assert.equal(grid.columns.length, 5);
  assert.deepEqual(Array.from(grid.periods), [1, 2, 3]);
  assert.equal(grid.rows[0][0][0].title, '긴 과목명');
  assert.equal(grid.rows[0][0].length, 1);
  assert.equal(grid.rows[1][0].length, 0);
  assert.equal(grid.rows[2][1][0].title, '수학Ⅱ');
});

test('teacher view retains all classes at the same period', () => {
  const grid = createExportGrid({ ...options, view: 'teacher', teacherName: '김철수' });
  assert.deepEqual(Array.from(grid.rows[0][0], (lesson) => lesson.title), ['1학년 2반', '1학년 1반', '1학년 3반']);
  assert.equal(grid.rows[0][1].length, 0);
  const unselected = createExportGrid({ ...options, view: 'teacher', teacherName: '김' });
  assert.equal(unselected.periods.length, 0);
});

test('today view exports only the chosen date', () => {
  const grid = createExportGrid({ ...options, view: 'today', selectedDay: '2026-11-10' });
  assert.equal(grid.columns.length, 1);
  assert.deepEqual(Array.from(grid.periods), [1, 2, 3]);
  assert.equal(grid.rows[2][0][0].title, '수학Ⅱ');
  assert.equal(grid.rows[0][0].length, 0);
});
