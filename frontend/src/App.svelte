<script lang="ts">
  import { onMount } from 'svelte';
  import { currentKoreaDate, monday, addDays, clampWeek } from './date';
  import { resolveMealSchool, mealSchoolCandidates } from './neis-match';
  import { apiNotConfigured, getMeals, getTimetable, searchSchools, searchNeisSchools, type Meal, type NeisSchool, type School, type TimetableRecord, type TimetableResponse } from './api';

  let school: School | null = null;
  let neis: NeisSchool | null = null;
  let schoolQuery = '';
  let schoolResults: School[] = [];
  let neisResults: NeisSchool[] = [];
  let schoolSearchState = '';
  let neisSearchState = '';
  let neisLoading = false;
  let schoolEditorOpen = true;
  let view: 'timetable' | 'meals' = 'timetable';
  let grade = 1;
  let classroom = 1;
  let classError = false;
  let today = currentKoreaDate(new Date());
  let current = monday(today);
  let week = current;
  let mealDate = today;
  let dateError = '';
  let theme: 'light' | 'dark' = 'light';
  let timetable: TimetableResponse | null = null;
  let meals: Meal[] = [];
  let hasMeals = false;
  let mealsStale = false;
  let tableState = '';
  let mealState = '';
  let tableLoading = false;
  let mealLoading = false;
  let mealDataKey = '';
  let mealRequestKey = '';
  const mealTypes = ['조식', '중식', '석식'];
  const refreshInterval = 30 * 60 * 1000;
  let timetableRefreshAt = 0;
  let mealsRefreshAt = 0;
  let schoolTimer: ReturnType<typeof setTimeout>;
  let schoolRequest: AbortController | undefined;
  let neisRequest: AbortController | undefined;
  let tableRequest: AbortController | undefined;
  let mealRequest: AbortController | undefined;

  $: filtered = (timetable?.records ?? []).filter((r) => Number(r.grade) === Number(grade) && Number(r.class) === Number(classroom));
  $: weekendClasses = filtered.some((r) => r.date === addDays(week, 5) || r.date === addDays(week, 6));
  $: dates = Array.from({ length: weekendClasses ? 7 : 5 }, (_, i) => addDays(week, i));
  $: periods = Array.from({ length: Math.max(0, ...filtered.map((r) => Number(r.period))) }, (_, i) => i + 1);
  $: dayMeals = meals.filter((meal) => meal.date === mealDate);

  function dateText(key: string, options: Intl.DateTimeFormatOptions = { month: 'numeric', day: 'numeric' }) {
    return new Intl.DateTimeFormat('ko-KR', { ...options, timeZone: 'UTC' }).format(new Date(key + 'T00:00:00Z'));
  }
  function timeText(value: string | null | undefined) {
    if (!value || Number.isNaN(Date.parse(value))) return '정보 없음';
    return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
  }
  function errorText(error: unknown) { return error instanceof Error ? error.message : '요청을 완료하지 못했어요.'; }
  function record(date: string, period: number): TimetableRecord | undefined { return filtered.find((r) => r.date === date && Number(r.period) === period); }
  function neisKey(id: string) { return 'opensigan-neis:' + id; }

  function findSchool() {
    clearTimeout(schoolTimer); schoolRequest?.abort(); schoolResults = []; schoolSearchState = '';
    if (schoolQuery.trim().length < 2) return;
    schoolSearchState = '검색 중…';
    schoolTimer = setTimeout(async () => {
      const controller = new AbortController(); schoolRequest = controller;
      try {
        const result = await searchSchools(schoolQuery.trim(), controller.signal);
        if (!controller.signal.aborted) {
          schoolResults = result.schools;
          schoolSearchState = result.stale ? '저장된 검색 결과예요. 최신 정보가 아닐 수 있습니다.' : schoolResults.length ? '' : '검색 결과가 없어요.';
        }
      } catch (error) { if (!controller.signal.aborted) schoolSearchState = errorText(error); }
    }, 250);
  }
  function chooseSchool(value: School) {
    schoolRequest?.abort(); clearTimeout(schoolTimer); neisRequest?.abort(); mealRequest?.abort();
    school = value; schoolQuery = value.name; schoolResults = []; schoolSearchState = ''; schoolEditorOpen = false;
    neis = null; neisResults = []; neisSearchState = ''; neisLoading = false;
    meals = []; hasMeals = false; mealsStale = false; mealState = ''; mealLoading = false; mealDataKey = ''; mealRequestKey = '';
    try { localStorage.setItem('opensigan-school', JSON.stringify(value)); } catch { /* 현재 선택은 저장 없이 유지합니다. */ }
    loadTimetable();
    try {
      const saved = localStorage.getItem(neisKey(value.id));
      if (saved) {
        const candidate = JSON.parse(saved) as NeisSchool;
        if (resolveMealSchool(value, [candidate])) { chooseNeis(candidate); return; }
      }
    } catch { /* 사용할 수 없는 저장 정보는 다시 조회합니다. */ }
    void connectMeals(value);
  }
  async function connectMeals(value: School | null = school) {
    if (!value) return;
    neisRequest?.abort();
    const controller = new AbortController(); neisRequest = controller;
    neisLoading = true; neisResults = []; neisSearchState = '같은 학교의 급식을 연결하고 있어요.';
    try {
      const result = await searchNeisSchools(value.name, controller.signal);
      if (controller.signal.aborted || school?.id !== value.id) return;
      const match = resolveMealSchool(value, result.schools);
      if (match) chooseNeis(match);
      else {
        neisResults = mealSchoolCandidates(value, result.schools);
        neisSearchState = neisResults.length ? '같은 이름의 학교가 여러 곳이에요. 주소만 확인해 주세요.' : '같은 학교의 급식 정보를 찾지 못했어요.';
      }
    } catch (error) {
      if (!controller.signal.aborted && school?.id === value.id) neisSearchState = errorText(error);
    } finally {
      if (!controller.signal.aborted && school?.id === value.id) neisLoading = false;
    }
  }
  function chooseNeis(value: NeisSchool) {
    neisRequest?.abort(); neis = value; neisResults = []; neisLoading = false;
    neisSearchState = '급식도 ' + value.name + '로 연결했어요.';
    if (school) { try { localStorage.setItem(neisKey(school.id), JSON.stringify(value)); } catch { /* 현재 연결은 저장 없이 유지합니다. */ } }
    loadMeals();
  }
  function loadTimetable(preserve = false) {
    tableRequest?.abort(); if (!preserve) timetable = null; tableState = ''; tableLoading = false;
    if (!school) return;
    timetableRefreshAt = Date.now() + refreshInterval;
    const controller = new AbortController(); tableRequest = controller; tableLoading = true;
    void getTimetable(school.id, week, controller.signal)
      .then((data) => { if (!controller.signal.aborted) timetable = data; })
      .catch((error) => { if (!controller.signal.aborted) tableState = errorText(error); })
      .finally(() => { if (!controller.signal.aborted) tableLoading = false; });
  }
  function loadMeals(preserve = false) {
    if (!school || !neis) return;
    const from = monday(mealDate);
    const key = neis.id + ':' + from;
    if (!preserve && hasMeals && mealDataKey === key && !mealLoading && Date.now() < mealsRefreshAt) return;
    if (mealLoading && mealRequestKey === key && !mealRequest?.signal.aborted) return;
    mealRequest?.abort();
    if (!preserve || mealDataKey !== key) { meals = []; mealsStale = false; hasMeals = false; }
    mealState = ''; mealsRefreshAt = Date.now() + refreshInterval;
    const controller = new AbortController(); mealRequest = controller; mealLoading = true; mealRequestKey = key;
    void getMeals(neis.id, from, addDays(from, 6), controller.signal)
      .then((data) => { if (!controller.signal.aborted) { meals = data.meals; mealsStale = data.stale; hasMeals = true; mealDataKey = key; } })
      .catch((error) => { if (!controller.signal.aborted) mealState = errorText(error); })
      .finally(() => { if (!controller.signal.aborted) mealLoading = false; });
  }
  function refreshCalendar() {
    const previousToday = today;
    today = currentKoreaDate(new Date()); current = monday(today);
    const validWeek = clampWeek(week, current);
    if (validWeek !== week) { week = validWeek; loadTimetable(); }
    if (mealDate === previousToday && today !== previousToday) { mealDate = today; loadMeals(); }
    if (document.visibilityState === 'visible') {
      const now = Date.now();
      if (school && !tableLoading && now >= timetableRefreshAt) loadTimetable(true);
      if (school && neis && !mealLoading && now >= mealsRefreshAt) loadMeals(true);
    }
  }
  function changeWeek(delta: number) {
    refreshCalendar(); const next = addDays(week, delta * 7);
    if (next < current || next > addDays(current, 7)) return;
    week = next; loadTimetable();
  }
  function currentWeek() { refreshCalendar(); const preserve = week === current; week = current; loadTimetable(preserve); }
  function changeMealDate(delta: number) { mealDate = addDays(mealDate, delta); dateError = ''; loadMeals(); }
  function todayMeals() { refreshCalendar(); mealDate = today; dateError = ''; loadMeals(); }
  function selectMealDate(event: Event) {
    const value = (event.currentTarget as HTMLInputElement).value;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || Number.isNaN(Date.parse(value + 'T00:00:00Z'))) { dateError = '날짜를 선택해 주세요.'; return; }
    mealDate = value; dateError = ''; loadMeals();
  }
  function changeTheme() {
    theme = theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('opensigan-theme', theme); } catch { /* 현재 선택은 저장 없이 유지합니다. */ }
  }
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
    return () => {
      clearInterval(calendarTimer); document.removeEventListener('visibilitychange', onVisibilityChange); window.removeEventListener('focus', refreshCalendar);
      clearTimeout(schoolTimer); schoolRequest?.abort(); neisRequest?.abort(); tableRequest?.abort(); mealRequest?.abort();
    };
  });
