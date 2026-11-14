import { expect, test } from '@playwright/test';

test.describe('classroom navigation', () => {
test.use({ serviceWorkers: 'block' });
test('switching classes updates lessons, PNG and both links', async ({ page }) => {
  const school = { id: '2:봄빛고등학교', name: '봄빛고등학교', region: '서울' };
  await page.clock.setFixedTime(new Date('2026-11-09T02:00:00Z'));
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/v1/schools') return route.fulfill({ json: { schools: [school], stale: false } });
    if (url.pathname === '/api/v1/timetable') {
      const week = url.searchParams.get('week');
      return route.fulfill({ json: {
        schoolId: school.id, weekStart: week, fetchedAt: new Date().toISOString(), sourceUpdatedAt: null, stale: false,
        records: ['샘플 수학', '샘플 과학'].map((subject, i) => ({
          grade: 1, class: i + 1, date: week, period: 1, subject, teacher: null, isChanged: false,
        })),
      } });
    }
    if (url.pathname === '/api/v1/timetable/history') {
      return route.fulfill({ json: { changes: [1, 2].map((room) => ({
        grade: 1, class: room, date: '2026-11-09', period: 1, type: 'changed',
        observedAt: '2026-11-09T01:00:00Z', before: { subject: `이전 과목 ${room}`, teacher: '이전 교사' },
        after: { subject: `변경 과목 ${room}`, teacher: null },
      })), nextCursor: null } });
    }
    return route.fulfill({ json: { schools: [], meals: [], stale: false } });
  });
  await page.goto('/');
  await page.getByRole('searchbox', { name: '학교 찾기' }).fill('봄빛');
  await page.getByRole('button', { name: /봄빛고등학교/ }).click();
  await expect(page.getByRole('searchbox', { name: '학교 찾기' })).toHaveCount(0);
  const panel = page.locator('#timetable-panel');
  const weekTable = panel.getByRole('table');
  await expect(panel.getByRole('button', { name: '이번 주', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(weekTable.getByText('샘플 수학', { exact: true })).toBeVisible();
  await expect(weekTable.locator('th[aria-current="date"]')).toContainText('오늘');
  await expect(weekTable.locator('td.today-column')).toContainText('샘플 수학');
  const rowHeight = await weekTable.locator('tbody tr').first().evaluate((row) => row.getBoundingClientRect().height);
  expect(rowHeight).toBeLessThan(60);
  const collection = await panel.locator('.last-fetched').boundingBox();
  const refresh = await panel.getByRole('button', { name: /시간표 새로고침/ }).boundingBox();
  expect(collection.y + collection.height).toBeLessThanOrEqual(refresh.y);
  await panel.getByRole('button', { name: /시간표 새로고침/ }).click();
  await expect(panel.locator('.refresh-feedback')).toContainText('마지막 확인');
  await page.getByRole('button', { name: '설정', exact: true }).click();
  await expect(page.getByRole('heading', { name: '설정', exact: true })).toBeVisible();
  await expect(page.getByText('급식 알레르기 설정', { exact: true })).toBeVisible();
  await expect(panel).toBeHidden();
  await page.getByText('시간표 표시 설정', { exact: true }).click();
  await page.getByRole('checkbox', { name: '1학년 1반만 따로 설정' }).check();
  await page.getByRole('checkbox', { name: '주간 시간표 머리글에 날짜 표시' }).uncheck();
  await page.getByRole('navigation', { name: '캘린더 메뉴' }).getByRole('button', { name: '시간표', exact: true }).click();
  await expect(weekTable.locator('thead small.sr-only')).toHaveCount(5);
  const classes = panel.locator('.quick-class select').nth(1);
  await classes.selectOption('2');
  await expect(weekTable.locator('thead small.sr-only')).toHaveCount(0);
  await expect(weekTable.getByText('샘플 과학', { exact: true })).toBeVisible();
  await expect(weekTable.getByText('샘플 수학', { exact: true })).toHaveCount(0);
  await panel.getByRole('button', { name: '이력 보기' }).click();
  const history = panel.getByRole('region', { name: '시간표 변경 이력' });
  await expect(history.getByRole('listitem')).toHaveCount(1);
  await expect(history.getByRole('listitem')).toContainText('이전 과목 2 · 이전 교사');
  await expect(history.getByRole('listitem')).toContainText('변경 과목 2');
  await history.getByRole('combobox').selectOption('school');
  await expect(history.getByRole('listitem')).toHaveCount(2);
  const download = page.waitForEvent('download');
  await panel.getByRole('button', { name: 'PNG 저장' }).click();
  expect((await download).suggestedFilename()).toMatch(/\.png$/);

  await page.getByRole('button', { name: '캘린더 구독 링크' }).click();
  const subscription = page.getByLabel(/시간표 구독 URL/);
  await expect(subscription).toHaveValue(/class=2&weeks=2&mode=summary$/);
  await page.getByRole('combobox', { name: /일정 표시 방식/ }).selectOption('periods');
  await expect(subscription).toHaveValue(/class=2&weeks=2$/);
  await classes.selectOption('1');
  await expect(subscription).toHaveCount(0);
  await page.getByRole('button', { name: '현재 학급 즐겨찾기 추가' }).click();
  await classes.selectOption('2');
  await page.getByRole('button', { name: /봄빛고등학교.*1학년 1반/ }).filter({ has: page.locator('strong') }).click();
  await expect(classes).toHaveValue('1');
  await classes.selectOption('2');
  await page.getByRole('button', { name: '학급 링크 복사' }).click();
  const shared = await page.getByLabel('공유 링크', { exact: true }).inputValue();
  await page.goto(shared);
  await page.reload();
  await panel.getByRole('button', { name: '이번 주', exact: true }).click();
  await expect(weekTable.getByText('샘플 과학', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width);
});
});

test('the installed shell reloads offline and only restores the matching week', async ({ context, page, browserName }) => {
  test.skip(browserName !== 'chromium', 'Playwright WebKit does not consistently emulate service-worker offline requests on Windows.');
  const school = { id: '2:봄빛고등학교', name: '봄빛고등학교', region: '서울' };
  const week = '2026-11-09';
  await page.clock.setFixedTime(new Date('2026-11-09T02:00:00Z'));
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({ json: path === '/api/v1/timetable' ? {
      schoolId: school.id, weekStart: week, fetchedAt: '2026-11-09T01:00:00Z', sourceUpdatedAt: null, stale: false,
      records: [{ grade: 1, class: 1, date: week, period: 1, subject: '오프라인 수학', teacher: null, isChanged: false }],
    } : { schools: path === '/api/v1/schools' ? [school] : [], stale: false } });
  });
  await page.goto('/');
  await page.getByRole('searchbox', { name: '학교 찾기' }).fill('봄빛');
  await page.getByRole('button', { name: /봄빛고등학교/ }).click();
  await expect(page.getByRole('table').getByText('오프라인 수학')).toBeVisible();
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
  await page.unroute('**/api/v1/**');
  await page.route('**/api/v1/**', (route) => route.abort('internetdisconnected'));
  await context.setOffline(true);
  const navigation = await page.goto('/?offline=1');
  expect(navigation.fromServiceWorker()).toBe(true);
  await expect(page.getByRole('heading', { name: school.name })).toBeVisible();
  await expect(page.getByText('오프라인 · 이 기기에 저장된 시간표')).toBeVisible();
  await expect(page.getByRole('table').getByText('오프라인 수학')).toBeVisible();
  await page.getByRole('button', { name: '다음 주' }).click();
  await expect(page.getByRole('table')).toHaveCount(0);
  await expect(page.getByText('오프라인 · 이 기기에 저장된 시간표')).toHaveCount(0);
});
