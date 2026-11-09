import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';

test('정규 API 경로, 매개변수와 오류를 처리한다', async () => {
  globalThis.location = { hostname: 'localhost' };
  const requests = [];
  globalThis.fetch = async (url) => {
    requests.push(url);
    return { ok: true, json: async () => ({ schools: [], records: [], meals: [] }) };
  };
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
  try {
    const api = await server.ssrLoadModule('/src/api.ts');
    await api.searchSchools('서울 학교');
    await api.searchNeisSchools('서울 학교');
    await api.getTimetable('comci/1', '2026-11-09');
    await api.getMeals('neis/2', '2026-11-09', '2026-11-15');
    assert.deepEqual(requests, [
      '/api/v1/schools?q=%EC%84%9C%EC%9A%B8%20%ED%95%99%EA%B5%90',
      '/api/v1/neis/schools?q=%EC%84%9C%EC%9A%B8%20%ED%95%99%EA%B5%90',
      '/api/v1/timetable?school=comci%2F1&week=2026-11-09',
      '/api/v1/meals?school=neis%2F2&from=2026-11-09&to=2026-11-15',
    ]);
    globalThis.fetch = async () => ({ ok: false, status: 503 });
    await assert.rejects(api.getMeals('neis/2', '2026-11-09', '2026-11-15'), /503/);
  } finally { await server.close(); }
});
