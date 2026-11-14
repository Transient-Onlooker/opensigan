import { parseDisplaySettings, type DisplaySettings } from './personalization';
import { parseLessonTimes, type LessonTimes } from './lesson-times';

export const MAX_SETTINGS_BACKUP_BYTES = 64 * 1024;

type ClassroomScope = { grade: number; classroom: number };

export function createSettingsBackup(schoolId: string, displaySettings: DisplaySettings, lessonTimes: LessonTimes, scope?: ClassroomScope): string {
  return JSON.stringify({
    format: 'opencigan-settings',
    version: 1,
    schoolId,
    displaySettings: parseDisplaySettings(displaySettings),
    ...(scope ? { scope } : { lessonTimes: parseLessonTimes(lessonTimes) }),
  }, null, 2);
}

export function parseSettingsBackup(text: string, schoolId: string, scope?: ClassroomScope): { displaySettings: DisplaySettings; lessonTimes: LessonTimes; scoped?: true } {
  if (new TextEncoder().encode(text).length > MAX_SETTINGS_BACKUP_BYTES) throw new Error('설정 파일은 64KB 이하여야 해요.');
  let raw: unknown;
  try { raw = JSON.parse(text); } catch { throw new Error('올바른 JSON 설정 파일이 아니에요.'); }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('Opencigan 설정 파일이 아니에요.');
  const backup = raw as Record<string, unknown>;
  if (backup.format !== 'opencigan-settings' || backup.version !== 1) throw new Error('지원하지 않는 설정 파일 형식이에요.');
  if (backup.schoolId !== schoolId) throw new Error('현재 선택한 학교의 설정 파일만 불러올 수 있어요.');
  if (backup.scope !== undefined) {
    const target = backup.scope as Partial<ClassroomScope> | null;
    if (!target || !scope || target.grade !== scope.grade || target.classroom !== scope.classroom) {
      throw new Error('현재 선택한 학급의 설정 파일만 불러올 수 있어요.');
    }
  }
  if (!backup.displaySettings || typeof backup.displaySettings !== 'object' || Array.isArray(backup.displaySettings) ||
      (backup.scope === undefined && (!backup.lessonTimes || typeof backup.lessonTimes !== 'object' || Array.isArray(backup.lessonTimes)))) {
    throw new Error('시간표 표시 설정이나 교시 시각 정보가 누락되었어요.');
  }
  const display = backup.displaySettings as Record<string, unknown>;
  if (!('colorMode' in display) || !('showTeachers' in display)) throw new Error('표시 설정이 불완전해요.');
  if (backup.scope !== undefined) return { displaySettings: parseDisplaySettings(display), lessonTimes: {}, scoped: true };
  const lessonTimes = parseLessonTimes(backup.lessonTimes);
  if (Object.keys(lessonTimes).length !== Object.keys(backup.lessonTimes as object).length) {
    throw new Error('교시 시각이 잘못되었거나 서로 겹쳐요.');
  }
  return { displaySettings: parseDisplaySettings(display), lessonTimes };
}
