import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { createServer } from 'vite';
import { personalizationVm } from './helpers/personalization-vm.js';

const vite = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
after(() => vite.close());
const dates = await vite.ssrLoadModule('/src/date.ts');
const matching = await vite.ssrLoadModule('/src/neis-match.ts');
const flush = () => new Promise(setImmediate);
const school = { id: '11:중앙고등학교', name: '중앙고등학교', region: '서울' };
const neis = { id: 'B10:1234567', name: school.name, region: '고등학교', address: '서울특별시' };

async function harness() {
  const source = await readFile(new URL('../src/App.svelte', import.meta.url), 'utf8');
  const script = source.match(/<script lang="ts">([\s\S]*?)<\/script>/)[1].replace(/^\s*import .*;\s*$/gm, '');
  const body = script + '\nreturn { chooseSchool, changeMealDate, selectMealDate, todayMeals, state: () => ({ school, neis, neisResults, meals, mealDate, hasMeals, mealLoading, mealState, dateError }) };';
  const calls = { neis: [], meals: [] };
  const pending = (list, args) => new Promise((resolve, reject) => list.push({ ...args, resolve, reject }));
  const app = runInNewContext(ts.transpile('(function(){' + body + '})()', { target: ts.ScriptTarget.ES2022 }), {
    ...dates, ...matching, ...personalizationVm, currentKoreaDate: () => '2026-11-13',
    onMount() {}, document: { visibilityState: 'visible' },
    localStorage: { getItem: () => null, setItem() {} },
    getTimetable: () => new Promise(() => {}),
    searchNeisSchools: (q, signal) => pending(calls.neis, { q, signal }),
    getMeals: (id, from, to, signal) => pending(calls.meals, { id, from, to, signal }),
    AbortController, Date, setTimeout, clearTimeout,
  });
  return { app, calls };
}

test('한 번의 학교 선택으로 급식을 연결하고 같은 주의 날짜 이동은 응답을 재사용한다', async () => {
  const { app, calls } = await harness();
  app.chooseSchool(school);
  assert.equal(calls.neis[0].q, school.name);
  calls.neis[0].resolve({ schools: [neis] });
  await flush();
  assert.equal(calls.meals.length, 1);
  assert.equal(calls.meals[0].id, neis.id);
  assert.equal(calls.meals[0].from, '2026-11-09');
  assert.equal(calls.meals[0].to, '2026-11-15');
  calls.meals[0].resolve({ meals: [{ date: '2026-11-13', type: '중식', dishes: ['밥(1)'] }], stale: false });
  await flush();
  app.changeMealDate(1);
  assert.equal(app.state().mealDate, '2026-11-14');
  assert.equal(calls.meals.length, 1);
  app.changeMealDate(2);
  assert.equal(app.state().mealDate, '2026-11-16');
  assert.equal(calls.meals.length, 2);
  assert.equal(calls.meals[1].from, '2026-11-16');
  assert.equal(app.state().hasMeals, false);
  assert.equal(app.state().meals.length, 0);
});

test('학교 변경 후 늦게 도착한 급식 학교 응답은 무시한다', async () => {
  const { app, calls } = await harness();
  app.chooseSchool(school);
  const second = { id: '22:다음고등학교', name: '다음고등학교', region: '경기' };
  app.chooseSchool(second);
  assert.equal(calls.neis[0].signal.aborted, true);
  calls.neis[0].resolve({ schools: [neis] });
  await flush();
  assert.equal(app.state().neis, null);
  assert.equal(calls.meals.length, 0);
  calls.neis[1].resolve({ schools: [{ ...neis, id: 'J10:2345678', name: second.name }] });
  await flush();
  assert.equal(app.state().neis.name, second.name);
  assert.equal(calls.meals[0].id, 'J10:2345678');
});

test('다른 주 로딩 중 원래 주로 돌아가면 오래된 요청이 표시 결과를 덮지 못한다', async () => {
  const { app, calls } = await harness();
  app.chooseSchool(school);
  calls.neis[0].resolve({ schools: [neis] });
  await flush();
  calls.meals[0].resolve({ meals: [{ date: '2026-11-13', type: '중식', dishes: ['밥'] }], stale: false });
  await flush();
  app.changeMealDate(3);
  assert.equal(calls.meals[1].from, '2026-11-16');
  app.changeMealDate(-3);
  assert.equal(calls.meals[1].signal.aborted, true);
  calls.meals[1].resolve({ meals: [{ date: '2026-11-16', type: '중식', dishes: ['다른 주'] }], stale: false });
  calls.meals[2].resolve({ meals: [{ date: '2026-11-13', type: '중식', dishes: ['밥'] }], stale: false });
  await flush();
  assert.equal(app.state().meals[0].dishes[0], '밥');
});

test('동명이교는 자동 선택하지 않고 후보 확인으로 남긴다', async () => {
  const { app, calls } = await harness();
  app.chooseSchool(school);
  calls.neis[0].resolve({ schools: [neis, { ...neis, id: 'B10:3456789', address: '서울특별시 다른 주소' }] });
  await flush();
  assert.equal(app.state().neis, null);
  assert.equal(app.state().neisResults.length, 2);
  assert.equal(calls.meals.length, 0);
});

test('빈 날짜 입력은 선택 날짜와 요청을 바꾸지 않는다', async () => {
  const { app, calls } = await harness();
  app.selectMealDate({ currentTarget: { value: '' } });
  assert.equal(app.state().mealDate, '2026-11-13');
  assert.ok(app.state().dateError);
  assert.equal(calls.meals.length, 0);
});
