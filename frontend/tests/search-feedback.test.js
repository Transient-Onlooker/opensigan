import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { compile } from 'svelte/compiler';

test('school search announcement stays mounted while results update and meal connection status is announced', async () => {
  const component = await readFile(new URL('../src/App.svelte', import.meta.url), 'utf8');
  const schoolSearch = component.match(/<input id="school"[\s\S]*?<\/div>([\s\S]*?)<\/div>\s*<div class="selectors">/)?.[0];
  assert.ok(schoolSearch, 'school search markup exists');

  const liveRegion = schoolSearch.indexOf('aria-live="polite"');
  const conditionalResults = schoolSearch.indexOf('{#if ');
  assert.notEqual(liveRegion, -1, 'school search exposes a live region');
  assert.ok(conditionalResults > liveRegion, 'school live region is outside the conditional results');
  const announcement = schoolSearch.slice(liveRegion, conditionalResults);
  assert.match(announcement, /schoolSearchState/);
  assert.match(announcement, /schoolResults\.length/);

  // Meal connection status announcement region
  const mealConnection = component.match(/<div class="meal-connection" aria-live="polite">([\s\S]*?)<\/div>/)?.[0];
  assert.ok(mealConnection, 'meal-connection live region exists');
  assert.match(mealConnection, /neisSearchState/);

  assert.doesNotThrow(() => compile(component, { filename: 'App.svelte' }));
});
