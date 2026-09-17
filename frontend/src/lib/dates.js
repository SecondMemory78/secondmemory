// Единая утилита дат для календаря (T3). Реальные даты вместо захардкоженного марта 2026.

export const pad = (n) => String(n).padStart(2, "0");
export const iso = (y, m, d) => `${y}-${pad(m)}-${pad(d)}`;

export const WD = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
export const MONTHS_NOM = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
export const MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня",
  "июля", "августа", "сентября", "октября", "ноября", "декабря"];

export function todayISO() {
  const t = new Date();
  return iso(t.getFullYear(), t.getMonth() + 1, t.getDate());
}

export function monthRange(y, m) {
  const last = new Date(y, m, 0).getDate();
  return [iso(y, m, 1), iso(y, m, last)];
}

export function monthLabel(y, m) {
  return `${MONTHS_NOM[m - 1]} ${y}`;
}

// Матрица недель месяца; каждая ячейка — {day, cur (в этом месяце), iso}
export function monthMatrix(y, m) {
  const firstWeekday = (new Date(y, m - 1, 1).getDay() + 6) % 7; // Пн=0
  const start = new Date(y, m - 1, 1);
  start.setDate(1 - firstWeekday);
  const weeks = [];
  for (let w = 0; w < 6; w++) {
    const row = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + w * 7 + i);
      row.push({ day: d.getDate(), cur: d.getMonth() === m - 1, iso: iso(d.getFullYear(), d.getMonth() + 1, d.getDate()) });
    }
    weeks.push(row);
  }
  return weeks.filter((row) => row.some((c) => c.cur));
}

// Понедельник недели, содержащей today + offset недель
export function weekStart(offset = 0) {
  const t = new Date(); t.setHours(0, 0, 0, 0);
  t.setDate(t.getDate() - ((t.getDay() + 6) % 7) + offset * 7);
  return t;
}

export function weekDays(offset = 0) {
  const s = weekStart(offset);
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(s); d.setDate(s.getDate() + i);
    return { day: d.getDate(), month: d.getMonth() + 1, year: d.getFullYear(), iso: iso(d.getFullYear(), d.getMonth() + 1, d.getDate()) };
  });
}

// Смещение недели (в неделях) от текущей до недели с датой isoStr
export function weekOffsetOfISO(isoStr) {
  const [y, m, d] = isoStr.split("-").map(Number);
  const a = new Date(y, m - 1, d); a.setHours(0, 0, 0, 0);
  a.setDate(a.getDate() - ((a.getDay() + 6) % 7));
  const b = weekStart(0);
  return Math.round((a - b) / (7 * 86400000));
}

export function fmtDay(isoStr) {
  const [y, m, d] = isoStr.split("-").map(Number);
  return `${d} ${MONTHS_GEN[m - 1]}`;
}
