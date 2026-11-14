import type { TimetableRecord } from './api';

export type ExportView = 'today' | 'week' | 'teacher';

export interface ExportOptions {
  view: ExportView;
  schoolName: string;
  grade: number;
  classroom: number;
  selectedDay: string;
  week: string;
  teacherName: string;
  records: TimetableRecord[];
  dark: boolean;
}

type ExportLesson = { title: string; detail: string };

function addDate(date: string, offset: number) {
  const value = new Date(date + 'T00:00:00Z');
  value.setUTCDate(value.getUTCDate() + offset);
  return value.toISOString().slice(0, 10);
}

function labelDate(date: string) {
  return new Intl.DateTimeFormat('ko-KR', { timeZone: 'UTC', month: 'numeric', day: 'numeric', weekday: 'short' }).format(new Date(date + 'T00:00:00Z'));
}

export function createExportGrid(options: ExportOptions) {
  const { view, records, grade, classroom, teacherName, schoolName, selectedDay, week } = options;
  const dates = view === 'today' ? [selectedDay] : Array.from({ length: 5 }, (_, index) => addDate(week, index));
  const selected = records.filter((lesson) => view === 'teacher'
    ? !!teacherName.trim() && lesson.teacher?.trim() === teacherName.trim() && dates.includes(lesson.date)
    : Number(lesson.grade) === Number(grade) && Number(lesson.class) === Number(classroom) && dates.includes(lesson.date));
  const periods = Array.from({ length: Math.max(0, ...selected.map((lesson) => Number(lesson.period)).filter((period) => Number.isInteger(period) && period > 0)) }, (_, index) => index + 1);
  const rows = periods.map((period) => dates.map((date): ExportLesson[] => selected
    .filter((lesson) => lesson.date === date && Number(lesson.period) === period)
    .map((lesson) => ({
      title: view === 'teacher' ? `${lesson.grade}학년 ${lesson.class}반` : lesson.subject || '수업 정보 없음',
      detail: view === 'teacher' ? lesson.subject || '과목 정보 없음' : lesson.teacher || '',
    }))));
  return {
    title: schoolName,
    subtitle: view === 'teacher' ? `${teacherName.trim()} 선생님 · ${labelDate(dates[0])} ~ ${labelDate(dates[dates.length - 1])}`
      : `${grade}학년 ${classroom}반 · ${view === 'today' ? labelDate(selectedDay) : `${labelDate(dates[0])} ~ ${labelDate(dates[dates.length - 1])}`}`,
    columns: dates.map(labelDate),
    periods,
    rows,
  };
}

function wrappedText(ctx: CanvasRenderingContext2D, value: string, maxWidth: number) {
  const lines: string[] = [];
  let line = '';
  for (const letter of Array.from(value)) {
    if (line && ctx.measureText(line + letter).width > maxWidth) {
      lines.push(line);
      line = letter;
    } else line += letter;
  }
  if (line) lines.push(line);
  return lines.length ? lines : [''];
}

