// Русские окончания по числу: 1 приём, 2 приёма, 5 приёмов.
// Без этого в интерфейсе появляется «1 приёмов» — мелочь, но выдаёт машину.
export function plural(n, one, few, many) {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  if (b === 1) return one;
  return many;
}
