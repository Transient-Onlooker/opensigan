import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

const component = await readFile(new URL('../src/App.svelte', import.meta.url), 'utf8');
const script = component.match(/<script lang="ts">([\s\S]*?)<\/script>/)[1]
  .replace(/^\s*import .*;\s*$/gm, '');
const source = ts.transpile(`(function () { ${script}
  return { chooseSchool, loadFavorites, addFavorite, removeFavorite, switchToFavorite,
    setClass: (value) => { classroom = value; },
    state: () => ({ school, grade, classroom, favorites }) };
})()`, { target: ts.ScriptTarget.ES2022 });

function setup(initial = []) {
  const store = new Map([['opensigan-favorites', JSON.stringify(initial)]]);
  const requests = [];
  const app = runInNewContext(source, {
    onMount() {}, currentKoreaDate: () => '2026-11-14', monday: () => '2026-11-09',
    addDays: () => '2026-11-15', clampWeek: (week) => week,
    localStorage: {
      getItem: (key) => store.get(key) ?? null,
      setItem: (key, value) => store.set(key, value),
    },
    getTimetable: (id) => { requests.push(id); return Promise.resolve({ schoolId: id, records: [] }); },
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
