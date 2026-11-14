import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { personalizationVm } from './helpers/personalization-vm.js';

const component = await readFile(new URL('../src/App.svelte', import.meta.url), 'utf8');
const script = component.match(/<script lang="ts">([\s\S]*?)<\/script>/)[1]
  .replace(/^\s*import .*;\s*$/gm, '');
const source = ts.transpile(`(function () { ${script}
  return { chooseSchool, loadFavorites, addFavorite, removeFavorite, switchToFavorite, updateClass,
    setClass: (value) => { classroom = value; },
    setAvailableClasses: (values) => { availableClasses = values; },
    state: () => ({ school, grade, classroom, classError, favorites }) };
})()`, { target: ts.ScriptTarget.ES2022 });

function setup(initial = [], recordsBySchool = {}) {
  const store = new Map([['opensigan-favorites', JSON.stringify(initial)]]);
  const requests = [];
  const app = runInNewContext(source, {
    ...personalizationVm,
    onMount() {}, currentKoreaDate: () => '2026-11-14', monday: () => '2026-11-09',
    addDays: () => '2026-11-15', clampWeek: (week) => week,
    localStorage: {
      getItem: (key) => store.get(key) ?? null,
      setItem: (key, value) => store.set(key, value),
    },
    getTimetable: (id) => { requests.push(id); return Promise.resolve({ schoolId: id, records: recordsBySchool[id] ?? [] }); },
    searchNeisSchools: () => new Promise(() => {}),
    AbortController, setTimeout, clearTimeout,
  });
  return { app, requests, store };
}

const first = { id: '1:첫학교', name: '첫학교', region: '서울' };
const second = { id: '2:둘째학교', name: '둘째학교', region: '경기' };

test('즐겨찾기는 중복 없이 저장하고 학교/학급을 전환한다', () => {
  const { app, requests, store } = setup();
  app.chooseSchool(first);
  app.addFavorite();
  app.addFavorite();
  assert.equal(app.state().favorites.length, 1);
  app.setClass(3);
  app.addFavorite();
  assert.equal(app.state().favorites.length, 2);
  app.chooseSchool(second);
  const before = requests.length;
  app.switchToFavorite(app.state().favorites[1]);
  assert.equal(requests.length, before + 1);
  assert.equal(app.state().school.id, first.id);
  assert.equal(app.state().classroom, 3);
  app.switchToFavorite(app.state().favorites[0]);
  assert.equal(requests.length, before + 1, '같은 학교 내 학급 전환은 추가 요청이 없다');
  assert.equal(app.state().classroom, 1);
  assert.equal(store.get('opensigan-class'), '1');
  app.removeFavorite(app.state().favorites[0]);
  assert.equal(JSON.parse(store.get('opensigan-favorites')).length, 1);
});

test('저장소에서 잘못된 항목과 중복을 거르고 10개까지만 복원한다', () => {
  const records = [
    { school: first, grade: 1, classroom: 1 },
    { school: first, grade: 1, classroom: 1 },
    { school: first, grade: 0, classroom: 1 },
    { school: { id: 'bad', name: 'Bad', region: '' }, grade: 1, classroom: 1 },
    ...Array.from({ length: 12 }, (_, index) => ({ school: first, grade: 1, classroom: index + 2 })),
  ];
  const { app } = setup(records);
  app.loadFavorites();
  assert.equal(app.state().favorites.length, 10);
  assert.equal(app.state().favorites[0].classroom, 1);
  assert.equal(app.state().favorites[9].classroom, 10);
});

test('학교 변경과 즐겨찾기 전환 시 실제 학년·반을 선택하고 저장한다', async () => {
  const { app, requests, store } = setup([], {
    [first.id]: [{ grade: 2, class: 3, period: 1, date: '2026-11-09', subject: '국어' }],
    [second.id]: [{ grade: 1, class: 2, period: 1, date: '2026-11-09', subject: '수학' }],
  });

  app.chooseSchool(first);
  await new Promise(setImmediate);
  assert.equal(app.state().grade, 2);
  assert.equal(app.state().classroom, 3);
  assert.equal(store.get('opensigan-grade'), '2');
  assert.equal(store.get('opensigan-class'), '3');

  app.setAvailableClasses([3]);
  app.updateClass({ currentTarget: { valueAsNumber: 9 } });
  assert.equal(app.state().classError, true);
  assert.equal(app.state().classroom, 3);

  app.switchToFavorite({ school: first, grade: 2, classroom: 9 });
  assert.equal(app.state().classroom, 3);
  assert.equal(requests.length, 1, '같은 학교에서는 추가 API 요청이 없다');

  app.chooseSchool(second);
  await new Promise(setImmediate);
  assert.equal(app.state().grade, 1);
  assert.equal(app.state().classroom, 2);
  assert.equal(store.get('opensigan-class'), '2');

  app.switchToFavorite({ school: first, grade: 2, classroom: 1 });
  assert.equal(app.state().school.id, first.id);
  assert.equal(app.state().classroom, 3, '캐시된 시간표에서도 유효한 반으로 보정한다');
  assert.equal(requests.length, 2);
});
