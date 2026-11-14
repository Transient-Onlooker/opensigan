import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

const source = await readFile(new URL('../src/timetable-slots.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const moduleExports = {};
runInNewContext(compiled, { exports: moduleExports });
const { slotLessons } = moduleExports;

const lessons = [
  { date: '2026-11-09', period: 2, grade: 1, class: 1, subject: '수학', isChanged: false },
  { date: '2026-11-09', period: 2, grade: 1, class: '1', subject: '과학', isChanged: true },
  { date: '2026-11-09', period: 2, grade: 1, class: 2, subject: '국어', isChanged: false },
  { date: '2026-11-09', period: 3, grade: 1, class: 1, subject: '역사', isChanged: false },
  { date: '2026-11-10', period: 2, grade: 1, class: 1, subject: '음악', isChanged: false },
];

test('주간 수업 칸에서 같은 날짜·교시의 여러 과목을 누락하지 않는다', () => {
  const classRecords = lessons.filter((lesson) => Number(lesson.class) === 1);
  const selected = slotLessons(classRecords, '2026-11-09', 2);
  assert.deepEqual(Array.from(selected, (lesson) => lesson.subject), ['수학', '과학']);
  assert.equal(selected.some((lesson) => lesson.isChanged), true);
  assert.equal(slotLessons(classRecords, '2026-11-09', 4).length, 0);
});

test('학년 비교 칸은 해당 반의 수업만 모두 반환한다', () => {
  assert.deepEqual(Array.from(slotLessons(lessons, '2026-11-09', 2, 1), (lesson) => lesson.subject), ['수학', '과학']);
  assert.deepEqual(Array.from(slotLessons(lessons, '2026-11-09', 2, 2), (lesson) => lesson.subject), ['국어']);
  assert.equal(slotLessons(lessons, '2026-11-10', 3, 1).length, 0);
});
