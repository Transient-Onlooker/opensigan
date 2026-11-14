import './admin.css';

interface Summary {
  visitors: number; sessions: number; pageViews: number; apiRequests: number;
  apiErrorRate: number; apiAverageMs: number; droppedApiEvents: number;
  daily: { day: string; visitors: number; sessions: number; page_views: number; api_requests: number }[];
  routes: { route: string; requests: number; errors: number; avg_ms: number }[];
}

const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
const token = document.querySelector<HTMLInputElement>('#token')!;
const days = document.querySelector<HTMLSelectElement>('#days')!;
const button = document.querySelector<HTMLButtonElement>('#load')!;
const state = document.querySelector<HTMLParagraphElement>('#state')!;
const results = document.querySelector<HTMLElement>('#results')!;
let request: AbortController | undefined;

function rows(selector: string, values: (string | number)[][]) {
  const body = document.querySelector(selector)!;
  body.replaceChildren();
  for (const valuesRow of values) {
    const row = document.createElement('tr');
    for (const value of valuesRow) {
      const cell = document.createElement('td');
      cell.textContent = String(value);
      row.append(cell);
    }
    body.append(row);
  }
}

document.querySelector('#login')!.addEventListener('submit', async (event) => {
  event.preventDefault();
  request?.abort();
  const controller = new AbortController(); request = controller;
  button.disabled = true; results.hidden = true; state.textContent = '통계를 불러오는 중…';
  try {
    if (!base && location.hostname.endsWith('.github.io')) throw new Error('API가 연결된 배포 주소에서 이용해 주세요.');
    const response = await fetch(`${base}/api/v1/admin/analytics?days=${days.value}`, {
      headers: { Authorization: `Bearer ${token.value}`, Accept: 'application/json' },
      credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer',
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(10_000)]),
    });
    if (!response.ok) throw new Error(response.status === 401 ? '관리자 토큰을 확인해 주세요.' : response.status === 503 ? '서버의 통계 설정이나 저장소 상태를 확인해 주세요.' : `조회에 실패했습니다. (${response.status})`);
    const data: Summary = await response.json();
    if (controller.signal.aborted) return;
    const metrics = document.querySelector('#metrics')!;
    metrics.replaceChildren();
    const cards: [string, string | number][] = [
      ['방문 브라우저', data.visitors], ['세션', data.sessions], ['페이지 조회', data.pageViews],
      ['API 요청', data.apiRequests], ['API 오류율', `${(data.apiErrorRate * 100).toFixed(2)}%`],
      ['평균 처리 시간', `${data.apiAverageMs} ms`], ['이 프로세스의 누락 이벤트', data.droppedApiEvents],
    ];
    for (const [label, value] of cards) {
      const card = document.createElement('div');
      const heading = document.createElement('span'); heading.textContent = label;
      const number = document.createElement('strong'); number.textContent = typeof value === 'number' ? value.toLocaleString('ko-KR') : value;
      card.append(heading, number); metrics.append(card);
    }
    rows('#daily', data.daily.map((d) => [d.day, d.visitors, d.sessions, d.page_views, d.api_requests]));
    rows('#routes', data.routes.map((r) => [r.route, r.requests, r.errors, r.avg_ms]));
    results.hidden = false;
    state.textContent = data.pageViews || data.apiRequests ? `조회 완료 · ${new Date().toLocaleTimeString('ko-KR')}` : '선택한 기간에 수집된 이용 기록이 없습니다.';
  } catch (error) {
    if (!controller.signal.aborted) state.textContent = error instanceof Error ? error.message : '통계를 불러오지 못했습니다.';
  } finally {
    if (request === controller) button.disabled = false;
  }
});

document.querySelector('#clear')!.addEventListener('click', () => {
  request?.abort(); request = undefined; button.disabled = false;
  token.value = ''; results.hidden = true;
  document.querySelector('#metrics')!.replaceChildren(); rows('#daily', []); rows('#routes', []);
  state.textContent = '잠겼습니다. 다시 조회하려면 토큰을 입력하세요.'; token.focus();
});
