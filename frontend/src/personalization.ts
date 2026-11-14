export type ColorMode = 'none' | 'auto' | 'custom';

export interface DisplaySettings {
  colorMode: ColorMode;
  endedLessonMode: 'dim' | 'hide' | 'normal';
  dimOtherDays: boolean;
  subjectColors: Record<string, string>;
  subjectAliases: Record<string, string>;
  teacherAliases: Record<string, string>;
  teacherPrefix: string;
  teacherSuffix: string;
  showTeachers: boolean;
}

export function defaultDisplaySettings(): DisplaySettings {
  return { colorMode: 'none', endedLessonMode: 'dim', dimOtherDays: false, subjectColors: {}, subjectAliases: {}, teacherAliases: {}, teacherPrefix: '', teacherSuffix: '', showTeachers: true };
}

function textMap(value: unknown, maxLength: number): Record<string, string> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).slice(0, 250)
    .filter(([key, item]) => key.length <= 100 && typeof item === 'string' && item.length <= maxLength && item.trim())
    .map(([key, item]) => [key, (item as string).trim()]));
}

export function parseDisplaySettings(value: unknown): DisplaySettings {
  const defaults = defaultDisplaySettings();
  if (!value || typeof value !== 'object' || Array.isArray(value)) return defaults;
  const saved = value as Partial<DisplaySettings>;
  const colors = textMap(saved.subjectColors, 7);
  return {
    colorMode: saved.colorMode === 'auto' || saved.colorMode === 'custom' ? saved.colorMode : 'none',
    endedLessonMode: saved.endedLessonMode === 'hide' || saved.endedLessonMode === 'normal' ? saved.endedLessonMode : 'dim',
    dimOtherDays: saved.dimOtherDays === true,
    subjectColors: Object.fromEntries(Object.entries(colors).filter(([, color]) => /^#[0-9a-fA-F]{6}$/.test(color))),
    subjectAliases: textMap(saved.subjectAliases, 60),
    teacherAliases: textMap(saved.teacherAliases, 60),
    teacherPrefix: typeof saved.teacherPrefix === 'string' ? saved.teacherPrefix.slice(0, 30) : '',
    teacherSuffix: typeof saved.teacherSuffix === 'string' ? saved.teacherSuffix.slice(0, 30) : '',
    showTeachers: saved.showTeachers !== false,
  };
}

export function displaySubject(subject: string | null | undefined, settings: DisplaySettings) {
  if (!subject) return '수업 정보 없음';
  return settings.subjectAliases[subject]?.trim() || subject;
}

export function displayTeacher(teacher: string | null | undefined, settings: DisplaySettings) {
  if (!teacher) return '교사 정보 없음';
  return `${settings.teacherPrefix}${settings.teacherAliases[teacher]?.trim() || teacher}${settings.teacherSuffix}`;
}

const palette = ['#DCEBFD', '#E3F1E5', '#FCE7DA', '#F1E6FD', '#F8E8EF', '#E1F1F1', '#F1EEDA', '#E5EAF2', '#FCEAC8', '#E9E3E3'];

export function subjectColor(subject: string | null | undefined, settings: DisplaySettings): string | undefined {
  if (!subject || settings.colorMode === 'none') return undefined;
  if (settings.colorMode === 'custom') {
    const color = settings.subjectColors[subject];
    return color && /^#[0-9a-fA-F]{6}$/.test(color) ? color : undefined;
  }
  let hash = 0;
  for (const letter of subject) hash = (Math.imul(hash, 31) + letter.codePointAt(0)!) | 0;
  return palette[(hash >>> 0) % palette.length];
}

export function subjectTextColor(color: string): string {
  const [r, g, b] = [1, 3, 5].map((index) => parseInt(color.slice(index, index + 2), 16));
  const brightness = (r * 299 + g * 587 + b * 114) / 1000;
  return brightness >= 145 ? '#111111' : '#ffffff';
}
