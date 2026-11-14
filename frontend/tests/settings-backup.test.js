import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

async function loadModule(filename, imports = {}) {
  const source = await readFile(new URL(`../src/${filename}`, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  runInNewContext(compiled, { exports, require: (path) => imports[path], TextEncoder });
  return exports;
}

const personalization = await loadModule('personalization.ts');
const lessonTimes = await loadModule('lesson-times.ts');
const { createSettingsBackup, parseSettingsBackup, MAX_SETTINGS_BACKUP_BYTES } = await loadModule('settings-backup.ts', {
  './personalization': personalization,
  './lesson-times': lessonTimes,
});

const schoolId = 'test-school-123';
const display = { ...personalization.defaultDisplaySettings(), showTeachers: false, density: 'compact', subjectAliases: { math: 'M' } };
const times = { 1: { start: '09:00', end: '09:50' }, 2: { start: '10:00', end: '10:50' } };

test('export and import round trip preserves school settings without allergy preferences', () => {
  const exported = createSettingsBackup(schoolId, display, times);
  const parsed = JSON.parse(exported);
  assert.equal(parsed.version, 1);
  assert.equal(parsed.schoolId, schoolId);
  assert.equal(parsed.allergySelection, undefined);
  const restored = parseSettingsBackup(exported, schoolId);
  assert.equal(restored.displaySettings.showTeachers, false);
  assert.equal(restored.displaySettings.density, 'compact');
  assert.equal(restored.displaySettings.subjectAliases.math, 'M');
  assert.equal(restored.lessonTimes[2].start, '10:00');
});

test('rejects malformed, foreign-school, obsolete and oversized backup files', () => {
  const original = JSON.parse(createSettingsBackup(schoolId, display, times));
  assert.throws(() => parseSettingsBackup('{', schoolId), /JSON/);
  assert.throws(() => parseSettingsBackup(JSON.stringify(original), 'other-school'), /학교/);
  assert.throws(() => parseSettingsBackup(JSON.stringify({ ...original, version: 100 }), schoolId));
  assert.throws(() => parseSettingsBackup(' '.repeat(MAX_SETTINGS_BACKUP_BYTES + 1), schoolId), /64KB/);
  assert.throws(() => parseSettingsBackup(JSON.stringify({ ...original, lessonTimes: null }), schoolId));
});

test('rejects invalid period numbers and overlapping class times instead of silently dropping them', () => {
  const original = JSON.parse(createSettingsBackup(schoolId, display, times));
  assert.throws(() => parseSettingsBackup(JSON.stringify({ ...original, lessonTimes: { ...times, 21: times[1] } }), schoolId));
  assert.throws(() => parseSettingsBackup(JSON.stringify({ ...original, lessonTimes: { ...times, 2: { start: '09:30', end: '10:10' } } }), schoolId));
  assert.throws(() => parseSettingsBackup(JSON.stringify({ ...original, lessonTimes: { 1: { start: '25:00', end: '26:00' } } }), schoolId));
});

test('classroom backups restore only into the matching class and omit school bell times', () => {
  const scope = { grade: 1, classroom: 2 };
  const exported = createSettingsBackup(schoolId, display, times, scope);
  assert.equal(JSON.parse(exported).lessonTimes, undefined);
  assert.equal(parseSettingsBackup(exported, schoolId, scope).scoped, true);
  assert.equal(parseSettingsBackup(exported, schoolId, scope).displaySettings.density, 'compact');
  assert.throws(() => parseSettingsBackup(exported, schoolId, { ...scope, classroom: 3 }), /학급/);
  assert.throws(() => parseSettingsBackup(exported, schoolId), /학급/);
});
