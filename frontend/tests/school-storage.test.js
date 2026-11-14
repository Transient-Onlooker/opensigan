import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { personalizationVm } from './helpers/personalization-vm.js';

test('학교 선택 시 저장이 실패해도 이전 학교 데이터가 남지 않는다', async () => {
  const component = await readFile(new URL('../src/App.svelte', import.meta.url), 'utf8');
  const script = component.match(/<script lang="ts">([\s\S]*?)<\/script>/)[1]
    .replace(/^\s*import .*;\s*$/gm, '');
  const harness = `${script}\nreturn { chooseSchool, chooseNeis, state: () => ({ school, neis, timetable, meals }) };`;
  const javascript = ts.transpile(`(function () { ${harness} })()`, { target: ts.ScriptTarget.ES2022 });
  const storage = new Map();
  let failWrites = false;
  let failReads = false;
  const app = runInNewContext(javascript, {
    ...personalizationVm,
    onMount() {}, currentKoreaDate: () => '2026-11-10', monday: () => '2026-11-09',
    addDays: () => '2026-11-15', clampWeek: (week) => week,
    localStorage: {
      getItem: (key) => { if (failReads) throw new Error('storage unavailable'); return storage.get(key) ?? null; },
      setItem: (key, value) => { if (failWrites) throw new Error('storage unavailable'); storage.set(key, value); },
      removeItem: (key) => storage.delete(key),
    },
    getTimetable: async (id) => ({ schoolId: id, records: [] }),
    getMeals: async (id) => ({ meals: [{ type: id }], stale: false }),
    AbortController, setTimeout, clearTimeout,
  });
  const first = { id: 'a', name: 'A', region: '서울' };
  const second = { id: 'b', name: 'B', region: '서울' };
  app.chooseSchool(first);
  app.chooseNeis({ id: 'meal-a', name: 'A', region: '서울', address: '' });
  await new Promise(setImmediate);
  assert.equal(app.state().timetable.schoolId, 'a');
  assert.equal(app.state().meals[0].type, 'meal-a');

  failWrites = true;
  failReads = true;
  assert.doesNotThrow(() => app.chooseSchool(second));
  await new Promise(setImmediate);
  assert.equal(app.state().school.id, 'b');
  assert.equal(app.state().timetable.schoolId, 'b');
  assert.equal(app.state().neis, null);
  assert.equal(app.state().meals.length, 0);
  assert.doesNotThrow(() => app.chooseNeis({ id: 'meal-b', name: 'B', region: '서울', address: '' }));
  await new Promise(setImmediate);
  assert.equal(app.state().meals[0].type, 'meal-b');
});
