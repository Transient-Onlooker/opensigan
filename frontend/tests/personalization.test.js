import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

const source = await readFile(new URL('../src/personalization.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const helpers = {};
runInNewContext(compiled, { exports: helpers });
const { defaultDisplaySettings, parseDisplaySettings, displaySubject, displayTeacher, subjectColor, subjectTextColor } = helpers;

test('ended lesson and other weekday visibility settings default safely and parse saved choices', () => {
  assert.equal(defaultDisplaySettings().endedLessonMode, 'dim');
  assert.equal(defaultDisplaySettings().dimOtherDays, false);
  assert.equal(parseDisplaySettings({ endedLessonMode: 'hide', dimOtherDays: true }).endedLessonMode, 'hide');
  assert.equal(parseDisplaySettings({ endedLessonMode: 'normal' }).endedLessonMode, 'normal');
  assert.equal(parseDisplaySettings({ endedLessonMode: 'invalid', dimOtherDays: 'true' }).endedLessonMode, 'dim');
  assert.equal(parseDisplaySettings({ endedLessonMode: 'invalid', dimOtherDays: 'true' }).dimOtherDays, false);
});

test('timetable display preferences load old saves and reject invalid values', () => {
  const defaults = parseDisplaySettings({ showTeachers: false });
  assert.equal(defaults.showDates, true);
  assert.equal(defaults.showChangeHighlights, true);
  assert.equal(defaults.showChangeBadges, true);
  assert.equal(defaults.showCellBorders, true);
  assert.equal(defaults.density, 'normal');

  const custom = parseDisplaySettings({ showDates: false, showChangeHighlights: false, showChangeBadges: false, showCellBorders: false, density: 'compact' });
  assert.equal(custom.showDates, false);
  assert.equal(custom.showChangeHighlights, false);
  assert.equal(custom.showChangeBadges, false);
  assert.equal(custom.showCellBorders, false);
  assert.equal(custom.density, 'compact');
  assert.equal(parseDisplaySettings({ density: 'relaxed' }).density, 'relaxed');

  const invalid = parseDisplaySettings({ showDates: 'false', showChangeHighlights: null, showChangeBadges: 0, showCellBorders: 'no', density: 'extra' });
  assert.equal(invalid.showDates, true);
  assert.equal(invalid.showChangeHighlights, true);
  assert.equal(invalid.showChangeBadges, true);
  assert.equal(invalid.showCellBorders, true);
  assert.equal(invalid.density, 'normal');
});

test('default settings keep monochrome and original labels', () => {
  const settings = defaultDisplaySettings();
  assert.equal(settings.colorMode, 'none');
  assert.equal(settings.showTeachers, true);
  assert.equal(displaySubject('수학Ⅱ', settings), '수학Ⅱ');
  assert.equal(displayTeacher('김철수', settings), '김철수');
  assert.equal(subjectColor('수학Ⅱ', settings), undefined);
});

test('custom names change only displayed labels', () => {
  const settings = parseDisplaySettings({
    subjectAliases: { '수학Ⅱ': '수2' },
    teacherAliases: { '김철수': '김T' },
    teacherPrefix: '담당 ',
    teacherSuffix: ' 선생님',
  });
  assert.equal(displaySubject('수학Ⅱ', settings), '수2');
  assert.equal(displayTeacher('김철수', settings), '담당 김T 선생님');
  assert.equal(settings.subjectAliases['수학Ⅱ'], '수2');
  assert.equal(displaySubject('물리', settings), '물리');
});

test('malformed persisted colors and values are ignored', () => {
  const settings = parseDisplaySettings({
    colorMode: 'custom',
    subjectColors: { 수학: '#123abc', 과학: 'red' },
    subjectAliases: { 국어: 23 },
    showTeachers: false,
  });
  assert.equal(settings.subjectColors['수학'], '#123abc');
  assert.equal(settings.subjectColors['과학'], undefined);
  assert.equal(settings.subjectAliases['국어'], undefined);
  assert.equal(settings.showTeachers, false);
  assert.equal(subjectColor('수학', settings), '#123abc');
  assert.equal(subjectTextColor('#000000'), '#ffffff');
  assert.equal(subjectTextColor('#ffffff'), '#111111');
  assert.equal(parseDisplaySettings({ colorMode: 'other' }).colorMode, 'none');
});

test('automatic colors are stable for the same original subject', () => {
  const settings = parseDisplaySettings({ colorMode: 'auto', subjectAliases: { 수학: '수2' } });
  const original = subjectColor('수학', settings);
  assert.match(original, /^#[a-f0-9]{6}$/i);
  assert.equal(subjectColor('수학', settings), original);
  assert.equal(subjectColor('수학', parseDisplaySettings({ colorMode: 'auto' })), original);
});