export async function saveTimetablePng(options: ExportOptions) {
  const grid = createExportGrid(options);
  if (!grid.periods.length) throw new Error('저장할 수업 정보가 없어요.');
  await document.fonts?.ready;

  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  if (!context) throw new Error('이 브라우저에서는 이미지 저장을 지원하지 않아요.');
  const ctx = context;
  const padding = 44;
  const periodWidth = 92;
  const cellWidth = grid.columns.length === 1 ? 450 : 240;
  const width = 2 * padding + periodWidth + cellWidth * grid.columns.length;
  const contentWidth = width - 2 * padding;
  const colors = options.dark
    ? { bg: '#111111', text: '#f5f5f5', sub: '#bcbcbc', line: '#4b4b4b', heading: '#202020' }
    : { bg: '#ffffff', text: '#111111', sub: '#555555', line: '#d4d4d4', heading: '#f5f5f5' };
  const font = '"Pretendard Variable", system-ui, sans-serif';
  ctx.font = `700 32px ${font}`;
  const titleLines = wrappedText(ctx, grid.title, contentWidth);
  ctx.font = `400 17px ${font}`;
  const subtitleLines = wrappedText(ctx, grid.subtitle, contentWidth);
  const headingHeight = padding + titleLines.length * 43 + subtitleLines.length * 25 + 34;
  const rowHeights = grid.rows.map((cells) => {
    let maxHeight = 56;
    for (const lessons of cells) {
      let cellHeight = 20;
      for (const lesson of lessons) {
        ctx.font = `700 20px ${font}`;
        cellHeight += wrappedText(ctx, lesson.title, cellWidth - 24).length * 26;
        if (lesson.detail) {
          ctx.font = `400 16px ${font}`;
          cellHeight += wrappedText(ctx, lesson.detail, cellWidth - 24).length * 22;
        }
        cellHeight += 8;
      }
      maxHeight = Math.max(maxHeight, cellHeight + 12);
    }
    return maxHeight;
  });
  const height = headingHeight + 52 + rowHeights.reduce((sum, row) => sum + row, 0) + padding + 28;
  const scale = 2;
  canvas.width = width * scale;
  canvas.height = height * scale;
  ctx.scale(scale, scale);
  ctx.fillStyle = colors.bg;
  ctx.fillRect(0, 0, width, height);
  ctx.textBaseline = 'top';
  ctx.fillStyle = colors.text;
  ctx.font = `700 32px ${font}`;
  let titleY = padding;
  for (const line of titleLines) { ctx.fillText(line, padding, titleY); titleY += 43; }
  ctx.font = `400 17px ${font}`;
  ctx.fillStyle = colors.sub;
  for (const line of subtitleLines) { ctx.fillText(line, padding, titleY + 4); titleY += 25; }

  let y = headingHeight;
  ctx.fillStyle = colors.heading;
  ctx.fillRect(padding, y, contentWidth, 52);
  ctx.textAlign = 'center';
  ctx.fillStyle = colors.text;
  ctx.font = `700 17px ${font}`;
  ctx.fillText('교시', padding + periodWidth / 2, y + 15);
  grid.columns.forEach((column, index) => ctx.fillText(column, padding + periodWidth + cellWidth * (index + .5), y + 15));
  y += 52;
  const verticals = [padding, padding + periodWidth, ...grid.columns.map((_, index) => padding + periodWidth + cellWidth * (index + 1))];
  ctx.strokeStyle = colors.line;
  ctx.lineWidth = 1;
  for (let index = 0; index < grid.rows.length; index++) {
    const row = grid.rows[index];
    const rowHeight = rowHeights[index];
    ctx.beginPath(); ctx.moveTo(padding, y + .5); ctx.lineTo(padding + contentWidth, y + .5); ctx.stroke();
    ctx.textAlign = 'center'; ctx.font = `700 17px ${font}`; ctx.fillStyle = colors.text;
    ctx.fillText(String(grid.periods[index]), padding + periodWidth / 2, y + 18);
    for (let column = 0; column < row.length; column++) {
      const x = padding + periodWidth + column * cellWidth + 12;
      let textY = y + 14;
      ctx.textAlign = 'left';
      for (const lesson of row[column]) {
        ctx.font = `700 20px ${font}`; ctx.fillStyle = colors.text;
        for (const line of wrappedText(ctx, lesson.title, cellWidth - 24)) {
          ctx.fillText(line, x, textY); textY += 26;
        }
        if (lesson.detail) {
          ctx.font = `400 16px ${font}`; ctx.fillStyle = colors.sub;
          for (const line of wrappedText(ctx, lesson.detail, cellWidth - 24)) {
            ctx.fillText(line, x, textY); textY += 22;
          }
        }
        textY += 8;
      }
    }
    y += rowHeight;
  }
  ctx.beginPath(); ctx.moveTo(padding, y + .5); ctx.lineTo(padding + contentWidth, y + .5); ctx.stroke();
  for (const x of verticals) { ctx.beginPath(); ctx.moveTo(x + .5, headingHeight); ctx.lineTo(x + .5, y); ctx.stroke(); }
  ctx.textAlign = 'right'; ctx.font = `400 14px ${font}`; ctx.fillStyle = colors.sub;
  ctx.fillText('Opencigan · opencigan.mcv.kr', padding + contentWidth, y + 18);

  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((value) => value ? resolve(value) : reject(new Error('이미지 생성에 실패했어요.')), 'image/png');
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `Opencigan_${options.schoolName.replace(/[\\/:*?"<>|]/g, '')}_${options.view}_${options.selectedDay}.png`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
