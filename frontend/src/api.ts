export interface School { id: string; name: string; region: string }
export interface NeisSchool extends School { address: string }
export interface TimetableRecord { grade: number; class: number | string; date: string; period: number; subject: string; teacher: string | null; isChanged: boolean }
export interface TimetableResponse { schoolId: string; weekStart: string; records: TimetableRecord[]; sourceUpdatedAt: string | null; fetchedAt: string; stale: boolean }
export interface Meal { date: string; type: string; dishes: string[] }
export interface MealsResponse { meals: Meal[]; stale: boolean }
export interface HistoryLesson { subject: string; teacher: string | null }
export interface TimetableChange { observedAt: string; grade: number; class: number | string; date: string; period: number; type: string; before: HistoryLesson | null; after: HistoryLesson | null }
export interface TimetableHistoryResponse { changes: TimetableChange[]; nextCursor: string | null }

const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
export const apiNotConfigured = !base && location.hostname.endsWith('.github.io');
async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  if (apiNotConfigured) throw new Error('API 서버 주소가 설정되지 않았어요. 빌드 시 VITE_API_BASE_URL을 지정해 주세요.');
  const timeout = AbortSignal.timeout(15_000);
  try {
    const response = await fetch(`${base}${path}`, {
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) {
      if (response.status === 503) {
        const body = typeof response.clone === 'function'
          ? await response.clone().json().catch(() => null) as { code?: string } | null
          : null;
        if (body?.code === 'history_disabled') throw Object.assign(new Error('이 학교는 변경 이력을 제공하지 않습니다.'), { code: body.code });
      }
      throw new Error(`요청을 완료하지 못했어요. (${response.status})`);
    }
    return await response.json() as T;
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timeout.aborted) throw new Error('서버 응답이 늦어요. 잠시 후 다시 시도해 주세요.');
    if (error instanceof TypeError) throw new Error('서버에 연결할 수 없어요. 네트워크 연결을 확인하고 다시 시도해 주세요.');
    throw error;
  }
}
export const searchSchools = (q: string, signal?: AbortSignal) => get<{ schools: School[]; stale: boolean }>(`/api/v1/schools?q=${encodeURIComponent(q)}`, signal);
export const searchNeisSchools = (q: string, signal?: AbortSignal) => get<{ schools: NeisSchool[]; stale: boolean }>(`/api/v1/neis/schools?q=${encodeURIComponent(q)}`, signal);
export const getTimetable = (school: string, week: string, signal?: AbortSignal) => get<TimetableResponse>(`/api/v1/timetable?school=${encodeURIComponent(school)}&week=${encodeURIComponent(week)}`, signal);
export type SubscriptionMode = 'summary' | 'periods';
export const timetableSubscriptionUrl = (school: string, grade: number, classroom: number, mode: SubscriptionMode = 'periods') =>
  new URL(`${base}/api/v1/timetable.ics?school=${encodeURIComponent(school)}&grade=${grade}&class=${classroom}&weeks=2${mode === 'summary' ? '&mode=summary' : ''}`, location.origin).href;
export const getMeals = (school: string, from: string, to: string, signal?: AbortSignal) => get<MealsResponse>(`/api/v1/meals?school=${encodeURIComponent(school)}&from=${from}&to=${to}`, signal);
export const getTimetableHistory = (school: string, week: string, cursor?: string | null, signal?: AbortSignal) => get<TimetableHistoryResponse>(`/api/v1/timetable/history?school=${encodeURIComponent(school)}&week=${encodeURIComponent(week)}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`, signal);
