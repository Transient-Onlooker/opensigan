<script lang="ts">
  import { onMount } from 'svelte';
  import { currentKoreaDate, monday, addDays, clampWeek } from './date';
  import { resolveMealSchool, mealSchoolCandidates } from './neis-match';
  import { trackPageView } from './analytics';
  import { shareClassUrl, readSharedClass, findLessons } from './sharing';
  import { allergens, allergenMatches, withoutAllergenNumbers } from './allergens';
  import { saveTimetablePng } from './export-png';
  import { slotLessons } from './timetable-slots';
  import { dailyLessonOverview, koreaClockMinutes, parseLessonTimes, type LessonTimes } from './lesson-times';
  import { defaultDisplaySettings, parseDisplaySettings, displaySubject, displayTeacher, subjectColor, subjectTextColor, type ColorMode, type DisplaySettings } from './personalization';
  import { apiNotConfigured, getMeals, getTimetable, getTimetableHistory, searchSchools, searchNeisSchools, timetableSubscriptionUrl, type Meal, type NeisSchool, type School, type TimetableRecord, type TimetableResponse, type TimetableChange } from './api';

  type Favorite = { school: School; grade: number; classroom: number };
  let school: School | null = null;
  let favorites: Favorite[] = [];
  let neis: NeisSchool | null = null;
  let schoolQuery = '';
  let schoolResults: School[] = [];
  let neisResults: NeisSchool[] = [];
  let schoolSearchState = '';
  let neisSearchState = '';
  let neisLoading = false;
  let schoolEditorOpen = true;
  let view: 'timetable' | 'meals' = 'timetable';
  let timetableView: 'today' | 'week' | 'grade' | 'teacher' = typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 700px)').matches ? 'today' : 'week';
  let teacherQuery = '';
  let displaySettings: DisplaySettings = defaultDisplaySettings();
  let lessonTimes: LessonTimes = {};
  let lessonTimeDrafts: Record<number, { start: string; end: string }> = {};
  let lessonTimeState = '';
  let selectedSubject = '';
  let selectedTeacher = '';
  let allergySelection: number[] = [];
  let tableRefreshState = '';
  let exportState = '';
  let lessonQuery = '';
  let lessonWeekday = '';
  let shareUrl = '';
  let shareState = '';
  let subscriptionUrl = '';
  let subscriptionState = '';
  let grade = 1;
  let classroom = 1;
  let classError = false;
  let today = currentKoreaDate(new Date());
  let clockMinute = koreaClockMinutes(new Date());
  let selectedDay = today;
  let current = monday(today);
  let week = current;
  let mealDate = today;
  let mealView: 'day' | 'week' = 'day';
  let enabledMealTypes = ['조식', '중식', '석식'];
  let showAllergenNumbers = true;
  let dateError = '';
  let theme: 'light' | 'dark' | 'system' = 'light';
  let animationsEnabled = true;
  let systemDark = false;
  let analyticsReady = false;
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
  const timetableWeeks = new Map<string, { data: TimetableResponse; expires: number }>();
  let timetableRefreshAt = 0;
  let mealsRefreshAt = 0;
  let schoolTimer: ReturnType<typeof setTimeout>;
  let schoolRequest: AbortController | undefined;
  let neisRequest: AbortController | undefined;
  let tableRequest: AbortController | undefined;
  let mealRequest: AbortController | undefined;
  let historyOpen = false;
  let historyLoading = false;
  let historyDisabled = false;
  let historyError = '';
  let historyChanges: TimetableChange[] = [];
  let historyCursor: string | null = null;
  let historyRequest: AbortController | undefined;
  let historyRequestKey = '';

  $: filtered = (timetable?.records ?? []).filter((r) => Number(r.grade) === Number(grade) && Number(r.class) === Number(classroom));
  $: dayRecords = (timetable?.records ?? []).filter((r) => r.date === selectedDay);
  $: selectedClassLessons = dayRecords.filter((r) => Number(r.grade) === Number(grade) && Number(r.class) === Number(classroom)).sort((a, b) => Number(a.period) - Number(b.period));
  $: dayOverview = dailyLessonOverview(selectedClassLessons, lessonTimes, clockMinute, selectedDay === today);
  $: shownClassLessons = displaySettings.endedLessonMode === 'hide' ? selectedClassLessons.filter((item) => !dayOverview.completed.includes(Number(item.period))) : selectedClassLessons;
  $: comparableClasses = [...new Set(dayRecords.filter((r) => Number(r.grade) === Number(grade)).map((r) => Number(r.class)))].sort((a, b) => a - b);
  $: gradeRecords = dayRecords.filter((r) => Number(r.grade) === Number(grade));
  $: teacherNames = [...new Set((timetable?.records ?? []).map((r) => r.teacher?.trim()).filter((name): name is string => !!name))].sort((a, b) => a.localeCompare(b, 'ko-KR'));
  $: observedClassCount = new Set((timetable?.records ?? []).filter((r) => Number.isInteger(Number(r.grade)) && Number(r.grade) > 0 && Number.isInteger(Number(r.class)) && Number(r.class) > 0).map((r) => `${Number(r.grade)}:${Number(r.class)}`)).size;
  $: subjectNames = [...new Set((timetable?.records ?? []).map((r) => r.subject?.trim()).filter((name): name is string => !!name))].sort((a, b) => a.localeCompare(b, 'ko-KR'));
  $: teacherSuggestions = teacherNames.filter((name) => [name, displayTeacher(name, displaySettings)].some((label) => label.toLocaleLowerCase('ko-KR').includes(teacherQuery.trim().toLocaleLowerCase('ko-KR'))));
  $: selectedTeacherName = teacherNames.find((name) => name === teacherQuery.trim() || displayTeacher(name, displaySettings) === teacherQuery.trim()) ?? '';
  $: selectedTeacherRecords = selectedTeacherName ? (timetable?.records ?? []).filter((r) => r.teacher?.trim() === selectedTeacherName) : [];
  $: teacherPeriods = Array.from({ length: Math.max(0, ...selectedTeacherRecords.map((r) => Number(r.period))) }, (_, i) => i + 1);
  $: teacherDates = Array.from({ length: 5 }, (_, i) => addDays(week, i));
  $: availableGrades = gradesInTimetable(timetable?.records ?? [], school && /(?:중학교|고등학교)/.test(school.name) ? 3 : 6);
  $: gradeOptions = availableGrades.length ? availableGrades : school && /(?:중학교|고등학교)/.test(school.name) ? [1, 2, 3] : [1, 2, 3, 4, 5, 6];
  $: availableClasses = [...new Set((timetable?.records ?? []).filter((r) => Number(r.grade) === Number(grade)).map((r) => Number(r.class)).filter((n) => Number.isInteger(n) && n > 0))].sort((a, b) => a - b);
  $: weekendClasses = filtered.some((r) => r.date === addDays(week, 5) || r.date === addDays(week, 6));
  $: dates = Array.from({ length: weekendClasses ? 7 : 5 }, (_, i) => addDays(week, i));
  $: periods = Array.from({ length: Math.max(0, ...filtered.map((r) => Number(r.period))) }, (_, i) => i + 1);
  $: lessonTimePeriods = Array.from({ length: Math.max(8, ...((timetable?.records ?? []).map((r) => Number(r.period)).filter((period) => Number.isInteger(period) && period > 0 && period <= 20))) }, (_, i) => i + 1);
  $: dayMeals = meals.filter((meal) => meal.date === mealDate);
  $: visibleMealTypes = mealTypes.filter((type) => enabledMealTypes.includes(type));
  $: mealDates = Array.from({ length: 7 }, (_, index) => addDays(monday(mealDate), index));
  $: matchingLessons = lessonQuery.trim() || lessonWeekday ? findLessons(filtered, lessonQuery, lessonWeekday) : [];
  $: currentFavorite = favorites.some((item) => item.school.id === school?.id && item.grade === Number(grade) && item.classroom === Number(classroom));
  $: isDark = themeIsDark(theme, systemDark);
  $: if (analyticsReady) trackPageView(view === 'meals' ? '/meals' : '/timetable');

  function dateText(key: string, options: Intl.DateTimeFormatOptions = { month: 'numeric', day: 'numeric' }) {
    return new Intl.DateTimeFormat('ko-KR', { ...options, timeZone: 'UTC' }).format(new Date(key + 'T00:00:00Z'));
  }
  function shortDate(key: string) {
    const [, month, day] = key.split('-').map(Number);
    return `${month}.${day}`;
  }
  function timeText(value: string | null | undefined) {
    if (!value || Number.isNaN(Date.parse(value))) return '정보 없음';
    return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
  }
  function changeTypeText(type: string) { return type === 'added' ? '추가' : type === 'deleted' ? '삭제' : type === 'changed' ? '변경' : type; }
  function errorText(error: unknown) { return error instanceof Error ? error.message : '요청을 완료하지 못했어요.'; }
  function neisKey(id: string) { return 'opensigan-neis:' + id; }

  function themeIsDark(preference: 'light' | 'dark' | 'system', prefersDark: boolean) {
    return preference === 'dark' || (preference === 'system' && prefersDark);
  }

  function gradesInTimetable(records: TimetableRecord[], maxGrade: number) {
    return [...new Set(records.map((record) => Number(record.grade))
      .filter((value) => Number.isInteger(value) && value >= 1 && value <= maxGrade))].sort((a, b) => a - b);
  }

  function subjectStyle(subject: string | null | undefined) {
    const color = subjectColor(subject, displaySettings);
    return color ? `background-color:${color};color:${subjectTextColor(color)}` : undefined;
  }
  function saveDisplaySettings(next: DisplaySettings) {
    displaySettings = next;
    if (school) { try { localStorage.setItem('opensigan-display:' + school.id, JSON.stringify(next)); } catch { /* 현재 설정은 페이지에서 유지됩니다. */ } }
  }
  function saveAlias(kind: 'subject' | 'teacher', key: string, value: string) {
    if (!key) return;
    const property = kind === 'subject' ? 'subjectAliases' : 'teacherAliases';
    const aliases = { ...displaySettings[property] };
    if (value.trim()) aliases[key] = value.trim().slice(0, 60);
    else delete aliases[key];
    saveDisplaySettings({ ...displaySettings, [property]: aliases });
  }
  function saveSubjectColor(value: string) {
    if (!selectedSubject || !/^#[0-9a-fA-F]{6}$/.test(value)) return;
    saveDisplaySettings({ ...displaySettings, subjectColors: { ...displaySettings.subjectColors, [selectedSubject]: value } });
  }
  function setColorMode(value: string) {
    if (value === 'none' || value === 'auto' || value === 'custom') saveDisplaySettings({ ...displaySettings, colorMode: value as ColorMode });
  }
  function clearSubjectColors() { saveDisplaySettings({ ...displaySettings, subjectColors: {} }); }

  function editLessonTime(period: number, part: 'start' | 'end', value: string) {
    lessonTimeDrafts = { ...lessonTimeDrafts, [period]: { start: lessonTimeDrafts[period]?.start ?? '', end: lessonTimeDrafts[period]?.end ?? '', [part]: value } };
    lessonTimeState = '';
  }
  function saveLessonTimes() {
    if (!school) return;
    const entries = Object.entries(lessonTimeDrafts).filter(([, entry]) => entry.start || entry.end);
    const parsed = parseLessonTimes(Object.fromEntries(entries));
    if (entries.length !== Object.keys(parsed).length) {
      lessonTimeState = '각 교시의 시작·종료 시각을 모두 입력하고, 시간 순서와 겹침 여부를 확인해 주세요.';
      return;
    }
    lessonTimes = parsed;
    lessonTimeState = '이 학교의 교시 시각을 저장했어요.';
    try { localStorage.setItem('opensigan-lesson-times:' + school.id, JSON.stringify(lessonTimes)); }
    catch { lessonTimeState = '현재 화면에만 적용됐어요. 브라우저 저장소를 확인해 주세요.'; }
  }
  function clearLessonTimes() {
    lessonTimeDrafts = {}; lessonTimes = {}; lessonTimeState = '교시 시각을 초기화했어요.';
    if (school) { try { localStorage.removeItem('opensigan-lesson-times:' + school.id); } catch { /* 현재 화면에서 삭제했습니다. */ } }
  }

  function toggleAllergy(id: number, checked: boolean) {
    allergySelection = checked ? [...new Set([...allergySelection, id])].sort((a, b) => a - b) : allergySelection.filter((value) => value !== id);
    try { localStorage.setItem('opensigan-allergies', JSON.stringify(allergySelection)); } catch { /* 설정은 현재 페이지에서 유지됩니다. */ }
  }

  function saveMealPreferences() {
    try { localStorage.setItem('opensigan-meal-preferences', JSON.stringify({ view: mealView, types: enabledMealTypes, showAllergenNumbers })); }
    catch { /* 설정은 현재 페이지에서 유지됩니다. */ }
  }
  function setMealView(value: 'day' | 'week') { mealView = value; saveMealPreferences(); }
  function toggleMealType(type: string, checked: boolean) {
    const next = checked ? [...enabledMealTypes, type] : enabledMealTypes.filter((item) => item !== type);
    if (!next.length) return;
    enabledMealTypes = mealTypes.filter((item) => next.includes(item));
    saveMealPreferences();
  }
  function setAllergenNumbersVisible(value: boolean) { showAllergenNumbers = value; saveMealPreferences(); }

  function loadFavorites() {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem('opensigan-favorites') || '[]');
      if (!Array.isArray(saved)) return;
      const valid: Favorite[] = [];
      for (const entry of saved) {
        if (!entry || typeof entry !== 'object') continue;
        const item = entry as Partial<Favorite>;
        const value = item.school;
        if (!value || typeof value.id !== 'string' || !/^[0-9]+:[^:]{1,50}$/.test(value.id) || value.id.length > 100 ||
            typeof value.name !== 'string' || !value.name.trim() || value.name.length > 50 ||
            typeof value.region !== 'string' || value.region.length > 100 ||
            !Number.isInteger(item.grade) || Number(item.grade) < 1 || Number(item.grade) > 6 ||
            !Number.isInteger(item.classroom) || Number(item.classroom) < 1 || Number(item.classroom) > 99) continue;
        if (!valid.some((previous) => previous.school.id === value.id && previous.grade === item.grade && previous.classroom === item.classroom)) {
          valid.push({ school: { id: value.id, name: value.name, region: value.region }, grade: Number(item.grade), classroom: Number(item.classroom) });
        }
        if (valid.length === 10) break;
      }
      favorites = valid;
    } catch { favorites = []; }
  }
  function saveFavorites() {
    try { localStorage.setItem('opensigan-favorites', JSON.stringify(favorites)); } catch { /* 브라우저 저장이 차단되어도 현재 화면은 동작합니다. */ }
  }
  function addFavorite() {
    if (!school || classError || favorites.length >= 10 ||
        favorites.some((item) => item.school.id === school?.id && item.grade === Number(grade) && item.classroom === Number(classroom))) return;
    favorites = [...favorites, { school: { ...school }, grade: Number(grade), classroom: Number(classroom) }];
    saveFavorites();
  }
  function removeFavorite(favorite: Favorite) {
    favorites = favorites.filter((item) => !(item.school.id === favorite.school.id && item.grade === favorite.grade && item.classroom === favorite.classroom));
    saveFavorites();
  }
  function switchToFavorite(favorite: Favorite) {
    grade = favorite.grade; classroom = favorite.classroom; classError = false;
    shareUrl = ''; shareState = ''; subscriptionUrl = ''; subscriptionState = '';
    if (school?.id !== favorite.school.id) chooseSchool(favorite.school, true);
    else { schoolEditorOpen = false; ensureAvailableClass(); }
    try {
      localStorage.setItem('opensigan-grade', String(grade));
      localStorage.setItem('opensigan-class', String(classroom));
    } catch { /* 현재 선택은 저장 없이 유지합니다. */ }
  }

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
  function chooseSchool(value: School, keepClass = false) {
    tableRefreshState = '';
    exportState = '';
    if (school?.id !== value.id && !keepClass) { grade = 1; classroom = 1; classError = false; }
    if (/(?:중학교|고등학교)/.test(value.name) && grade > 3) grade = 1;
    shareUrl = ''; shareState = ''; subscriptionUrl = ''; subscriptionState = '';
    schoolRequest?.abort(); clearTimeout(schoolTimer); neisRequest?.abort(); mealRequest?.abort(); historyRequest?.abort();
    school = value; schoolQuery = value.name; schoolResults = []; schoolSearchState = ''; schoolEditorOpen = false;
    selectedSubject = ''; selectedTeacher = ''; teacherQuery = '';
    try { displaySettings = parseDisplaySettings(JSON.parse(localStorage.getItem('opensigan-display:' + value.id) || 'null')); }
    catch { displaySettings = defaultDisplaySettings(); }
    try { lessonTimes = parseLessonTimes(JSON.parse(localStorage.getItem('opensigan-lesson-times:' + value.id) || 'null')); }
    catch { lessonTimes = {}; }
    lessonTimeDrafts = { ...lessonTimes }; lessonTimeState = '';
    historyChanges = []; historyCursor = null; historyDisabled = false; historyError = ''; historyLoading = false; historyOpen = false; historyRequestKey = '';
    neis = null; neisResults = []; neisSearchState = ''; neisLoading = false;
    meals = []; hasMeals = false; mealsStale = false; mealState = ''; mealLoading = false; mealDataKey = ''; mealRequestKey = '';
    try {
      localStorage.setItem('opensigan-school', JSON.stringify(value));
      localStorage.setItem('opensigan-grade', String(grade));
      localStorage.setItem('opensigan-class', String(classroom));
    } catch { /* 현재 선택은 저장 없이 유지합니다. */ }
    loadTimetable(false, true, true);
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
  function ensureAvailableClass() {
    const grades = gradesInTimetable(timetable?.records ?? [], school && /(?:중학교|고등학교)/.test(school.name) ? 3 : 6);
    const previousGrade = Number(grade);
    const previousClass = Number(classroom);
    if (grades.length && !grades.includes(previousGrade)) grade = grades[0];
    const options = [...new Set((timetable?.records ?? []).filter((record) => Number(record.grade) === Number(grade))
      .map((record) => Number(record.class)).filter((value) => Number.isInteger(value) && value > 0))].sort((a, b) => a - b);
    if (options.length && !options.includes(Number(classroom))) classroom = options[0];
    if (previousGrade === Number(grade) && previousClass === Number(classroom)) return;
    classError = false;
    shareUrl = ''; shareState = ''; subscriptionUrl = ''; subscriptionState = '';
    try { localStorage.setItem('opensigan-grade', String(grade)); localStorage.setItem('opensigan-class', String(classroom)); } catch { /* 현재 선택을 유지합니다. */ }
  }
  function loadTimetable(preserve = false, reuseCachedWeek = false, validateClass = false) {
    tableRequest?.abort(); if (!preserve) timetable = null; tableState = ''; tableLoading = false;
    if (!school) return;
    const key = `${school.id}\u0000${week}`;
    if (reuseCachedWeek) {
      const cached = timetableWeeks.get(key);
      if (cached && cached.expires > Date.now()) {
        timetable = cached.data;
        if (validateClass) ensureAvailableClass();
        timetableRefreshAt = cached.expires;
        return;
      }
      timetableWeeks.delete(key);
    }
    timetableRefreshAt = Date.now() + refreshInterval;
    const controller = new AbortController(); tableRequest = controller; tableLoading = true;
    void getTimetable(school.id, week, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        timetable = data;
        if (validateClass) ensureAvailableClass();
        if (tableRefreshState === '갱신 중') tableRefreshState = data.stale ? '저장된 시간표 표시 중' : '새로고침 완료';
        if (!data.stale) {
          timetableWeeks.delete(key);
          timetableWeeks.set(key, { data, expires: Date.now() + refreshInterval });
          if (timetableWeeks.size > 4) timetableWeeks.delete(timetableWeeks.keys().next().value!);
        }
      })
      .catch((error) => { if (!controller.signal.aborted) { tableState = errorText(error); if (tableRefreshState === '갱신 중') tableRefreshState = '새로고침 실패'; } })
      .finally(() => { if (!controller.signal.aborted) tableLoading = false; });
  }
  async function loadHistory(append = false) {
    if (!school || historyDisabled || historyLoading) return;
    const capturedSchoolId = school.id;
    const capturedWeek = week;
    const requestKey = `${capturedSchoolId}\u0000${capturedWeek}`;
    const controller = new AbortController(); historyRequest?.abort(); historyRequest = controller; historyRequestKey = requestKey;
    historyLoading = true; historyError = '';
    try {
      const data = await getTimetableHistory(capturedSchoolId, capturedWeek, append ? historyCursor : null, controller.signal);
      if (!controller.signal.aborted && historyRequestKey === requestKey && school?.id === capturedSchoolId && week === capturedWeek) { historyChanges = append ? [...historyChanges, ...data.changes] : data.changes; historyCursor = data.nextCursor; }
    } catch (error) {
      if (!controller.signal.aborted && historyRequestKey === requestKey && school?.id === capturedSchoolId && week === capturedWeek) {
        if (typeof error === 'object' && error !== null && 'code' in error && error.code === 'history_disabled') historyDisabled = true;
        else historyError = errorText(error);
      }
    }
    finally { if (!controller.signal.aborted && historyRequestKey === requestKey && school?.id === capturedSchoolId && week === capturedWeek) historyLoading = false; }
  }
  function toggleHistory() {
    historyOpen = !historyOpen;
    if (historyOpen && !historyChanges.length && !historyDisabled) void loadHistory();
  }
  function selectTimetableView(value: typeof timetableView) {
    timetableView = value;
    exportState = '';
    if (value === 'today' || value === 'grade') selectedDay = week === current ? today : week;
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
  function refreshCalendar(refreshData = true) {
    const previousToday = today;
    clockMinute = koreaClockMinutes(new Date());
    today = currentKoreaDate(new Date()); current = monday(today);
    const validWeek = clampWeek(week, current);
    if (selectedDay === previousToday) selectedDay = today;
    if (validWeek !== week) {
      week = validWeek;
      selectedDay = selectedDay < week ? week : selectedDay > addDays(week, 6) ? addDays(week, 6) : selectedDay;
      historyRequest?.abort(); historyRequestKey = ''; historyChanges = []; historyCursor = null; historyDisabled = false; historyError = ''; historyLoading = false;
      if (refreshData) {
        loadTimetable();
        if (historyOpen) void loadHistory();
      }
    }
    if (mealDate === previousToday && today !== previousToday) { mealDate = today; if (refreshData) loadMeals(); }
    if (refreshData && document.visibilityState === 'visible') {
      const now = Date.now();
      if (school && !tableLoading && now >= timetableRefreshAt) loadTimetable(true);
      if (school && neis && !mealLoading && now >= mealsRefreshAt) loadMeals(true);
    }
  }
  function changeWeek(delta: number) {
    refreshCalendar(false); const next = addDays(week, delta * 7);
    if (next < current || next > addDays(current, 7)) return;
    tableRefreshState = ''; exportState = ''; teacherQuery = ''; week = next; selectedDay = week === current ? today : week; historyRequest?.abort(); historyRequestKey = ''; historyChanges = []; historyCursor = null; historyDisabled = false; historyError = ''; historyLoading = false; historyOpen = false; loadTimetable(false, true);
  }
  function currentWeek() { refreshCalendar(false); const preserve = week === current; const reopenHistory = historyOpen; tableRefreshState = ''; if (!preserve) teacherQuery = ''; week = current; selectedDay = today; historyRequest?.abort(); historyRequestKey = ''; historyChanges = []; historyCursor = null; historyDisabled = false; historyError = ''; historyLoading = false; loadTimetable(preserve); if (reopenHistory) void loadHistory(); }
  function changeMealDate(delta: number) { mealDate = addDays(mealDate, delta); dateError = ''; loadMeals(); }
  function selectTimetableDate(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const value = input.value;
    if (value && input.validity.valid && value >= week && value <= addDays(week, 6)) selectedDay = value;
    else input.value = selectedDay;
  }
  function todayMeals() { refreshCalendar(); mealDate = today; dateError = ''; loadMeals(); }
  function selectMealDate(event: Event) {
    const value = (event.currentTarget as HTMLInputElement).value;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || Number.isNaN(Date.parse(value + 'T00:00:00Z'))) { dateError = '날짜를 선택해 주세요.'; return; }
    mealDate = value; dateError = ''; loadMeals();
  }
  function setTheme(value: string) {
    if (value !== 'light' && value !== 'dark' && value !== 'system') return;
    theme = value;
    try { localStorage.setItem('opensigan-theme', theme); } catch { /* 현재 선택은 저장 없이 유지합니다. */ }
  }
  function changeTheme() { setTheme(themeIsDark(theme, systemDark) ? 'light' : 'dark'); }
  function setAnimationsEnabled(enabled: boolean) {
    animationsEnabled = enabled;
    try { localStorage.setItem('opensigan-animations', enabled ? 'on' : 'off'); } catch { /* 현재 선택은 저장 없이 유지합니다. */ }
  }
  function refreshTimetable() {
    tableRefreshState = '갱신 중';
    loadTimetable(!!timetable);
  }
  async function exportPng() {
    if (!timetable || !school || timetableView === 'grade' || classError) return;
    exportState = 'PNG를 만드는 중…';
    try {
      await saveTimetablePng({
        view: timetableView,
        schoolName: school.name,
        grade: Number(grade),
        classroom: Number(classroom),
        week,
        selectedDay,
        teacherName: selectedTeacherName,
        records: timetable.records,
        dark: isDark,
        displaySettings,
      });
      exportState = 'PNG 다운로드를 시작했어요.';
    } catch (error) { exportState = errorText(error); }
  }
  function updateClass(event: Event) {
    shareUrl = ''; shareState = ''; subscriptionUrl = ''; subscriptionState = '';
    const value = (event.currentTarget as HTMLInputElement).valueAsNumber;
    classError = !Number.isInteger(value) || value < 1 || value > 99 || (availableClasses.length > 0 && !availableClasses.includes(value));
    if (!classError) classroom = value;
  }
  function saveClass(event: Event) {
    updateClass(event);
    if (!classError) { try { localStorage.setItem('opensigan-class', String(classroom)); } catch { /* 현재 선택은 저장 없이 유지합니다. */ } }
  }
  function saveGrade() {
    shareUrl = ''; shareState = ''; subscriptionUrl = ''; subscriptionState = '';
    ensureAvailableClass();
    classError = false;
    try { localStorage.setItem('opensigan-grade', String(grade)); localStorage.setItem('opensigan-class', String(classroom)); } catch { /* 현재 선택은 저장 없이 유지합니다. */ }
  }
  function saveClassFromSelect() {
    classError = false;
    shareUrl = ''; shareState = ''; subscriptionUrl = ''; subscriptionState = '';
    try { localStorage.setItem('opensigan-class', String(classroom)); } catch { /* 현재 선택은 저장 없이 유지합니다. */ }
  }
  async function shareClass() {
    if (!school || classError) return;
    if (shareUrl) { shareUrl = ''; shareState = ''; return; }
    shareState = ''; subscriptionState = '';
    subscriptionUrl = '';
    shareUrl = shareClassUrl(window.location.href, school, Number(grade), Number(classroom));
    try {
      await navigator.clipboard.writeText(shareUrl);
      shareState = '학급 링크를 복사했어요.';
    } catch {
      shareState = '아래 링크를 선택해 복사해 주세요.';
    }
  }

  async function subscribeTimetable() {
    if (!school || classError || apiNotConfigured) return;
    if (subscriptionUrl) { subscriptionUrl = ''; subscriptionState = ''; return; }
    shareState = ''; subscriptionState = '';
    shareUrl = '';
    subscriptionUrl = timetableSubscriptionUrl(school.id, Number(grade), Number(classroom));
    try {
      await navigator.clipboard.writeText(subscriptionUrl);
      subscriptionState = '구독 링크를 복사했어요. 캘린더 앱에 URL로 추가하세요.';
    } catch {
      subscriptionState = '아래 URL을 복사해 캘린더 앱에 추가하세요.';
    }
  }

  onMount(() => {
    const shared = typeof window !== 'undefined' && window.location?.hash ? readSharedClass(window.location.hash) : null;
    analyticsReady = true;
    refreshCalendar();
    const calendarTimer = setInterval(refreshCalendar, 60_000);
    const onVisibilityChange = () => { if (document.visibilityState === 'visible') refreshCalendar(); };
    const onFocus = () => refreshCalendar();
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('focus', onFocus);
    const themeMedia = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-color-scheme: dark)') : null;
    systemDark = themeMedia?.matches ?? false;
    const onThemeMedia = (event: MediaQueryListEvent) => { systemDark = event.matches; };
    themeMedia?.addEventListener?.('change', onThemeMedia);
    loadFavorites();
    try {
      const savedAllergies: unknown = JSON.parse(localStorage.getItem('opensigan-allergies') || '[]');
      if (Array.isArray(savedAllergies)) allergySelection = [...new Set(savedAllergies.filter((id): id is number => Number.isInteger(id) && id >= 1 && id <= 19))].sort((a, b) => a - b);
      const savedMeals: unknown = JSON.parse(localStorage.getItem('opensigan-meal-preferences') || 'null');
      if (savedMeals && typeof savedMeals === 'object') {
        const preferences = savedMeals as { view?: unknown; types?: unknown; showAllergenNumbers?: unknown };
        if (preferences.view === 'day' || preferences.view === 'week') mealView = preferences.view;
        if (Array.isArray(preferences.types)) {
          const savedTypes = preferences.types.filter((type): type is string => typeof type === 'string');
          const validTypes = mealTypes.filter((type) => savedTypes.includes(type));
          if (validTypes.length) enabledMealTypes = validTypes;
        }
        if (typeof preferences.showAllergenNumbers === 'boolean') showAllergenNumbers = preferences.showAllergenNumbers;
      }
      const savedTheme = localStorage.getItem('opensigan-theme'); if (savedTheme === 'light' || savedTheme === 'dark' || savedTheme === 'system') theme = savedTheme;
      animationsEnabled = localStorage.getItem('opensigan-animations') !== 'off';
      const savedGrade = Number(localStorage.getItem('opensigan-grade')); if (savedGrade >= 1 && savedGrade <= 6) grade = savedGrade;
      const savedClass = Number(localStorage.getItem('opensigan-class')); if (Number.isInteger(savedClass) && savedClass >= 1 && savedClass <= 99) classroom = savedClass;
      const saved = localStorage.getItem('opensigan-school'); if (saved && !shared) chooseSchool(JSON.parse(saved) as School, true);
    } catch { /* 저장소를 사용할 수 없으면 기본 설정으로 시작합니다. */ }
    if (shared) { grade = shared.grade; classroom = shared.classroom; chooseSchool(shared.school, true); }
    return () => {
      clearInterval(calendarTimer); document.removeEventListener('visibilitychange', onVisibilityChange); window.removeEventListener('focus', onFocus); themeMedia?.removeEventListener?.('change', onThemeMedia); historyRequest?.abort();
      clearTimeout(schoolTimer); schoolRequest?.abort(); neisRequest?.abort(); tableRequest?.abort(); mealRequest?.abort();
    };
  });
