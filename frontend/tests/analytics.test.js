import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

async function harness(navigator = {}, storageFails = false) {
  const source = (await readFile(new URL('../src/analytics.ts', import.meta.url), 'utf8'))
    .replace('import.meta.env.VITE_API_BASE_URL', "''");
  const local = new Map(), session = new Map(), calls = [];
  const storage = (map) => ({
    getItem(key) { if (storageFails) throw Error('unavailable'); return map.get(key) ?? null; },
    setItem(key, value) { if (storageFails) throw Error('unavailable'); map.set(key, value); },
    removeItem(key) { map.delete(key); },
  });
  const context = {
    exports: {}, navigator, window: { location: { hostname: 'localhost' } },
    localStorage: storage(local), sessionStorage: storage(session),
    crypto: { randomUUID: () => '11111111-1111-4111-8111-111111111111' },
    fetch: (...args) => { calls.push(args); return Promise.resolve({ ok: true }); },
  };
  runInNewContext(ts.transpile(source, { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }), context);
  return { api: context.exports, local, session, calls, context };
}

test('analytics sends only random IDs and the page, and disabling removes identifiers', async () => {
  const { api, calls, local, session } = await harness();
  api.trackPageView('/timetable');
  assert.equal(calls.length, 1);
  assert.deepEqual(Object.keys(JSON.parse(calls[0][1].body)).sort(), ['page', 'sessionId', 'visitorId']);
  assert.equal(calls[0][1].credentials, 'omit');
  assert.equal(calls[0][1].referrerPolicy, 'no-referrer');
  api.setAnalyticsEnabled(false);
  assert.equal(local.has('opensigan-analytics-visitor'), false);
  assert.equal(session.size, 0);
  api.trackPageView('/meals');
  assert.equal(calls.length, 1);
});

for (const [name, navigator, fails] of [['DNT', { doNotTrack: '1' }, false], ['GPC', { globalPrivacyControl: true }, false], ['storage failure', {}, true]]) {
  test(`analytics respects ${name}`, async () => {
    const { api, calls, local } = await harness(navigator, fails);
    assert.equal(api.isAnalyticsEnabled(), false);
    assert.doesNotThrow(() => api.trackPageView('/'));
    assert.equal(calls.length, 0);
    assert.equal(local.size, 0);
  });
}

test('analytics network failure does not reject into the application', async () => {
  const { api, context } = await harness();
  context.fetch = () => Promise.reject(Error('offline'));
  assert.doesNotThrow(() => api.trackPageView('/'));
  await new Promise((resolve) => setTimeout(resolve, 0));
});
