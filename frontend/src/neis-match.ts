import type { NeisSchool, School } from './api';

const regions = [
  ['B10', '서울', '서울특별시'], ['C10', '부산', '부산광역시'],
  ['D10', '대구', '대구광역시'], ['E10', '인천', '인천광역시'],
  ['F10', '광주', '광주광역시'], ['G10', '대전', '대전광역시'],
  ['H10', '울산', '울산광역시'], ['I10', '세종', '세종특별자치시'],
  ['J10', '경기', '경기도'], ['K10', '강원', '강원도', '강원특별자치도'],
  ['M10', '충북', '충청북도'], ['N10', '충남', '충청남도'],
  ['P10', '전북', '전라북도', '전북특별자치도'], ['Q10', '전남', '전라남도'],
  ['R10', '경북', '경상북도'], ['S10', '경남', '경상남도'],
  ['T10', '제주', '제주도', '제주특별자치도'],
];

const compact = (value: string) => value.normalize('NFKC').replace(/\s+/g, '');

export function mealSchoolCandidates(school: School, candidates: NeisSchool[]): NeisSchool[] {
  const office = regions.find(([, ...aliases]) => aliases.includes(compact(school.region)))?.[0];
  return candidates.filter((candidate) =>
    compact(candidate.name) === compact(school.name)
    && (!office || candidate.id.split(':')[0] === office),
  );
}

export function resolveMealSchool(school: School, candidates: NeisSchool[]): NeisSchool | null {
  const matches = mealSchoolCandidates(school, candidates);
  return matches.length === 1 ? matches[0] : null;
}