</script>

<svelte:head><title>{school?.name ?? '내 학교 캘린더'} — Opencigan</title></svelte:head>
<div class:dark={isDark} class:motion-off={!animationsEnabled} class="app-shell">
  <a class="skip-link" href="#calendar">캘린더 본문으로 건너뛰기</a>
  <header class="topbar">
    <div class="brand"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m18 16 4-4-4-4M6 8l-4 4 4 4M14.5 4l-5 16"/></svg></span><span>Opencigan</span></div>
    <button class="theme-toggle" onclick={changeTheme} aria-label={isDark ? '라이트 모드로 전환' : '다크 모드로 전환'}>{isDark ? '라이트 모드' : '다크 모드'}</button>
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
          <label for="grade">학년<select id="grade" bind:value={grade} onchange={saveGrade}>{#each gradeOptions as n}<option value={n}>{n}학년</option>{/each}</select></label>
          <label for="classroom">반<input id="classroom" type="number" min="1" max="99" step="1" required value={classroom} oninput={updateClass} onchange={saveClass} aria-invalid={classError} aria-describedby={classError ? 'class-error' : undefined} /></label>
        </div>
        {#if classError}<p id="class-error" class="notice" role="alert">1~99 사이의 반을 입력해 주세요. 시간표가 있는 경우 등록된 반만 선택할 수 있어요.</p>{/if}
      </section>
    {/if}
    <nav class="calendar-menu" aria-label="캘린더 메뉴">
      <span class="menu-label">캘린더</span>
      <button aria-pressed={view === 'timetable'} aria-controls="timetable-panel" onclick={() => view = 'timetable'}><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3" y="5" width="18" height="16"/><path d="M7 3v4m10-4v4M3 10h18M8 14h3m2 0h3m-8 3h3m2 0h3"/></svg> 시간표</button>
      <button aria-pressed={view === 'meals'} aria-controls="meals-panel" onclick={() => view = 'meals'}><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M4 3v6a3 3 0 0 0 6 0V3M7 3v18M16 21V3c3 1 4 4 4 8h-4"/></svg> 급식</button>
    </nav>
    <div id="calendar" class="calendar-content" tabindex="-1">
        <section id="timetable-panel" hidden={view !== 'timetable'} aria-labelledby="timetable-title">
           <div class="section-heading"><div><p class="eyebrow">{week === current ? '이번 주' : '선택한 주'}</p><h2 id="timetable-title">시간표</h2></div><div class="heading-actions"><span class="last-fetched">{timetable ? '마지막 수집 ' + timeText(timetable.fetchedAt) : ''}</span>{#if timetable && timetableView !== 'grade'}<button class="secondary-button" disabled={classError || (timetableView === 'teacher' ? !selectedTeacherRecords.length : timetableView === 'today' ? !dayRecords.some((item) => Number(item.grade) === Number(grade) && Number(item.class) === Number(classroom)) : !filtered.length)} onclick={exportPng}>PNG 저장</button>{/if}<button class="secondary-button refresh-button" disabled={!school || tableLoading} onclick={refreshTimetable} aria-label="현재 표시 중인 주의 시간표 새로고침"><svg class:spinning={tableLoading} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5"/><path d="M5.4 9a7.5 7.5 0 0 1 13.3-1.4L20 12M4 12l1.3 4.4A7.5 7.5 0 0 0 18.6 15"/></svg> {tableLoading ? '갱신 중' : '새로고침'}</button><button class="secondary-button" onclick={currentWeek}>이번 주로</button></div></div>
           {#if tableRefreshState}<p class="refresh-feedback" role="status">{tableRefreshState}</p>{/if}
           {#if exportState}<p class="export-feedback" role="status">{exportState}</p>{/if}
           <div class="view-switch timetable-switch" role="group" aria-label="시간표 보기"><button aria-pressed={timetableView === 'today'} onclick={() => selectTimetableView('today')}>오늘</button><button aria-pressed={timetableView === 'week'} onclick={() => selectTimetableView('week')}>이번 주</button><button aria-pressed={timetableView === 'grade'} onclick={() => selectTimetableView('grade')}>{grade}학년</button><button aria-pressed={timetableView === 'teacher'} onclick={() => selectTimetableView('teacher')}>교사</button></div>
           {#if school}<div class="quick-class" aria-label="학급 빠른 전환"><label>학년 <select bind:value={grade} onchange={saveGrade}>{#each gradeOptions as n}<option value={n}>{n}학년</option>{/each}</select></label><label>반 <select bind:value={classroom} onchange={saveClassFromSelect}>{#if !availableClasses.length}<option value={Number(classroom)}>{classroom}반</option>{/if}{#each availableClasses as n}<option value={n}>{n}반</option>{/each}</select></label>{#if !availableClasses.length}<span class="quick-class-hint">{tableLoading ? '학급 정보를 불러오는 중이에요.' : '이 학년의 학급 정보가 없어요.'}</span>{/if}</div>{/if}
           <div class="calendar-toolbar"><button class="arrow-button" onclick={() => changeWeek(-1)} disabled={week <= current} aria-label="이전 주">←</button><div class="calendar-date" aria-live="polite"><strong>{shortDate(week)} ~ {shortDate(addDays(week, weekendClasses ? 6 : 4))}</strong></div><button class="arrow-button" onclick={() => changeWeek(1)} disabled={week >= addDays(current, 7)} aria-label="다음 주">→</button></div>
          {#if timetable && !classError && timetableView === 'week'}<details class="lesson-search"><summary>이 반의 수업 찾기</summary><div class="lesson-search-fields"><label>과목명 또는 교사명<input type="search" bind:value={lessonQuery} placeholder="이번 주 수업 검색" maxlength="100" /></label><label>요일<select bind:value={lessonWeekday}><option value="">모든 요일</option>{#each ['일', '월', '화', '수', '목', '금', '토'] as day, index}<option value={String(index)}>{day}요일</option>{/each}</select></label></div>{#if lessonQuery.trim() || lessonWeekday}<p role="status">검색 결과 {matchingLessons.length}개</p>{#if matchingLessons.length}<div class="lesson-list">{#each matchingLessons as lesson}<article><span class="lesson-period">{dateText(lesson.date, { weekday: 'short' })} · {lesson.period}교시</span><strong style={subjectStyle(lesson.subject)}>{displaySubject(lesson.subject, displaySettings)}</strong>{#if displaySettings.showTeachers && lesson.teacher}<span>{displayTeacher(lesson.teacher, displaySettings)}</span>{/if}</article>{/each}</div>{:else}<p>이 반의 이번 주 수업 중 일치하는 결과가 없어요.</p>{/if}{/if}</details>{/if}
          {#if tableState}<div class="notice" role="alert">{timetable ? '이전 시간표를 표시하고 있어요. ' : ''}{tableState} <button class="text-button" onclick={() => loadTimetable(!!timetable)}>다시 시도</button></div>{/if}
          {#if !school}<div class="state-message"><strong>학교를 먼저 선택해 주세요</strong><p>학교와 학급을 선택하면 시간표가 표시돼요.</p></div>
          {:else if tableLoading && !timetable}<div class="state-message" role="status"><strong>시간표를 불러오고 있어요.</strong></div>
          {:else if classError}<div class="state-message">반을 1부터 99까지의 정수로 입력해 주세요.</div>
          {:else if timetable && timetableView === 'today'}
            <div class="day-picker"><label for="today-date">날짜</label><input id="today-date" type="date" min={week} max={addDays(week, 6)} value={selectedDay} onchange={selectTimetableDate} /><span>{selectedDay === today ? '오늘' : dateText(selectedDay, { weekday: 'long' })}</span></div>
            {#if selectedClassLessons.length}
              <div class="day-summary" aria-live="polite">
                <span>총 {dayOverview.total}교시</span>
                {#if dayOverview.changed}<span>변동 {dayOverview.changed}교시</span>{/if}
                {#if selectedDay === today}
                  {#if dayOverview.timed}
                    <span>남은 수업 {dayOverview.remaining}교시</span>
                    {#if dayOverview.current}<strong>현재 {dayOverview.current.period}교시 · {dayOverview.current.lessons.map((lesson) => displaySubject(lesson.subject, displaySettings)).join(' / ')}</strong>{:else if !dayOverview.next}<span>오늘 수업 종료</span>{/if}
                    {#if dayOverview.next}<strong>다음 {dayOverview.next.period}교시 · {dayOverview.next.lessons.map((lesson) => displaySubject(lesson.subject, displaySettings)).join(' / ')} <small>{dayOverview.next.time.start} 시작</small></strong>{/if}
                  {:else}<span>교시 시각 설정 후 현재·다음 수업을 볼 수 있어요.</span>{/if}
                {/if}
              </div>
              <div class="lesson-list" aria-label="선택한 날짜 시간표">
                {#each shownClassLessons as item}
                  <article class:active-lesson={dayOverview.current?.period === Number(item.period)} class:completed-lesson={displaySettings.endedLessonMode === 'dim' && dayOverview.completed.includes(Number(item.period))}>
                    <span class="lesson-period">{item.period}교시{#if lessonTimes[Number(item.period)]}<small class="lesson-time">{lessonTimes[Number(item.period)].start}–{lessonTimes[Number(item.period)].end}</small>{/if}</span>
                    <strong style={subjectStyle(item.subject)}>{displaySubject(item.subject, displaySettings)}</strong>
                    {#if displaySettings.showTeachers && item.teacher}<span>{displayTeacher(item.teacher, displaySettings)}</span>{/if}
                    {#if item.isChanged}<span class="change-label">변동</span>{/if}
                  </article>
                {/each}
              </div>
              {#if !shownClassLessons.length}<p class="state-inline" role="status">종료된 수업을 모두 숨겼어요. 표시 설정에서 다시 볼 수 있어요.</p>{/if}
            {:else}<div class="state-message"><strong>이 날짜의 시간표가 없어요</strong><p>다른 날짜를 선택하거나 주간 반 시간표를 확인해 주세요.</p></div>{/if}
          {:else if timetable && timetableView === 'grade'}
            <div class="day-picker"><label for="grade-date">비교 날짜</label><input id="grade-date" type="date" min={week} max={addDays(week, 6)} value={selectedDay} onchange={selectTimetableDate} /></div>
            {#if comparableClasses.length}
              <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
               <div class="table-scroll grade-comparison-scroll" tabindex="0" role="region" aria-label={grade + '학년 학급별 비교 시간표'}><table class="timetable comparison-table"><caption class="sr-only">{school.name} {grade}학년 {dateText(selectedDay)} 학급별 교시 비교</caption><thead><tr><th scope="col">교시</th>{#each comparableClasses as classNumber}<th scope="col">{classNumber}반</th>{/each}</tr></thead><tbody>{#each Array.from({ length: Math.max(0, ...gradeRecords.map((item) => Number(item.period))) }, (_, index) => index + 1) as period}<tr><th scope="row">{period}교시</th>{#each comparableClasses as classNumber}{@const lessons = slotLessons(gradeRecords, selectedDay, period, classNumber)}<td class:changed={lessons.some((lesson) => lesson.isChanged)}>{#each lessons as lesson}<div class="class-cell"><strong style={subjectStyle(lesson.subject)}>{displaySubject(lesson.subject, displaySettings)}</strong>{#if displaySettings.showTeachers && lesson.teacher}<span>{displayTeacher(lesson.teacher, displaySettings)}</span>{/if}{#if lesson.isChanged}<span class="change-label">변동</span>{/if}</div>{:else}<span class="empty-cell">—</span>{/each}</td>{/each}</tr>{/each}</tbody></table></div>
               <div class="grade-compact" aria-label={`${grade}학년 ${dateText(selectedDay)} 학급별 비교`}>
                 {#each Array.from({ length: Math.max(0, ...gradeRecords.map((item) => Number(item.period))) }, (_, index) => index + 1) as period}
                   <section class="grade-period"><h3>{period}교시</h3><div class="grade-class-grid">
                     {#each comparableClasses as classNumber}
                       {@const lessons = slotLessons(gradeRecords, selectedDay, period, classNumber)}
                       <div class="grade-class" class:changed={lessons.some((lesson) => lesson.isChanged)}><h4>{classNumber}반</h4>
                         {#each lessons as lesson}<div class="class-cell"><strong style={subjectStyle(lesson.subject)}>{displaySubject(lesson.subject, displaySettings)}</strong>{#if displaySettings.showTeachers && lesson.teacher}<span>{displayTeacher(lesson.teacher, displaySettings)}</span>{/if}{#if lesson.isChanged}<span class="change-label">변동</span>{/if}</div>{:else}<span class="empty-cell">—</span>{/each}
                       </div>
                     {/each}
                   </div></section>
                 {/each}
               </div>
             {:else}<div class="state-message"><strong>비교할 시간표가 없어요</strong><p>선택한 날짜에 선택 학년의 수업이 없습니다.</p></div>{/if}
           {:else if timetable && timetableView === 'teacher'}
             <label class="teacher-search" for="teacher-search">교사별 주간 시간표<input id="teacher-search" type="search" bind:value={teacherQuery} placeholder="교사 이름 입력 또는 목록에서 선택" autocomplete="off" /></label>
              {#if !selectedTeacherRecords.length && teacherSuggestions.length}<div class="teacher-options" aria-label="선택 가능한 교사 목록">{#each teacherSuggestions as teacherName}<button class="secondary-button" onclick={() => teacherQuery = teacherName}>{displayTeacher(teacherName, displaySettings)}</button>{/each}</div>{/if}
             {#if selectedTeacherRecords.length}
                <p class="table-hint">{displayTeacher(selectedTeacherName, displaySettings)} 선생님 · 이번 주 수업 (동명이인은 원본 시간표에서 구분할 수 없어요.)</p>
               <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
                <div class="table-scroll" tabindex="0" role="region" aria-label={`${displayTeacher(selectedTeacherName, displaySettings)} 선생님 주간 시간표`}>
                  <table class="timetable teacher-table"><caption class="sr-only">{displayTeacher(selectedTeacherName, displaySettings)} 선생님 주간 시간표</caption><thead><tr><th scope="col">교시</th>{#each teacherDates as date}<th scope="col" class:other-day={displaySettings.dimOtherDays && week === current && date !== today}><span>{dateText(date, { weekday: 'short' })}</span><small>{dateText(date)}</small></th>{/each}</tr></thead><tbody>{#each teacherPeriods as period}<tr><th scope="row">{period}교시</th>{#each teacherDates as date}<td class:other-day={displaySettings.dimOtherDays && week === current && date !== today}>{#each selectedTeacherRecords.filter((r) => r.date === date && Number(r.period) === period) as item}<div class="class-cell"><strong>{item.grade}학년 {item.class}반</strong><span style={subjectStyle(item.subject)}>{displaySubject(item.subject, displaySettings)}</span></div>{:else}<span class="empty-cell">—</span>{/each}</td>{/each}</tr>{/each}</tbody></table>
               </div>
             {:else if teacherQuery.trim() && !teacherSuggestions.length}<div class="state-message"><strong>검색된 교사가 없어요</strong><p>다른 이름을 입력해 주세요.</p></div>{:else}<p class="table-hint">목록에서 이름을 고르면 월~금 시간표가 표시돼요.</p>{/if}
          {:else if timetable && timetableView === 'week' && filtered.length}
            <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
            <div class="table-scroll" tabindex="0" role="region" aria-label="주간 시간표, 좌우로 스크롤 가능">
              <table class="timetable"><caption class="sr-only">{school.name} {grade}학년 {classroom}반 주간 시간표</caption><thead><tr><th scope="col">교시</th>{#each dates as date}<th scope="col" class:today-column={date === today} class:other-day={displaySettings.dimOtherDays && week === current && date !== today} aria-current={date === today ? 'date' : undefined}><span>{dateText(date, { weekday: 'short' })}</span><small>{dateText(date)}{date === today ? ' · 오늘' : ''}</small></th>{/each}</tr></thead>
                 <tbody>{#each periods as period}<tr><th scope="row">{period}<span class="sr-only">교시</span></th>{#each dates as date}{@const lessons = slotLessons(filtered, date, period)}<td class:today-column={date === today} class:other-day={displaySettings.dimOtherDays && week === current && date !== today} class:changed={lessons.some((lesson) => lesson.isChanged)}>{#each lessons as lesson}<div class="class-cell"><strong style={subjectStyle(lesson.subject)}>{displaySubject(lesson.subject, displaySettings)}</strong>{#if displaySettings.showTeachers && lesson.teacher}<span>{displayTeacher(lesson.teacher, displaySettings)}</span>{/if}{#if lesson.isChanged}<span class="change-label">변동</span>{/if}</div>{:else}<span class="empty-cell" aria-label="수업 없음">—</span>{/each}</td>{/each}</tr>{/each}</tbody>
              </table>
            </div>
             <p class="table-hint">‘변동’ 표시는 수업 정보 변경을 뜻해요.</p>
          {:else if !tableState}<div class="state-message"><strong>등록된 시간표가 없어요.</strong><p>학교와 학년·반을 확인해 주세요.</p></div>{/if}
           {#if timetable}<div class="freshness" aria-live="polite">{#if timetable.stale}<span>저장된 시간표 · 최신 정보가 아닐 수 있어요</span>{/if}<span>원본 갱신 {timeText(timetable.sourceUpdatedAt)}</span></div>{/if}
           {#if timetable?.records.length}<details class="dataset-details"><summary>수업 데이터 규모 · 학급 {observedClassCount}개 · 교사 이름 {teacherNames.length}개</summary><p>선택한 주에 수집된 수업 기록 기준입니다. 학교 전체 학급·교사 수가 아닐 수 있고, 교사 이름 누락이나 동명이인이 있으면 실제 인원과 다를 수 있어요.</p></details>{/if}
           {#if school}
             <details class="display-settings">
               <summary>시간표 표시 설정</summary>
               <div class="display-settings-grid">
                <label>테마
                  <select value={theme} onchange={(event) => setTheme(event.currentTarget.value)}>
                    <option value="light">라이트 모드</option><option value="dark">다크 모드</option><option value="system">시스템 설정 따르기</option>
                  </select>
                </label>
                 <label class="display-toggle"><input type="checkbox" checked={animationsEnabled} onchange={(event) => setAnimationsEnabled(event.currentTarget.checked)} /> 애니메이션 사용</label>
                 <label>과목 색상
                   <select value={displaySettings.colorMode} onchange={(event) => setColorMode(event.currentTarget.value)}>
                     <option value="none">색상 없음 (기본)</option><option value="auto">자동 색상</option><option value="custom">직접 선택</option>
                   </select>
                 </label>
                 <label>과목 선택
                   <select bind:value={selectedSubject} disabled={!subjectNames.length}>
                     <option value="">과목을 선택하세요</option>{#each subjectNames as subject}<option value={subject}>{subject}</option>{/each}
                   </select>
                 </label>
                 <label>과목 표시 이름
                   <input type="text" value={displaySettings.subjectAliases[selectedSubject] || ''} disabled={!selectedSubject} maxlength="60" placeholder="원본 이름 유지" oninput={(event) => saveAlias('subject', selectedSubject, event.currentTarget.value)} />
                 </label>
                 {#if displaySettings.colorMode === 'custom'}
                   <label>선택한 과목 색상
                     <input type="color" value={displaySettings.subjectColors[selectedSubject] || '#dcebfD'} disabled={!selectedSubject} onchange={(event) => saveSubjectColor(event.currentTarget.value)} />
                   </label>
                   <button type="button" class="secondary-button display-reset" onclick={clearSubjectColors}>과목 색상 초기화</button>
                 {/if}
                 <label class="display-toggle"><input type="checkbox" checked={displaySettings.showTeachers} onchange={(event) => saveDisplaySettings({ ...displaySettings, showTeachers: event.currentTarget.checked })} /> 시간표에 교사 표시</label>
                 <label>종료된 수업 표시
                   <select value={displaySettings.endedLessonMode} onchange={(event) => saveDisplaySettings({ ...displaySettings, endedLessonMode: event.currentTarget.value as DisplaySettings['endedLessonMode'] })}>
                     <option value="dim">흐리게 표시</option><option value="hide">숨기기</option><option value="normal">그대로 표시</option>
                   </select>
                 </label>
                 <label class="display-toggle"><input type="checkbox" checked={displaySettings.dimOtherDays} onchange={(event) => saveDisplaySettings({ ...displaySettings, dimOtherDays: event.currentTarget.checked })} /> 이번 주 오늘 외 요일 흐리게 표시</label>
                 <label>교사 선택
                   <select bind:value={selectedTeacher} disabled={!teacherNames.length}>
                     <option value="">교사를 선택하세요</option>{#each teacherNames as teacher}<option value={teacher}>{teacher}</option>{/each}
                   </select>
                 </label>
                 <label>교사 표시 이름
                   <input type="text" value={displaySettings.teacherAliases[selectedTeacher] || ''} disabled={!selectedTeacher} maxlength="60" placeholder="원본 이름 유지" oninput={(event) => saveAlias('teacher', selectedTeacher, event.currentTarget.value)} />
                 </label>
                 <label>모든 교사 이름 앞에 추가
                   <input type="text" value={displaySettings.teacherPrefix} maxlength="30" placeholder="예: 선생님 " oninput={(event) => saveDisplaySettings({ ...displaySettings, teacherPrefix: event.currentTarget.value })} />
                 </label>
                 <label>모든 교사 이름 뒤에 추가
                   <input type="text" value={displaySettings.teacherSuffix} maxlength="30" placeholder="예: T" oninput={(event) => saveDisplaySettings({ ...displaySettings, teacherSuffix: event.currentTarget.value })} />
                 </label>
               </div>
               <p class="display-settings-hint">원본 시간표는 그대로 유지되며 이 학교의 표시 설정만 브라우저에 저장됩니다.</p>
             </details>
             <details class="lesson-time-settings">
               <summary>학교 교시 시각 설정</summary>
               <p class="display-settings-hint">학교에서 확인한 실제 시작·종료 시각을 입력해 주세요. 설정은 이 브라우저의 해당 학교에만 저장되며, 입력하지 않은 교시는 추측하지 않습니다.</p>
               <div class="lesson-time-grid">
                 {#each lessonTimePeriods as period}
                   <div class="lesson-time-row">
                     <strong>{period}교시</strong>
                     <label>시작 <input type="time" aria-label={`${period}교시 시작`} value={lessonTimeDrafts[period]?.start ?? ''} oninput={(event) => editLessonTime(period, 'start', event.currentTarget.value)} /></label>
                     <label>종료 <input type="time" aria-label={`${period}교시 종료`} value={lessonTimeDrafts[period]?.end ?? ''} oninput={(event) => editLessonTime(period, 'end', event.currentTarget.value)} /></label>
                   </div>
                 {/each}
               </div>
               <div class="lesson-time-actions"><button class="secondary-button" type="button" onclick={saveLessonTimes}>시각 저장</button><button class="secondary-button" type="button" onclick={clearLessonTimes}>시각 초기화</button></div>
               {#if lessonTimeState}<p class="state-inline" role="status">{lessonTimeState}</p>{/if}
             </details>
           {/if}
          {#if timetable}<section class="history-section" aria-labelledby="history-title"><div class="history-heading"><div><h3 id="history-title">시간표 변경 이력</h3><p>이번 주 학교 시간표의 수집 변경 사항</p></div><button class="secondary-button" aria-expanded={historyOpen} aria-controls="history-list" onclick={toggleHistory}>{historyOpen ? '이력 닫기' : '이력 보기'}</button></div>{#if historyOpen}<div id="history-list">{#if historyDisabled}<p class="state-inline">변경 이력 저장이 아직 활성화되지 않았어요.</p>{:else if historyLoading && !historyChanges.length}<p class="state-inline" role="status">변경 이력을 불러오는 중…</p>{:else if historyError}<div class="notice" role="alert">{historyError} <button class="text-button" onclick={() => loadHistory()}>다시 시도</button></div>{:else if historyChanges.length}<ol class="history-list">{#each historyChanges as change}<li><div><strong>{change.grade}학년 {change.class}반 · {dateText(change.date)} · {change.period}교시</strong><span>{timeText(change.observedAt)} 확인 · {changeTypeText(change.type)}</span></div><p><span>{change.before ? `${change.before.subject}${change.before.teacher ? ` · ${change.before.teacher}` : ''}` : '수업 없음'}</span><span aria-hidden="true"> → </span><span>{change.after ? `${change.after.subject}${change.after.teacher ? ` · ${change.after.teacher}` : ''}` : '수업 없음'}</span></p></li>{/each}</ol>{#if historyCursor}<button class="secondary-button history-more" disabled={historyLoading} onclick={() => loadHistory(true)}>{historyLoading ? '불러오는 중…' : '이전 변경 더 보기'}</button>{:else}<p class="state-inline">표시할 변경 이력을 모두 불러왔습니다.</p>{/if}{:else if !historyLoading}<p class="state-inline">이번 주에 기록된 변경 이력이 없습니다.</p>{/if}</div>{/if}</section>{/if}
        </section>
        <section id="meals-panel" hidden={view !== 'meals'} aria-labelledby="meals-title">
          <div class="section-heading"><div><p class="eyebrow">{mealDate === today ? '오늘의 식단' : '하루 식단'}</p><h2 id="meals-title">학교 급식</h2></div><button class="secondary-button" onclick={todayMeals}>오늘로</button></div>
          <div class="view-switch" role="group" aria-label="급식 보기"><button aria-pressed={mealView === 'day'} onclick={() => setMealView('day')}>하루 식단</button><button aria-pressed={mealView === 'week'} onclick={() => setMealView('week')}>주간 식단</button></div>
          <div class="calendar-toolbar"><button class="arrow-button" onclick={() => changeMealDate(mealView === 'week' ? -7 : -1)} aria-label={mealView === 'week' ? '이전 급식 주' : '이전 날짜'}>←</button><div class="calendar-date"><strong aria-live="polite">{mealView === 'week' ? dateText(mealDates[0]) + ' — ' + dateText(mealDates[6]) : dateText(mealDate, { month: 'long', day: 'numeric', weekday: 'long' })}</strong><label class="date-picker">날짜 선택 <input type="date" value={mealDate} onchange={selectMealDate} aria-invalid={!!dateError} /></label></div><button class="arrow-button" onclick={() => changeMealDate(mealView === 'week' ? 7 : 1)} aria-label={mealView === 'week' ? '다음 급식 주' : '다음 날짜'}>→</button></div>
          {#if dateError}<p class="notice" role="alert">{dateError}</p>{/if}
           <div class="meal-connection" aria-live="polite">{!neis && school ? neisSearchState : ''}</div>
          {#if !school}<div class="state-message"><strong>학교를 먼저 선택해 주세요</strong><p>시간표 학교를 선택하면 급식도 함께 연결돼요.</p></div>
          {:else if neisLoading}<div class="state-message" role="status">같은 학교의 급식을 연결하고 있어요.</div>
          {:else if !neis}
            <div class="connection-options">{#each neisResults as item (item.id)}<button class="school-option" onclick={() => chooseNeis(item)}><strong>{item.name}</strong><span>{item.address}</span></button>{/each}<button class="text-button" onclick={() => connectMeals()}>급식 연결 다시 시도</button></div>
           {:else}
             <details class="meal-preferences"><summary>급식 보기 설정</summary><div class="meal-preference-options" aria-label="표시할 식사"><span>표시할 식사</span>{#each mealTypes as type}<label><input type="checkbox" checked={enabledMealTypes.includes(type)} disabled={enabledMealTypes.length === 1 && enabledMealTypes.includes(type)} onchange={(event) => toggleMealType(type, event.currentTarget.checked)} />{type}</label>{/each}</div><label class="meal-number-toggle"><input type="checkbox" checked={showAllergenNumbers} onchange={(event) => setAllergenNumbersVisible(event.currentTarget.checked)} />메뉴의 알레르기 번호 표시</label><p>하루·주간 보기와 표시 설정은 이 브라우저에 저장돼요. 주의 알레르기 경고는 항상 표시됩니다.</p></details>
             <details class="allergy-settings"><summary>급식 알레르기 설정 {allergySelection.length ? `(${allergySelection.length}개 선택)` : ''}</summary><div class="allergy-grid">{#each allergens as name, index}<label><input type="checkbox" checked={allergySelection.includes(index + 1)} onchange={(event) => toggleAllergy(index + 1, event.currentTarget.checked)} /><span>{index + 1}. {name}</span></label>{/each}</div><p>선택 항목은 이 브라우저에만 저장돼요. NEIS에서 알레르기가 표시되지 않았더라도 안전하다는 뜻은 아니에요.</p></details>
            {#if mealState}<div class="notice" role="alert">{hasMeals ? '이전 급식 정보를 표시하고 있어요. ' : ''}{mealState} <button class="text-button" onclick={() => loadMeals(true)}>다시 시도</button></div>{/if}
            {#if mealLoading && !hasMeals}<div class="state-message" role="status">식단을 불러오고 있어요.</div>
            {:else if hasMeals}
               {#if mealView === 'day'}{#if !dayMeals.some((meal) => visibleMealTypes.includes(meal.type))}<p class="no-meal">이 날짜에 등록된 식단이 없어요.</p>{:else}<div class="meal-cards">{#each visibleMealTypes as type}<article class="meal-card" aria-label={dateText(mealDate) + ' ' + type}><div class="meal-card-heading"><h3>{type}</h3><span>{type === '조식' ? '아침' : type === '중식' ? '점심' : '저녁'}</span></div>{#if dayMeals.some((meal) => meal.type === type)}<ul class="dishes">{#each dayMeals.filter((meal) => meal.type === type) as meal}{#each meal.dishes as dish}{@const matches = allergenMatches(dish, allergySelection)}<li class:allergy-warning={matches.length > 0}>{#if matches.length}<strong class="allergy-label">⚠ 주의: {matches.map(({ id, name }) => `${id}. ${name}`).join(', ')}</strong>{/if}<span>{showAllergenNumbers ? dish : withoutAllergenNumbers(dish)}</span></li>{/each}{/each}</ul>{:else}<p class="no-meal">등록된 {type} 식단이 없어요.</p>{/if}</article>{/each}</div>{/if}
               {:else}<div class="weekly-meals">{#each mealDates as date}<article class:current-meal-day={date === today}><h3>{dateText(date, { month: 'numeric', day: 'numeric', weekday: 'long' })}{date === today ? ' · 오늘' : ''}</h3>{#if !meals.some((meal) => meal.date === date && visibleMealTypes.includes(meal.type))}<p class="no-meal">등록된 식단이 없어요.</p>{:else}<div class="weekly-meal-types">{#each visibleMealTypes as type}<section aria-label={dateText(date) + ' ' + type}><h4>{type}</h4>{#if meals.some((meal) => meal.date === date && meal.type === type)}<ul class="dishes">{#each meals.filter((meal) => meal.date === date && meal.type === type) as meal}{#each meal.dishes as dish}{@const matches = allergenMatches(dish, allergySelection)}<li class:allergy-warning={matches.length > 0}>{#if matches.length}<strong class="allergy-label">⚠ 주의: {matches.map(({ id, name }) => `${id}. ${name}`).join(', ')}</strong>{/if}<span>{showAllergenNumbers ? dish : withoutAllergenNumbers(dish)}</span></li>{/each}{/each}</ul>{:else}<p class="no-meal">등록된 식단이 없어요.</p>{/if}</section>{/each}</div>{/if}</article>{/each}</div>{/if}
            {/if}
            {#if mealsStale}<p class="notice">저장된 급식 정보예요. 최신 정보가 아닐 수 있습니다.</p>{/if}
          {/if}
        </section>
    </div>
    <section class="secondary-actions" aria-label="공유 및 즐겨찾기">
      {#if school}
        <div class="share-tools"><button class="secondary-button" disabled={classError} onclick={shareClass} aria-expanded={!!shareUrl}>{shareUrl ? '학급 링크 닫기' : '학급 링크 복사'}</button><button class="secondary-button" disabled={classError || apiNotConfigured} onclick={subscribeTimetable} aria-expanded={!!subscriptionUrl}>{subscriptionUrl ? '구독 링크 닫기' : '캘린더 구독 링크'}</button><span role="status">{shareState || subscriptionState}</span></div>
        {#if shareUrl}<label class="shared-link">공유 링크<input type="text" readonly value={shareUrl} onfocus={(event) => event.currentTarget.select()} /></label>{/if}
        {#if subscriptionUrl}<label class="shared-link">시간표 구독 URL (현재·다음 주, 교시별 종일 일정)<input type="text" readonly value={subscriptionUrl} onfocus={(event) => event.currentTarget.select()} /></label>{/if}
        <div class="favorite-save"><button class="secondary-button" disabled={classError || currentFavorite || favorites.length >= 10} onclick={addFavorite}>{currentFavorite ? '즐겨찾기 저장됨' : '현재 학급 즐겨찾기 추가'}</button><span>{favorites.length}/10개 저장됨</span></div>
      {/if}
      {#if favorites.length}
        <section class="favorites-bar" aria-labelledby="favorites-title">
          <div class="favorites-heading"><h2 id="favorites-title">즐겨찾는 학급</h2><span>선택하면 바로 전환됩니다</span></div>
          <div class="favorite-list">
            {#each favorites as favorite (`${favorite.school.id}-${favorite.grade}-${favorite.classroom}`)}
              <div class="favorite-item">
                <button class="favorite-switch" aria-pressed={school?.id === favorite.school.id && Number(grade) === favorite.grade && Number(classroom) === favorite.classroom} onclick={() => switchToFavorite(favorite)}>
                  <strong>{favorite.school.name}</strong><span>{favorite.grade}학년 {favorite.classroom}반</span>
                </button>
                <button class="favorite-remove" aria-label={`${favorite.school.name} ${favorite.grade}학년 ${favorite.classroom}반 즐겨찾기 삭제`} onclick={() => removeFavorite(favorite)}>×</button>
              </div>
            {/each}
          </div>
        </section>
      {/if}
    </section>
    <footer><div class="footer-open"><svg class="github-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 .75a11.25 11.25 0 0 0-3.56 21.92c.56.1.77-.24.77-.54v-2.1c-3.13.68-3.79-1.33-3.79-1.33-.51-1.3-1.25-1.64-1.25-1.64-1.02-.7.08-.69.08-.69 1.13.08 1.72 1.16 1.72 1.16 1 1.72 2.63 1.22 3.27.93.1-.72.39-1.22.7-1.5-2.5-.28-5.13-1.25-5.13-5.56 0-1.23.44-2.24 1.16-3.03-.12-.28-.5-1.43.11-2.98 0 0 .95-.3 3.1 1.16A10.8 10.8 0 0 1 12 6.17c.96 0 1.92.13 2.82.38 2.15-1.46 3.1-1.16 3.1-1.16.61 1.55.23 2.7.11 2.98.72.79 1.16 1.8 1.16 3.03 0 4.32-2.63 5.27-5.14 5.55.4.35.76 1.03.76 2.08v3.1c0 .3.2.65.78.54A11.25 11.25 0 0 0 12 .75Z"/></svg><div><strong>함께 만드는 오픈소스</strong><p>Opencigan은 오픈소스 프로젝트예요. GitHub에서 함께 기여해 주세요.</p><div class="footer-links"><a href="https://github.com/Transient-Onlooker/opensigan">Opencigan GitHub ↗</a><a href="https://github.com/hegelty/pycomcigan">pycomcigan ↗</a><a href="https://opencigan.mcv.kr/">Opencigan 사이트 ↗</a><a href="/api-docs.html">API 문서</a></div></div></div></footer>
  </main>
</div>
