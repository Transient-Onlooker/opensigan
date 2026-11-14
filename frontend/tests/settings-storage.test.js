import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { personalizationVm } from './helpers/personalization-vm.js';
import { lessonTimesVm } from './helpers/lesson-times-vm.js';

for (const failure of ['property access', 'storage methods']) {
  test(`storage unavailable through ${failure}: startup and settings remain usable`, async () => {
    const component = await readFile(new URL('../src/App.svelte', import.meta.url), 'utf8');
    const script = component.match(/<script lang="ts">([\s\S]*?)<\/script>/)[1]
      .replace(/^\s*import .*;\s*$/gm, '');
    const harness = `${script}\nreturn { changeTheme, setTheme, saveGrade, saveClass, setGrade: (value) => grade = value, state: () => ({ theme, dark: themeIsDark(theme, systemDark), grade, classroom, classError }) };`;
    const javascript = ts.transpile(`(function () { ${harness} })()`, { target: ts.ScriptTarget.ES2022 });
    let mount;
    let themeChange;
    let themeListenerRemoved = false;
    const context = {
      ...personalizationVm,
      ...lessonTimesVm,
      onMount: (callback) => { mount = callback; },
      isAnalyticsEnabled: () => false,
      currentKoreaDate: () => '2026-11-10', monday: () => '2026-11-09',
      addDays: () => '2026-11-15', clampWeek: (week) => week,
      document: { addEventListener() {}, removeEventListener() {} },
      window: {
        addEventListener() {}, removeEventListener() {},
        matchMedia: (query) => query === '(prefers-color-scheme: dark)'
          ? { matches: true, addEventListener: (_, callback) => { themeChange = callback; }, removeEventListener: (_, callback) => { themeListenerRemoved = callback === themeChange; } }
          : { matches: false },
      },
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
    app.setTheme('system');
    assert.equal(app.state().dark, true);
    themeChange({ matches: false });
    assert.equal(app.state().dark, false, '시스템 테마 변경을 즉시 반영한다');
    app.setTheme('invalid');
    assert.equal(app.state().theme, 'system');
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
    assert.equal(themeListenerRemoved, true);
  });
}
