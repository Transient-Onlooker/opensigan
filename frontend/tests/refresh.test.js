import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { personalizationVm } from './helpers/personalization-vm.js';
import { lessonTimesVm } from './helpers/lesson-times-vm.js';

const addDays = (key, days) => {
  const date = new Date(`${key}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
};
const monday = (key) => addDays(key, -((new Date(`${key}T00:00:00Z`).getUTCDay() + 6) % 7));
const clampWeek = (week, today) => {
  const first = monday(today);
  return week < first ? first : week > addDays(first, 7) ? addDays(first, 7) : week;
};

async function createApp() {
  const component = await readFile(new URL('../src/App.svelte', import.meta.url), 'utf8');
  const script = component.match(/<script lang="ts">([\s\S]*?)<\/script>/)[1]
    .replace(/^\s*import .*;\s*$/gm, '');
  const harness = `${script}\nreturn { chooseSchool, chooseNeis, refreshCalendar, changeWeek, currentWeek, state: () => ({ week, tableLoading, mealLoading, timetable, meals, hasMeals, tableState, mealState }) };`;
  const javascript = ts.transpile(`(function () { ${harness} })()`, { target: ts.ScriptTarget.ES2022 });
  let now = 1_000;
  const calls = { timetable: [], meals: [] };
  const pending = (list, id, args) => new Promise((resolve, reject) => list.push({ id, ...args, resolve, reject }));
  const context = {
    ...personalizationVm,
    ...lessonTimesVm,
    onMount() {}, currentKoreaDate: () => '2026-11-10', monday, addDays, clampWeek,
    document: { visibilityState: 'visible' },
    Date: class extends Date { static now() { return now; } },
    localStorage: { getItem: () => null, setItem() {} },
    getTimetable: (id, week, signal) => pending(calls.timetable, id, { week, signal }),
    getMeals: (id, from, to, signal) => pending(calls.meals, id, { from, to, signal }),
    AbortController, setTimeout, clearTimeout,
  };
  const app = runInNewContext(javascript, context);
  return { app, calls, setNow: (value) => { now = value; }, setVisibility: (value) => { context.document.visibilityState = value; } };
}

test('refreshes each visible dataset at 30 minutes and coalesces repeated visibility checks', async () => {
  const { app, calls, setNow, setVisibility } = await createApp();
  app.chooseSchool({ id: 'school', name: '학교', region: '서울' });
  app.chooseNeis({ id: 'neis', name: '학교', region: '서울', address: '' });
  assert.equal(calls.timetable.length, 1);
  assert.equal(calls.meals.length, 1);
  for (const call of [...calls.timetable, ...calls.meals]) call.resolve({ records: [], meals: [], stale: false });
  await new Promise(setImmediate);

  setNow(1_000 + 30 * 60 * 1000 - 1);
  app.refreshCalendar();
  assert.equal(calls.timetable.length, 1);
  assert.equal(calls.meals.length, 1);

  setVisibility('hidden');
  setNow(1_000 + 30 * 60 * 1000);
  app.refreshCalendar();
  assert.equal(calls.timetable.length, 1);
  assert.equal(calls.meals.length, 1);

  setVisibility('visible');
  app.refreshCalendar();
  app.refreshCalendar();
  assert.equal(calls.timetable.length, 2);
  assert.equal(calls.meals.length, 2);
  for (const call of [...calls.timetable, ...calls.meals]) call.resolve({ records: [], meals: [], stale: false });
  await new Promise(setImmediate);

  setNow(1_000 + 60 * 60 * 1000);
  app.refreshCalendar();
  assert.equal(calls.timetable.length, 3);
  assert.equal(calls.meals.length, 3);
});

test('failed refresh keeps previous results and timetable week changes preserve the selected meal date', async () => {
  const { app, calls, setNow } = await createApp();
  app.chooseSchool({ id: 'school', name: '학교', region: '서울' });
  app.chooseNeis({ id: 'neis', name: '학교', region: '서울', address: '' });
  const table = { records: [{ subject: '수학' }] };
  const meal = { date: '2026-11-10', dishes: ['밥'] };
  calls.timetable[0].resolve(table);
  calls.meals[0].resolve({ meals: [meal], stale: false });
  await new Promise(setImmediate);

  setNow(1_000 + 30 * 60 * 1000);
  app.refreshCalendar();
  assert.equal(app.state().timetable, table);
  assert.equal(app.state().meals[0], meal);
  calls.timetable[1].reject(new Error('offline'));
  calls.meals[1].reject(new Error('offline'));
  await new Promise(setImmediate);
  assert.equal(app.state().timetable, table);
  assert.equal(app.state().meals[0], meal);
  assert.equal(app.state().hasMeals, true);
  assert.ok(app.state().tableState);
  assert.ok(app.state().mealState);

  app.changeWeek(1);
  assert.equal(app.state().timetable, null);
  assert.equal(app.state().hasMeals, true);
  assert.equal(app.state().meals.length, 1);
});

test('timetable week changes abort only the timetable request and leave meals alone', async () => {
  const { app, calls } = await createApp();
  app.chooseSchool({ id: 'school', name: '학교', region: '서울' });
  app.chooseNeis({ id: 'neis', name: '학교', region: '서울', address: '' });
  const oldTable = calls.timetable[0];
  const oldMeals = calls.meals[0];

  app.changeWeek(1);

  assert.equal(oldTable.signal.aborted, true);
  assert.equal(oldMeals.signal.aborted, false);
  assert.equal(calls.timetable.length, 2);
  assert.equal(calls.meals.length, 1);
  assert.equal(calls.timetable[1].week, '2026-11-16');
});

test('returning to this timetable week retains previous results if refreshing fails', async () => {
  const { app, calls } = await createApp();
  app.chooseSchool({ id: 'school', name: '학교', region: '서울' });
  app.chooseNeis({ id: 'neis', name: '학교', region: '서울', address: '' });
  const table = { records: [{ subject: '수학' }] };
  const meal = { date: '2026-11-10', dishes: ['밥'] };
  calls.timetable[0].resolve(table);
  calls.meals[0].resolve({ meals: [meal], stale: false });
  await new Promise(setImmediate);

  app.currentWeek();
  assert.equal(calls.timetable.length, 2);
  assert.equal(calls.meals.length, 1);
  calls.timetable[1].reject(new Error('offline'));
  await new Promise(setImmediate);
  assert.equal(app.state().timetable, table);
  assert.equal(app.state().meals[0], meal);
  assert.equal(app.state().hasMeals, true);
  assert.ok(app.state().tableState);
});

test('revisiting a loaded week uses browser memory while explicit refresh still contacts the server', async () => {
  const { app, calls } = await createApp();
  const school = { id: 'school', name: '학교', region: '서울' };
  app.chooseSchool(school);
  const thisWeek = { records: [{ subject: '과학' }], stale: false };
  calls.timetable[0].resolve(thisWeek);
  await new Promise(setImmediate);

  app.changeWeek(1);
  const nextWeek = { records: [{ subject: '국어' }], stale: false };
  calls.timetable[1].resolve(nextWeek);
  await new Promise(setImmediate);

  app.changeWeek(-1);
  assert.equal(calls.timetable.length, 2);
  assert.equal(app.state().timetable, thisWeek);
  assert.equal(app.state().tableLoading, false);

  app.currentWeek();
  assert.equal(calls.timetable.length, 3, '명시적 새로고침은 메모리 캐시를 우회한다');
  calls.timetable[2].resolve(thisWeek);
  await new Promise(setImmediate);

  app.chooseSchool({ id: 'other', name: '다른 학교', region: '경기' });
  assert.equal(calls.timetable.length, 4, '다른 학교는 기존 주간 캐시를 재사용하지 않는다');
  app.chooseSchool(school);
  assert.equal(calls.timetable.length, 4, '기존 학교로 돌아가면 저장한 주간 데이터를 즉시 표시한다');
  assert.equal(app.state().timetable, thisWeek);
  assert.equal(calls.timetable[3].signal.aborted, true);
});

test('expired or upstream-stale timetables are fetched again on week revisit', async () => {
  const { app, calls, setNow, setVisibility } = await createApp();
  app.chooseSchool({ id: 'school', name: '학교', region: '서울' });
  calls.timetable[0].resolve({ records: [{ subject: '수학' }], stale: false });
  await new Promise(setImmediate);
  app.changeWeek(1);
  calls.timetable[1].resolve({ records: [], stale: true });
  await new Promise(setImmediate);

  app.changeWeek(-1);
  assert.equal(calls.timetable.length, 2, '유효한 주간 응답은 재사용한다');
  app.changeWeek(1);
  assert.equal(calls.timetable.length, 3, '원본 stale 응답은 재사용하지 않는다');
  calls.timetable[2].resolve({ records: [], stale: false });
  await new Promise(setImmediate);

  setVisibility('hidden');
  setNow(1_000 + 30 * 60 * 1000);
  app.changeWeek(-1);
  assert.equal(calls.timetable.length, 4, '30분 만료 후에는 다시 요청한다');
  assert.equal(app.state().timetable, null);
});

test('navigating an expired week only fetches the destination week once', async () => {
  const { app, calls, setNow } = await createApp();
  app.chooseSchool({ id: 'school', name: '학교', region: '서울' });
  calls.timetable[0].resolve({ records: [], stale: false });
  await new Promise(setImmediate);

  setNow(1_000 + 30 * 60 * 1000);
  app.changeWeek(1);
  assert.equal(calls.timetable.length, 2, '이전 주의 만료 데이터는 이동 중 재조회하지 않는다');
  assert.equal(calls.timetable[1].week, '2026-11-16');

  app.currentWeek();
  assert.equal(calls.timetable.length, 3, '이번 주 버튼은 목적지 주간만 한 번 요청한다');
  assert.equal(calls.timetable[2].week, '2026-11-09');
  assert.equal(calls.timetable[1].signal.aborted, true);
});
