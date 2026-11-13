import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

for (const failure of ['property access', 'storage methods']) {
  test(`storage unavailable through ${failure}: startup and settings remain usable`, async () => {
    const component = await readFile(new URL('../src/App.svelte', import.meta.url), 'utf8');
    const script = component.match(/<script lang="ts">([\s\S]*?)<\/script>/)[1]
      .replace(/^\s*import .*;\s*$/gm, '');
    const harness = `${script}\nreturn { changeTheme, saveGrade, saveClass, setGrade: (value) => grade = value, state: () => ({ theme, grade, classroom, classError }) };`;
    const javascript = ts.transpile(`(function () { ${harness} })()`, { target: ts.ScriptTarget.ES2022 });
    let mount;
    const context = {
      onMount: (callback) => { mount = callback; },
      currentKoreaDate: () => '2026-11-10', monday: () => '2026-11-09',
      addDays: () => '2026-11-15', clampWeek: (week) => week,
      document: { addEventListener() {}, removeEventListener() {} },
      window: { addEventListener() {}, removeEventListener() {} },
      setInterval: () => 1, clearInterval() {}, clearTimeout() {},
    };
    const unavailable = () => { throw new Error('storage unavailable'); };
    if (failure === 'property access') {
      context.unavailable = unavailable;
      runInNewContext("Object.defineProperty(globalThis, 'localStorage', { get: unavailable })", context);
    } else {
      context.localStorage = { getItem: unavailable, setItem: unavailable };
    }
    const app = runInNewContext(javascript, context);
    let cleanup;
    assert.doesNotThrow(() => { cleanup = mount(); });
    assert.equal(app.state().theme, 'light');
    assert.equal(app.state().grade, 1);
    assert.equal(app.state().classroom, 1);

    const errors = [];
    try { app.changeTheme(); } catch { errors.push('theme'); }
    assert.equal(app.state().theme, 'dark');
    app.setGrade(3);
    try { app.saveGrade(); } catch { errors.push('grade'); }
    assert.equal(app.state().grade, 3);
    try { app.saveClass({ currentTarget: { valueAsNumber: 7 } }); } catch { errors.push('class'); }
    assert.equal(app.state().classroom, 7);
    assert.deepEqual(errors, []);
    assert.doesNotThrow(() => app.saveClass({ currentTarget: { valueAsNumber: 100 } }));
    assert.equal(app.state().classError, true);
    assert.equal(app.state().classroom, 7);
    assert.doesNotThrow(cleanup);
  });
}
