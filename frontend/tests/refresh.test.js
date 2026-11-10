import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

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
  const harness = `${script}\nreturn { chooseSchool, chooseNeis, refreshCalendar, changeWeek, state: () => ({ week, tableLoading, mealLoading, timetable, meals, hasMeals, tableState, mealState }) };`;
  const javascript = ts.transpile(`(function () { ${harness} })()`, { target: ts.ScriptTarget.ES2022 });
  let now = 1_000;
  const calls = { timetable: [], meals: [] };
  const pending = (list, id, args) => new Promise((resolve, reject) => list.push({ id, ...args, resolve, reject }));
  const context = {
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

test('automatic refresh retains previous results when requests fail, but clears them for a new week', async () => {
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
  assert.equal(app.state().hasMeals, false);
  assert.equal(app.state().meals.length, 0);
});

test('week changes abort in-flight requests and immediately load the selected week', async () => {
  const { app, calls } = await createApp();
  app.chooseSchool({ id: 'school', name: '학교', region: '서울' });
  app.chooseNeis({ id: 'neis', name: '학교', region: '서울', address: '' });
  const oldTable = calls.timetable[0];
  const oldMeals = calls.meals[0];

  app.changeWeek(1);

  assert.equal(oldTable.signal.aborted, true);
  assert.equal(oldMeals.signal.aborted, true);
  assert.equal(calls.timetable.length, 2);
  assert.equal(calls.meals.length, 2);
  assert.equal(calls.timetable[1].week, '2026-11-16');
  assert.equal(calls.meals[1].from, '2026-11-16');
});
