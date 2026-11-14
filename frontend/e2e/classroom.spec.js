import { expect, test } from '@playwright/test';

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
    return route.fulfill({ json: { schools: [], meals: [], stale: false } });
  });
  await page.goto('/');
  await page.getByRole('searchbox', { name: '학교 찾기' }).fill('봄빛');
  await page.getByRole('button', { name: /봄빛고등학교/ }).click();
  const panel = page.locator('#timetable-panel');
  const weekTable = panel.getByRole('table');
  await expect(panel.getByRole('button', { name: '이번 주', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(weekTable.getByText('샘플 수학', { exact: true })).toBeVisible();
  await expect(weekTable.locator('th[aria-current="date"]')).toContainText('오늘');
  await expect(weekTable.locator('td.today-column')).toContainText('샘플 수학');
  await panel.getByRole('button', { name: /시간표 새로고침/ }).click();
  await expect(panel.locator('.refresh-feedback')).toContainText('마지막 확인');
  await page.getByRole('button', { name: '설정', exact: true }).click();
  await expect(page.getByRole('heading', { name: '설정', exact: true })).toBeVisible();
  await expect(page.getByText('급식 알레르기 설정', { exact: true })).toBeVisible();
  await expect(panel).toBeHidden();
  await page.getByRole('navigation', { name: '캘린더 메뉴' }).getByRole('button', { name: '시간표', exact: true }).click();
  const classes = panel.locator('.quick-class select').nth(1);
  await classes.selectOption('2');
  await expect(weekTable.getByText('샘플 과학', { exact: true })).toBeVisible();
  await expect(weekTable.getByText('샘플 수학', { exact: true })).toHaveCount(0);
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
