const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
const visitorKey = 'opensigan-analytics-visitor';
const sessionKey = 'opensigan-analytics-session';
const enabledKey = 'opensigan-analytics-enabled';
const uuidV4Pattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function identifier(storage: Storage, key: string) {
  try {
    const current = storage.getItem(key);
    if (current && uuidV4Pattern.test(current)) return current;
    const cryptoApi = globalThis.crypto;
    if (!cryptoApi?.randomUUID && !cryptoApi?.getRandomValues) return null;
    let value: string;
    if (typeof cryptoApi.randomUUID === 'function') {
      value = cryptoApi.randomUUID();
    } else {
      const bytes = cryptoApi.getRandomValues(new Uint8Array(16));
      bytes[6] = (bytes[6] & 0x0f) | 0x40;
      bytes[8] = (bytes[8] & 0x3f) | 0x80;
      const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
      value = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }
    storage.setItem(key, value);
    return value;
  } catch {
    return null;
  }
}

export function isAnalyticsEnabled() {
  try {
    if (navigator.doNotTrack === '1' || (navigator as Navigator & { globalPrivacyControl?: boolean }).globalPrivacyControl) return false;
    return localStorage.getItem(enabledKey) !== 'false';
  } catch { return false; }
}

export function setAnalyticsEnabled(enabled: boolean) {
  try { localStorage.setItem(enabledKey, String(enabled)); } catch { /* 브라우저 저장소를 사용할 수 없으면 수집하지 않습니다. */ }
  if (!enabled) {
    try { localStorage.removeItem(visitorKey); } catch { /* 브라우저 저장소를 사용할 수 없으면 수집하지 않습니다. */ }
    try { sessionStorage.removeItem(sessionKey); } catch { /* 브라우저 저장소를 사용할 수 없으면 수집하지 않습니다. */ }
  }
}

export function trackPageView(page: '/' | '/timetable' | '/meals') {
  if (!isAnalyticsEnabled() || typeof window === 'undefined') return;
  if (!base && window.location.hostname.endsWith('.github.io')) return;
  try {
    const visitorId = identifier(localStorage, visitorKey);
    const sessionId = identifier(sessionStorage, sessionKey);
    if (!visitorId || !sessionId) return;
    const payload = JSON.stringify({
      visitorId,
      sessionId,
      page,
    });
    void fetch(`${base}/api/v1/analytics/pageview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: payload,
      keepalive: true,
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
    }).catch(() => undefined);
  } catch { /* 분석 실패는 시간표 조회에 영향을 주지 않습니다. */ }
}
