import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';

test('Korean date and week calculations handle calendar boundaries', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
  try {
    const { currentKoreaDate, monday, addDays, clampWeek } = await server.ssrLoadModule('/src/date.ts');

    assert.equal(currentKoreaDate(new Date('2026-12-31T14:59:59.999Z')), '2026-12-31');
    assert.equal(currentKoreaDate(new Date('2026-12-31T15:00:00Z')), '2027-01-01');
    assert.equal(currentKoreaDate(new Date('2026-11-08T15:00:00Z')), '2026-11-09');
    assert.equal(monday(currentKoreaDate(new Date('2026-11-08T14:59:59Z'))), '2026-11-02');
    assert.equal(monday(currentKoreaDate(new Date('2026-11-08T15:00:00Z'))), '2026-11-09');
    assert.equal(monday('2027-01-03'), '2026-12-28');
    assert.equal(monday('2027-01-04'), '2027-01-04');
    assert.equal(addDays('2026-12-28', 6), '2027-01-03');
    assert.equal(addDays('2027-01-04', -7), '2026-12-28');
    assert.equal(addDays('2024-02-28', 1), '2024-02-29');
    assert.equal(clampWeek('2026-12-21', '2026-12-31'), '2026-12-28');
    assert.equal(clampWeek('2027-01-04', '2026-12-31'), '2027-01-04');
    assert.equal(clampWeek('2027-01-11', '2026-12-31'), '2027-01-04');
  } finally {
    await server.close();
  }
});
