import type { TimetableRecord } from './api';

export function slotLessons(records: TimetableRecord[], date: string, period: number, classroom?: number): TimetableRecord[] {
  return records.filter((record) => record.date === date && Number(record.period) === period &&
    (classroom === undefined || Number(record.class) === classroom));
}