</script>

<svelte:head><title>{school?.name ?? '내 학교 캘린더'} — Opencigan</title></svelte:head>
<div class:dark={theme === 'dark'} class="app-shell">
  <a class="skip-link" href="#calendar">캘린더 본문으로 건너뛰기</a>
  <header class="topbar">
    <div class="brand"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m18 16 4-4-4-4M6 8l-4 4 4 4M14.5 4l-5 16"/></svg></span><span>Opencigan</span></div>
    <button class="theme-toggle" onclick={changeTheme} aria-label={theme === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환'}>{theme === 'dark' ? '라이트 모드' : '다크 모드'}</button>
  </header>
  <main>
    <section class="school-heading" aria-label="선택한 학교">
      <div><p class="eyebrow">내 학교 캘린더</p><h1>{school?.name ?? '어느 학교에 다니나요?'}</h1><p class="school-facts">{school ? school.region + ' · ' + grade + '학년 ' + classroom + '반' : '학교를 한 번 고르면 시간표와 급식을 함께 볼 수 있어요.'}</p></div>
      {#if school}<button class="secondary-button" onclick={() => schoolEditorOpen = !schoolEditorOpen} aria-expanded={schoolEditorOpen} aria-controls="school-settings">학교·학급 변경</button>{/if}
    </section>
    {#if apiNotConfigured}<p class="notice" role="alert">학교 정보를 불러올 API 주소가 설정되지 않았어요.</p>{/if}
    {#if schoolEditorOpen || !school}
      <section id="school-settings" class="school-panel" aria-label="학교 및 학급 선택">
        <div class="search-field">
          <label for="school">학교 찾기</label>
          <div class="search-wrap"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m16 16 4 4"/></svg><input id="school" type="search" bind:value={schoolQuery} oninput={findSchool} onkeydown={(event) => { if (event.key === 'Escape') { clearTimeout(schoolTimer); schoolRequest?.abort(); schoolResults = []; schoolSearchState = ''; } }} placeholder="학교 이름 두 글자 이상" autocomplete="off" /></div>
          <span class="sr-only" aria-live="polite">{schoolSearchState || (schoolResults.length ? schoolResults.length + '개 학교 검색 결과' : '')}</span>
          {#if schoolResults.length || schoolSearchState}
            <div class="search-results">
              {#each schoolResults as item (item.id)}<button class="school-option" onclick={() => chooseSchool(item)}><strong>{item.name}</strong><span>{item.region}</span></button>{/each}
              {#if schoolSearchState}<p>{schoolSearchState}</p>{/if}
            </div>
          {/if}
        </div>
        <div class="selectors">
          <label for="grade">학년<select id="grade" bind:value={grade} onchange={saveGrade}>{#each [1,2,3,4,5,6] as n}<option value={n}>{n}학년</option>{/each}</select></label>
          <label for="classroom">반<input id="classroom" type="number" min="1" max="99" step="1" required value={classroom} oninput={updateClass} onchange={saveClass} aria-invalid={classError} aria-describedby={classError ? 'class-error' : undefined} /></label>
        </div>
        {#if classError}<p id="class-error" class="notice" role="alert">반은 1부터 99까지의 정수로 입력해 주세요.</p>{/if}
      </section>
    {/if}
    <nav class="calendar-menu" aria-label="캘린더 메뉴">
      <span class="menu-label">캘린더</span>
      <button aria-pressed={view === 'timetable'} aria-controls="timetable-panel" onclick={() => view = 'timetable'}><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3" y="5" width="18" height="16"/><path d="M7 3v4m10-4v4M3 10h18M8 14h3m2 0h3m-8 3h3m2 0h3"/></svg> 시간표</button>
      <button aria-pressed={view === 'meals'} aria-controls="meals-panel" onclick={() => view = 'meals'}><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M4 3v6a3 3 0 0 0 6 0V3M7 3v18M16 21V3c3 1 4 4 4 8h-4"/></svg> 급식</button>
    </nav>
    <div id="calendar" class="calendar-content" tabindex="-1">
        <section id="timetable-panel" hidden={view !== 'timetable'} aria-labelledby="timetable-title">
          <div class="section-heading"><div><p class="eyebrow">{week === current ? '이번 주' : '다음 주'}</p><h2 id="timetable-title">우리 반 시간표</h2></div><button class="secondary-button" onclick={currentWeek}>이번 주로</button></div>
          <div class="calendar-toolbar"><button class="arrow-button" onclick={() => changeWeek(-1)} disabled={week <= current} aria-label="이전 주">←</button><div class="calendar-date" aria-live="polite"><strong>{dateText(week)} — {dateText(addDays(week, weekendClasses ? 6 : 4))}</strong><span>{weekendClasses ? '월요일부터 일요일' : '월요일부터 금요일'}</span></div><button class="arrow-button" onclick={() => changeWeek(1)} disabled={week >= addDays(current, 7)} aria-label="다음 주">→</button></div>
          {#if tableState}<div class="notice" role="alert">{timetable ? '이전 시간표를 표시하고 있어요. ' : ''}{tableState} <button class="text-button" onclick={() => loadTimetable(!!timetable)}>다시 시도</button></div>{/if}
          {#if !school}<div class="state-message"><strong>학교를 먼저 선택해 주세요</strong><p>학교와 학급을 선택하면 시간표가 표시돼요.</p></div>
          {:else if tableLoading && !timetable}<div class="state-message" role="status"><strong>시간표를 불러오고 있어요.</strong></div>
          {:else if classError}<div class="state-message">반을 1부터 99까지의 정수로 입력해 주세요.</div>
          {:else if timetable && filtered.length}
            <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
            <div class="table-scroll" tabindex="0" role="region" aria-label="주간 시간표, 좌우로 스크롤 가능">
              <table class="timetable"><caption class="sr-only">{school.name} {grade}학년 {classroom}반 주간 시간표</caption><thead><tr><th scope="col">교시</th>{#each dates as date}<th scope="col" class:today-column={date === today} aria-current={date === today ? 'date' : undefined}><span>{dateText(date, { weekday: 'short' })}</span><small>{dateText(date)}{date === today ? ' · 오늘' : ''}</small></th>{/each}</tr></thead>
                <tbody>{#each periods as period}<tr><th scope="row">{period}<span class="sr-only">교시</span></th>{#each dates as date}<td class:today-column={date === today} class:changed={record(date, period)?.isChanged}>{#if record(date, period)}<div class="class-cell"><strong>{record(date, period)?.subject || '수업 정보 없음'}</strong>{#if record(date, period)?.teacher}<span>{record(date, period)?.teacher}</span>{/if}{#if record(date, period)?.isChanged}<span class="change-label">변동</span>{/if}</div>{:else}<span class="empty-cell" aria-label="수업 없음">—</span>{/if}</td>{/each}</tr>{/each}</tbody>
              </table>
            </div>
            <p class="table-hint">‘변동’ 표시가 있는 교시는 수업 정보가 변경됐어요. <span>휴대폰에서는 표를 좌우로 밀어 보세요.</span></p>
          {:else if !tableState}<div class="state-message"><strong>등록된 시간표가 없어요.</strong><p>학교와 학년·반을 확인해 주세요.</p></div>{/if}
          {#if timetable}<div class="freshness" aria-live="polite"><span>{timetable.stale ? '저장된 시간표 · 최신 정보가 아닐 수 있어요' : tableLoading ? '시간표 갱신 중…' : '시간표 조회 완료'}</span><span>원본 갱신 {timeText(timetable.sourceUpdatedAt)}</span><span>마지막 수집 {timeText(timetable.fetchedAt)}</span></div>{/if}
        </section>
        <section id="meals-panel" hidden={view !== 'meals'} aria-labelledby="meals-title">
          <div class="section-heading"><div><p class="eyebrow">{mealDate === today ? '오늘의 식단' : '하루 식단'}</p><h2 id="meals-title">학교 급식</h2></div><button class="secondary-button" onclick={todayMeals}>오늘로</button></div>
          <div class="calendar-toolbar"><button class="arrow-button" onclick={() => changeMealDate(-1)} aria-label="이전 날짜">←</button><div class="calendar-date"><strong aria-live="polite">{dateText(mealDate, { month: 'long', day: 'numeric', weekday: 'long' })}</strong><label class="date-picker">날짜 선택 <input type="date" value={mealDate} onchange={selectMealDate} aria-invalid={!!dateError} /></label></div><button class="arrow-button" onclick={() => changeMealDate(1)} aria-label="다음 날짜">→</button></div>
          {#if dateError}<p class="notice" role="alert">{dateError}</p>{/if}
          <div class="meal-connection" aria-live="polite">{#if neis}<span>{neis.name} · {neis.address} · 급식 연결됨</span>{:else if school}<span>{neisSearchState}</span>{/if}</div>
          {#if !school}<div class="state-message"><strong>학교를 먼저 선택해 주세요</strong><p>시간표 학교를 선택하면 급식도 함께 연결돼요.</p></div>
          {:else if neisLoading}<div class="state-message" role="status">같은 학교의 급식을 연결하고 있어요.</div>
          {:else if !neis}
            <div class="connection-options">{#each neisResults as item (item.id)}<button class="school-option" onclick={() => chooseNeis(item)}><strong>{item.name}</strong><span>{item.address}</span></button>{/each}<button class="text-button" onclick={() => connectMeals()}>급식 연결 다시 시도</button></div>
          {:else}
            {#if mealState}<div class="notice" role="alert">{hasMeals ? '이전 급식 정보를 표시하고 있어요. ' : ''}{mealState} <button class="text-button" onclick={() => loadMeals(true)}>다시 시도</button></div>{/if}
            {#if mealLoading && !hasMeals}<div class="state-message" role="status">식단을 불러오고 있어요.</div>
            {:else if hasMeals}
              <div class="meal-cards">{#each mealTypes as type}<article class="meal-card" aria-label={dateText(mealDate) + ' ' + type}><div class="meal-card-heading"><h3>{type}</h3><span>{type === '조식' ? '아침' : type === '중식' ? '점심' : '저녁'}</span></div>{#if dayMeals.some((meal) => meal.type === type)}<ul class="dishes">{#each dayMeals.filter((meal) => meal.type === type) as meal}{#each meal.dishes as dish}<li>{dish}</li>{/each}{/each}</ul>{:else}<p class="no-meal">등록된 {type} 식단이 없어요.</p>{/if}</article>{/each}</div>
              <p class="meal-note">식단 뒤의 숫자는 알레르기 정보예요. 학교에서 안내하는 원본 식단도 확인해 주세요.</p>
            {/if}
            {#if mealsStale}<p class="notice">저장된 급식 정보예요. 최신 정보가 아닐 수 있습니다.</p>{/if}
          {/if}
        </section>
    </div>
    <footer><p>학교·학급 설정은 이 기기에 저장돼요.</p><div class="footer-open"><svg class="github-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 .75a11.25 11.25 0 0 0-3.56 21.92c.56.1.77-.24.77-.54v-2.1c-3.13.68-3.79-1.33-3.79-1.33-.51-1.3-1.25-1.64-1.25-1.64-1.02-.7.08-.69.08-.69 1.13.08 1.72 1.16 1.72 1.16 1 1.72 2.63 1.22 3.27.93.1-.72.39-1.22.7-1.5-2.5-.28-5.13-1.25-5.13-5.56 0-1.23.44-2.24 1.16-3.03-.12-.28-.5-1.43.11-2.98 0 0 .95-.3 3.1 1.16A10.8 10.8 0 0 1 12 6.17c.96 0 1.92.13 2.82.38 2.15-1.46 3.1-1.16 3.1-1.16.61 1.55.23 2.7.11 2.98.72.79 1.16 1.8 1.16 3.03 0 4.32-2.63 5.27-5.14 5.55.4.35.76 1.03.76 2.08v3.1c0 .3.2.65.78.54A11.25 11.25 0 0 0 12 .75Z"/></svg><div><strong>함께 만드는 오픈소스</strong><p>Opencigan은 오픈소스 프로젝트예요. GitHub에서 함께 기여해 주세요.</p><div class="footer-links"><a href="https://github.com/Transient-Onlooker/opensigan">Opencigan GitHub ↗</a><a href="https://github.com/hegelty/pycomcigan">pycomcigan ↗</a><a href="https://transient-onlooker.github.io/opensigan/">Opencigan 사이트 ↗</a></div></div></div></footer>
  </main>
</div>
