<script lang="ts">
  import { onMount } from 'svelte';
  import { currentKoreaDate, monday, addDays, clampWeek } from './date';
  import { apiNotConfigured, getMeals, getTimetable, searchSchools, searchNeisSchools, type Meal, type NeisSchool, type School, type TimetableRecord, type TimetableResponse } from './api';

  let school: School | null = null;
  let neis: NeisSchool | null = null;
  let schoolQuery = '';
  let neisQuery = '';
  let schoolResults: School[] = [];
  let neisResults: NeisSchool[] = [];
  let schoolSearchState = '';
  let neisSearchState = '';
  let grade = 1;
  let classroom = 1;
  let classError = false;
  let today = currentKoreaDate(new Date());
  let current = monday(today);
  let week = current;
  let theme: 'light' | 'dark' = 'dark';
  let timetable: TimetableResponse | null = null;
  let meals: Meal[] = [];
  let mealsStale = false;
  let tableState = '';
  let mealState = '';
  let tableLoading = false;
  let mealLoading = false;
  let schoolTimer: ReturnType<typeof setTimeout>;
  let neisTimer: ReturnType<typeof setTimeout>;
  let schoolRequest: AbortController | undefined;
  let neisRequest: AbortController | undefined;
  let tableRequest: AbortController | undefined;
  let mealRequest: AbortController | undefined;

  $: filtered = (timetable?.records ?? []).filter((r) => Number(r.grade) === Number(grade) && Number(r.class) === Number(classroom));
  $: dates = Array.from({ length: filtered.some((r) => r.date === addDays(week, 5) || r.date === addDays(week, 6)) ? 7 : 5 }, (_, i) => addDays(week, i));
  $: periods = Array.from({ length: Math.max(0, ...filtered.map((r) => Number(r.period))) }, (_, i) => i + 1);
  $: sortedMeals = [...meals].sort((a, b) => a.date.localeCompare(b.date));

  function dateText(key: string, options: Intl.DateTimeFormatOptions = { month: 'numeric', day: 'numeric' }) { return new Intl.DateTimeFormat('ko-KR', { ...options, timeZone: 'UTC' }).format(new Date(`${key}T00:00:00Z`)); }
  function timeText(value: string | null | undefined) { if (!value || Number.isNaN(Date.parse(value))) return '정보 없음'; return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value)); }
  function errorText(error: unknown) { return error instanceof Error ? error.message : '요청을 완료하지 못했어요.'; }
  function record(date: string, period: number): TimetableRecord | undefined { return filtered.find((r) => r.date === date && Number(r.period) === period); }
  function neisKey(id: string) { return `opensigan-neis:${id}`; }

  function findSchool() {
    clearTimeout(schoolTimer); schoolRequest?.abort(); schoolResults = []; schoolSearchState = '';
    if (schoolQuery.trim().length < 2) return;
    schoolSearchState = '검색 중…';
    schoolTimer = setTimeout(async () => {
      const controller = new AbortController(); schoolRequest = controller;
      try { const result = await searchSchools(schoolQuery.trim(), controller.signal); if (!controller.signal.aborted) { schoolResults = result.schools; schoolSearchState = result.stale ? '저장된 검색 결과예요. 최신 정보가 아닐 수 있습니다.' : schoolResults.length ? '' : '검색 결과가 없어요.'; } }
      catch (error) { if (!controller.signal.aborted) schoolSearchState = errorText(error); }
    }, 250);
  }
  function findNeis() {
    clearTimeout(neisTimer); neisRequest?.abort(); neisResults = []; neisSearchState = '';
    if (neisQuery.trim().length < 2) return;
    neisSearchState = '검색 중…';
    neisTimer = setTimeout(async () => {
      const controller = new AbortController(); neisRequest = controller;
      try { const result = await searchNeisSchools(neisQuery.trim(), controller.signal); if (!controller.signal.aborted) { neisResults = result.schools; neisSearchState = result.stale ? '저장된 검색 결과예요. 최신 정보가 아닐 수 있습니다.' : neisResults.length ? '' : '검색 결과가 없어요.'; } }
      catch (error) { if (!controller.signal.aborted) neisSearchState = errorText(error); }
    }, 250);
  }
  function chooseSchool(value: School) {
    schoolRequest?.abort(); clearTimeout(schoolTimer); school = value; schoolQuery = value.name; schoolResults = []; schoolSearchState = '';
    try { localStorage.setItem('opensigan-school', JSON.stringify(value)); } catch { /* 현재 선택은 저장 없이 유지합니다. */ }
    neisRequest?.abort(); clearTimeout(neisTimer);
    neis = null; neisQuery = ''; neisResults = []; neisSearchState = '';
    try { const saved = localStorage.getItem(neisKey(value.id)); if (saved) neis = JSON.parse(saved) as NeisSchool; } catch { /* 저장된 설정을 사용할 수 없습니다. */ }
    if (neis) neisQuery = neis.name;
    loadTimetable(); loadMeals();
  }
  function chooseNeis(value: NeisSchool) {
    neisRequest?.abort(); clearTimeout(neisTimer); neis = value; neisQuery = value.name; neisResults = []; neisSearchState = '';
    if (school) { try { localStorage.setItem(neisKey(school.id), JSON.stringify(value)); } catch { /* 현재 선택은 저장 없이 유지합니다. */ } }
    loadMeals();
  }
  function loadTimetable() {
    tableRequest?.abort(); timetable = null; tableState = ''; tableLoading = false;
    if (!school) return;
    const controller = new AbortController(); tableRequest = controller; tableLoading = true;
    void getTimetable(school.id, week, controller.signal).then((data) => { if (!controller.signal.aborted) timetable = data; })
      .catch((error) => { if (!controller.signal.aborted) tableState = errorText(error); })
      .finally(() => { if (!controller.signal.aborted) tableLoading = false; });
  }
  function loadMeals() {
    mealRequest?.abort(); meals = []; mealsStale = false; mealState = ''; mealLoading = false;
    if (!school || !neis) return;
    const controller = new AbortController(); mealRequest = controller; mealLoading = true;
    void getMeals(neis.id, week, addDays(week, 6), controller.signal).then((data) => { if (!controller.signal.aborted) { meals = data.meals; mealsStale = data.stale; } })
      .catch((error) => { if (!controller.signal.aborted) mealState = errorText(error); })
      .finally(() => { if (!controller.signal.aborted) mealLoading = false; });
  }
  function refreshCalendar() {
    today = currentKoreaDate(new Date());
    current = monday(today);
    const validWeek = clampWeek(week, current);
    if (validWeek !== week) { week = validWeek; loadTimetable(); loadMeals(); }
  }
  function changeWeek(delta: number) { refreshCalendar(); const next = addDays(week, delta * 7); if (next < current || next > addDays(current, 7)) return; week = next; loadTimetable(); loadMeals(); }
  function currentWeek() { refreshCalendar(); week = current; loadTimetable(); loadMeals(); }
  function changeTheme() { theme = theme === 'dark' ? 'light' : 'dark'; try { localStorage.setItem('opensigan-theme', theme); } catch { /* 현재 선택은 저장 없이 유지합니다. */ } }
  function updateClass(event: Event) {
    const value = (event.currentTarget as HTMLInputElement).valueAsNumber;
    classError = !Number.isInteger(value) || value < 1 || value > 99;
    if (!classError) classroom = value;
  }
  function saveClass(event: Event) {
    updateClass(event);
    if (!classError) { try { localStorage.setItem('opensigan-class', String(classroom)); } catch { /* 현재 선택은 저장 없이 유지합니다. */ } }
  }
  function saveGrade() { try { localStorage.setItem('opensigan-grade', String(grade)); } catch { /* 현재 선택은 저장 없이 유지합니다. */ } }

  onMount(() => {
    refreshCalendar();
    const calendarTimer = setInterval(refreshCalendar, 60_000);
    const onVisibilityChange = () => { if (document.visibilityState === 'visible') refreshCalendar(); };
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('focus', refreshCalendar);
    try {
      const savedTheme = localStorage.getItem('opensigan-theme'); if (savedTheme === 'light' || savedTheme === 'dark') theme = savedTheme;
      const savedGrade = Number(localStorage.getItem('opensigan-grade')); if (savedGrade >= 1 && savedGrade <= 6) grade = savedGrade;
      const savedClass = Number(localStorage.getItem('opensigan-class')); if (Number.isInteger(savedClass) && savedClass >= 1 && savedClass <= 99) classroom = savedClass;
      const saved = localStorage.getItem('opensigan-school'); if (saved) chooseSchool(JSON.parse(saved) as School);
    } catch { /* 저장소를 사용할 수 없으면 기본 설정으로 시작합니다. */ }
    return () => { clearInterval(calendarTimer); document.removeEventListener('visibilitychange', onVisibilityChange); window.removeEventListener('focus', refreshCalendar); clearTimeout(schoolTimer); clearTimeout(neisTimer); schoolRequest?.abort(); neisRequest?.abort(); tableRequest?.abort(); mealRequest?.abort(); };
  });
