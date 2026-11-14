import type { TimetableRecord } from './api';

export type LessonTimes = Record<number, { start: string; end: string }>;

function minutes(value: string): number | null {
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(value)) return null;
  const [hours, part] = value.split(':').map(Number);
  return hours * 60 + part;
}

export function parseLessonTimes(value: unknown): LessonTimes {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const result: LessonTimes = {};
  for (const [rawPeriod, rawEntry] of Object.entries(value)) {
    const period = Number(rawPeriod);
    if (!Number.isInteger(period) || period < 1 || period > 20 || !rawEntry || typeof rawEntry !== 'object') continue;
    const entry = rawEntry as { start?: unknown; end?: unknown };
    if (typeof entry.start !== 'string' || typeof entry.end !== 'string') continue;
    const start = minutes(entry.start);
    const end = minutes(entry.end);
    if (start === null || end === null || start >= end) continue;
    result[period] = { start: entry.start, end: entry.end };
  }
  const ordered = Object.entries(result).sort(([a], [b]) => Number(a) - Number(b)).map(([, entry]) => entry);
  if (ordered.some((entry, index) => index > 0 && entry.start < ordered[index - 1].end)) return {};
  return result;
}

export function koreaClockMinutes(now: Date): number {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(now);
  const getPart = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? 0);
  return getPart('hour') * 60 + getPart('minute');
}

export function dailyLessonOverview(records: TimetableRecord[], times: LessonTimes, nowMinute: number, isToday: boolean) {
  const groups = new Map<number, TimetableRecord[]>();
  for (const record of records) {
    const period = Number(record.period);
    if (!Number.isInteger(period) || period < 1) continue;
    groups.set(period, [...(groups.get(period) ?? []), record]);
  }
  const periods = [...groups.keys()].sort((a, b) => a - b);
  const changed = periods.filter((period) => groups.get(period)?.some((record) => record.isChanged)).length;
  const hasTimes = isToday && periods.length > 0 && periods.every((period) => {
    const entry = times[period];
    return entry && minutes(entry.start) !== null && minutes(entry.end) !== null;
  });
  if (!hasTimes) return { total: periods.length, changed, timed: false, current: null, next: null, remaining: null, completed: [] as number[] };
  const current = periods.find((period) => minutes(times[period].start)! <= nowMinute && nowMinute < minutes(times[period].end)!);
  const next = periods.find((period) => minutes(times[period].start)! > nowMinute);
  const remaining = periods.filter((period) => minutes(times[period].end)! > nowMinute).length;
  const completed = periods.filter((period) => minutes(times[period].end)! <= nowMinute);
  const label = (period: number | undefined) => period === undefined ? null : ({ period, lessons: groups.get(period) ?? [], time: times[period] });
  return { total: periods.length, changed, timed: true, current: label(current), next: label(next), remaining, completed };
}
