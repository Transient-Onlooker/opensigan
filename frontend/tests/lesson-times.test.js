import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

const source = await readFile(new URL('../src/lesson-times.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const exports = {};
runInNewContext(compiled, { exports, Intl });
const { dailyLessonOverview, parseLessonTimes, koreaClockMinutes } = exports;

const records = [
  { date: '2026-11-16', grade: 1, class: 1, period: 1, subject: '국어', isChanged: false },
  { date: '2026-11-16', grade: 1, class: 1, period: 2, subject: '수학', isChanged: true },
  { date: '2026-11-16', grade: 1, class: 1, period: 2, subject: '과학', isChanged: true },
  { date: '2026-11-16', grade: 1, class: 1, period: 3, subject: '영어', isChanged: false },
];
const times = { 1: { start: '09:00', end: '09:50' }, 2: { start: '10:00', end: '10:50' }, 3: { start: '13:00', end: '13:50' } };

test('completed periods are distinct, boundary-aware, and unavailable without verified times', () => {
  assert.deepEqual(Array.from(dailyLessonOverview(records, times, 10 * 60 + 20, true).completed), [1]);
  assert.deepEqual(Array.from(dailyLessonOverview(records, times, 10 * 60 + 50, true).completed), [1, 2]);
  assert.deepEqual(Array.from(dailyLessonOverview(records, times, 14 * 60, true).completed), [1, 2, 3]);
  assert.equal(dailyLessonOverview(records, { 1: times[1] }, 14 * 60, true).completed.length, 0);
  assert.equal(dailyLessonOverview(records, times, 14 * 60, false).completed.length, 0);
});

test('교시별 수업 시각은 형식·선후·중복을 검증해 로드한다', () => {
  assert.equal(Object.keys(parseLessonTimes({ ...times, 4: { start: '25:00', end: '26:00' } })).length, 3);
  assert.equal(Object.keys(parseLessonTimes({ ...times, 2: { start: '09:30', end: '10:00' } })).length, 0);
  assert.equal(Object.keys(parseLessonTimes({ 1: { start: '10:00', end: '10:50' }, 2: { start: '09:00', end: '09:50' } })).length, 0);
  assert.equal(Object.keys(parseLessonTimes({ 1: { start: '09:50', end: '09:00' } })).length, 0);
  assert.equal(Object.keys(parseLessonTimes(null)).length, 0);
});

test('진행 중, 쉬는 시간, 수업 종료 시 다음 교시와 잔여 교시를 올바르게 계산한다', () => {
  const during = dailyLessonOverview(records, times, 10 * 60 + 20, true);
  assert.equal(during.current.period, 2);
  assert.equal(during.current.lessons.length, 2);
  assert.equal(during.next.period, 3);
  assert.equal(during.changed, 1);
  assert.equal(during.remaining, 2);
  const breakTime = dailyLessonOverview(records, times, 12 * 60, true);
  assert.equal(breakTime.current, null);
  assert.equal(breakTime.next.period, 3);
  assert.equal(breakTime.remaining, 1);
  const after = dailyLessonOverview(records, times, 14 * 60, true);
  assert.equal(after.next, null);
  assert.equal(after.remaining, 0);
});

test('설정이 없거나 오늘이 아닌 경우 현재 수업을 추정하지 않는다', () => {
  const partial = dailyLessonOverview(records, { 1: times[1] }, 10 * 60, true);
  assert.equal(partial.timed, false);
  assert.equal(partial.total, 3);
  assert.equal(partial.remaining, null);
  assert.equal(dailyLessonOverview(records, times, 10 * 60, false).current, null);
});

test('한국 시간대의 시각으로 현재 교시를 계산한다', () => {
  assert.equal(koreaClockMinutes(new Date('2026-11-16T01:20:00Z')), 10 * 60 + 20);
});