</script>

<svelte:head><title>{school ? `${school.name} 시간표` : '학교 시간표'} — 오픈시간표</title></svelte:head>
<div class:dark={theme === 'dark'} class="app-shell">
  <header class="topbar"><div class="brand"><span class="brand-mark">O</span><span>오픈시간표</span></div><button class="theme-toggle" onclick={changeTheme} aria-label={theme === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환'}>{theme === 'dark' ? '☀ 라이트 모드' : '☾ 다크 모드'}</button></header>
  <main>
    <section class="page-intro"><div><p class="eyebrow">MY SCHOOL DAY</p><h1>오늘의 학교생활</h1><p class="intro-copy">시간표와 급식을 간편하게 확인해요.</p></div><div class="date-chip">{dateText(today, { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })}</div></section>
    {#if apiNotConfigured}<div class="config-notice" role="alert"><strong>API 서버 주소가 설정되지 않았어요.</strong> GitHub Pages 배포 시 <code>VITE_API_BASE_URL</code>을 지정해야 학교와 급식 정보를 불러올 수 있습니다.</div>{/if}
    <section class="school-panel" aria-label="학교 및 학급 선택">
      <div class="search-field"><label for="school">시간표 학교 찾기</label><div class="search-wrap"><span aria-hidden="true">⌕</span><input id="school" bind:value={schoolQuery} oninput={findSchool} placeholder="학교 이름을 입력하세요" autocomplete="off"/><span class="search-hint">2글자 이상</span></div><span class="sr-only" aria-live="polite">{schoolSearchState || (schoolResults.length ? `${schoolResults.length}개 학교 검색 결과` : '')}</span>{#if schoolResults.length || schoolSearchState}<div class="search-results">{#each schoolResults as item (item.id)}<button class="school-option" onclick={() => chooseSchool(item)}><strong>{item.name}</strong><small>{item.region}</small></button>{/each}{#if schoolSearchState}<p>{schoolSearchState}</p>{/if}</div>{/if}</div>
      <div class="selectors"><label for="grade">학년<select id="grade" bind:value={grade} onchange={saveGrade}>{#each [1,2,3,4,5,6] as n}<option value={n}>{n}학년</option>{/each}</select></label><label for="classroom">반<input id="classroom" type="number" min="1" max="99" step="1" required value={classroom} oninput={updateClass} onchange={saveClass} aria-invalid={classError} aria-describedby={classError ? 'class-error' : undefined}/>{#if classError}<span id="class-error" role="alert">반은 1부터 99까지의 정수로 입력해 주세요.</span>{/if}</label></div>
      <div class="school-caption">{#if school}<span>✓ {school.name} <span class="muted">{school.region}</span></span>{:else}<span>학교를 검색해 선택해 주세요.</span>{/if}</div>
    </section>
    <section class="timetable-section" aria-labelledby="timetable-title"><div class="section-heading"><div><p class="eyebrow">CLASS SCHEDULE</p><h2 id="timetable-title">주간 시간표</h2></div><div class="week-control"><button onclick={() => changeWeek(-1)} disabled={week <= current} aria-label="이전 주">←</button><span>{dateText(week)} — {dateText(addDays(week, 6))}</span><button onclick={() => changeWeek(1)} disabled={week >= addDays(current, 7)} aria-label="다음 주">→</button><button class="today-button" onclick={currentWeek}>오늘</button></div></div>
      {#if timetable}<div class="freshness" aria-live="polite"><span class="status-dot"></span><strong>{timetable.stale ? '저장된 시간표 · 최신 정보가 아닐 수 있어요' : '시간표 조회 완료'}</strong><span>원본 갱신 {timeText(timetable.sourceUpdatedAt)}</span><span>마지막 수집 {timeText(timetable.fetchedAt)}</span></div>{/if}
      {#if tableState}<div class="state-message" role="alert"><strong>시간표를 불러오지 못했어요.</strong><span>{tableState}</span><button class="text-button" onclick={loadTimetable}>다시 시도</button></div>{:else if !school}<div class="state-message"><strong>학교를 먼저 선택해 주세요</strong><span>학교와 학년·반을 선택하면 주간 시간표가 표시됩니다.</span></div>{:else if tableLoading}<div class="state-message" role="status">시간표를 불러오고 있어요.</div>{:else if classError}<div class="state-message"><strong>올바른 반을 입력해 주세요</strong><span>1부터 99까지의 정수를 입력하면 시간표를 볼 수 있습니다.</span></div>{:else if !filtered.length}<div class="state-message"><strong>시간표가 아직 없어요</strong><span>선택한 학급과 주에 등록된 수업 정보가 없습니다.</span></div>{:else}<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div class="table-scroll" tabindex="0" role="region" aria-label="시간표 (가로로 스크롤 가능)"><table class="timetable"><thead><tr><th scope="col">교시</th>{#each dates as date}<th scope="col"><span>{dateText(date, { weekday: 'short' })}</span><small>{dateText(date)}</small></th>{/each}</tr></thead><tbody>{#each periods as period}<tr><th scope="row"><span class="period-number">{String(period).padStart(2, '0')}</span><small>교시</small></th>{#each dates as date}<td>{#if record(date, period)}<div class="class-cell"><span>{record(date, period)?.subject}</span>{#if record(date, period)?.isChanged}<span class="change-label">변동</span>{/if}{#if record(date, period)?.teacher}<small>{record(date, period)?.teacher}</small>{/if}</div>{:else}<span class="empty-cell">—</span>{/if}</td>{/each}</tr>{/each}</tbody></table></div>{/if}
      <div class="legend"><span class="change-label">변동</span><span>수업 정보가 변동된 교시</span><span class="mobile-hint">표를 좌우로 움직여 보세요</span></div>
    </section>
    <section class="meals-section" aria-labelledby="meals-title"><div class="section-heading"><div><p class="eyebrow">THIS WEEK</p><h2 id="meals-title">이번 주 급식</h2></div><span class="meal-range">{dateText(week)} — {dateText(addDays(week, 6))}</span></div>
      {#if school}<div class="neis-panel"><div><strong>급식 학교 선택</strong><p>학교명과 주소를 확인하고 직접 선택해 주세요.</p></div><div class="search-field neis-search"><label class="sr-only" for="neis">NEIS 급식 학교 찾기</label><div class="search-wrap"><span aria-hidden="true">⌕</span><input id="neis" bind:value={neisQuery} oninput={findNeis} placeholder="급식 학교 검색" autocomplete="off"/></div><span class="sr-only" aria-live="polite">{neisSearchState || (neisResults.length ? `${neisResults.length}개 급식 학교 검색 결과` : '')}</span>{#if neisResults.length || neisSearchState}<div class="search-results">{#each neisResults as item (item.id)}<button class="school-option neis-option" onclick={() => chooseNeis(item)}><strong>{item.name}</strong><small>{item.region} · {item.address}</small></button>{/each}{#if neisSearchState}<p>{neisSearchState}</p>{/if}</div>{/if}</div>{#if neis}<div class="neis-selected">✓ {neis.name} · {neis.region} · {neis.address}</div>{/if}</div>{/if}
      {#if mealState}<div class="state-message" role="alert"><strong>급식을 불러오지 못했어요.</strong><span>{mealState}</span><button class="text-button" onclick={loadMeals}>다시 시도</button></div>{:else if !school}<div class="state-message compact">시간표 학교를 먼저 선택해 주세요.</div>{:else if !neis}<div class="state-message compact">급식을 보려면 급식 학교를 직접 선택해 주세요.</div>{:else if mealLoading}<div class="state-message compact" role="status">급식을 불러오고 있어요.</div>{:else if !sortedMeals.length}<div class="state-message compact">이번 주 등록된 급식 정보가 없어요.</div>{:else}<div class="meal-list">{#each sortedMeals as meal, i (i)}<article class="meal-row"><div class="meal-date"><strong>{dateText(meal.date)}</strong><span>{dateText(meal.date, { weekday: 'long' })}</span></div><div class="meal-type">{meal.type}</div><ul class="dishes">{#each meal.dishes as dish}<li>{dish}</li>{/each}</ul></article>{/each}</div>{/if}
      {#if neis && !mealLoading && !mealState && mealsStale}<p class="meal-stale">저장된 급식 정보예요. 최신 정보가 아닐 수 있습니다.</p>{/if}
    </section><footer><span>오픈시간표</span><span>학교와 학급 설정은 이 기기에 저장됩니다.</span></footer>
  </main>
</div>
