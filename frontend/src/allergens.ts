export const allergens = [
  '난류', '우유', '메밀', '땅콩', '대두', '밀', '고등어', '게', '새우',
  '돼지고기', '복숭아', '토마토', '아황산류', '호두', '닭고기',
  '쇠고기', '오징어', '조개류', '잣',
] as const;

export function allergenMatches(dish: string, selected: readonly number[]) {
  const marked = new Set<number>();
  // NEIS denotes allergens inside parentheses as dot-separated integer IDs.
  for (const marker of dish.matchAll(/\(([0-9.,\s]+)\)/g)) {
    for (const token of marker[1].split(/[.,\s]+/)) {
      if (!/^(?:[1-9]|1[0-9])$/.test(token)) continue;
      marked.add(Number(token));
    }
  }
  return [...new Set(selected)]
    .filter((id) => Number.isInteger(id) && id >= 1 && id <= 19 && marked.has(id))
    .sort((a, b) => a - b)
    .map((id) => ({ id, name: allergens[id - 1] }));
}

export function withoutAllergenNumbers(dish: string) {
  return dish.replace(/\s*\(([0-9.,\s]+)\)/g, (marker, contents: string) => {
    const codes = contents.split(/[.,\s]+/).filter(Boolean);
    return codes.length && codes.every((code) => /^(?:[1-9]|1[0-9])$/.test(code)) ? '' : marker;
  }).trim();
}
