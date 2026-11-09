import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { compile } from 'svelte/compiler';

test('school search announcements stay mounted while results update', async () => {
  const component = await readFile(new URL('../src/App.svelte', import.meta.url), 'utf8');
  const schoolSearch = component.match(/<input id="school"[\s\S]*?<\/div>([\s\S]*?)<\/div>\n      <div class="selectors">/)?.[0];
  const neisSearch = component.match(/<input id="neis"[\s\S]*?<\/div>([\s\S]*?)<\/div>\{#if neis\}/)?.[0];

  for (const [name, markup, state, results] of [
    ['timetable', schoolSearch, 'schoolSearchState', 'schoolResults'],
    ['meal', neisSearch, 'neisSearchState', 'neisResults'],
  ]) {
    assert.ok(markup, `${name} search markup exists`);
    const liveRegion = markup.indexOf('aria-live="polite"');
    const conditionalResults = markup.indexOf('{#if ');
    assert.notEqual(liveRegion, -1, `${name} search exposes a live region`);
    assert.ok(conditionalResults > liveRegion, `${name} live region is outside the conditional results`);
    const announcement = markup.slice(liveRegion, conditionalResults);
    assert.match(announcement, new RegExp(state));
    assert.match(announcement, new RegExp(`${results}\\.length`));
  }

  assert.doesNotThrow(() => compile(component, { filename: 'App.svelte' }));
});
