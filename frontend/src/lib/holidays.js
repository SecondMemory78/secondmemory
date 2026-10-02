// Производственный календарь: что приложение знает про даты.
//
// Субботы и воскресенья считаем сами — их не нужно никуда вносить.
// Праздники и переносы вычислить нельзя: в России их каждый год утверждает
// постановление правительства. Поэтому они приходят с сервера, а если года
// там нет — мы показываем ТОЛЬКО выходные и не делаем вид, что знаем про
// праздники. Ошибиться молча хуже, чем не знать.

import { api } from "../api";

const cache = new Map();          // год → {known, map}

export async function loadYear(year) {
  if (cache.has(year)) return cache.get(year);
  let data = { known: false, map: new Map() };
  try {
    const r = await api.workCalendar(year);
    data = {
      known: !!r.known,
      map: new Map((r.days || []).map((d) => [d.day, d])),
    };
  } catch {
    // Сервер недоступен — работаем по выходным, это честнее пустого календаря
  }
  cache.set(year, data);
  return data;
}

/** Выходной ли день: суббота/воскресенье или праздник.
 *  Перенос («working») делает субботу рабочей — тогда НЕ выходной. */
export function dayKind(isoStr, yearData) {
  const d = new Date(isoStr);
  const wd = (d.getDay() + 6) % 7;            // 0 — понедельник
  const rec = yearData?.map?.get(isoStr);

  if (rec?.kind === "working") return { off: false, label: rec.label, work: true };
  if (rec?.kind === "holiday") return { off: true, holiday: true, label: rec.label };
  if (rec?.kind === "short") return { off: false, short: true, label: rec.label };
  return { off: wd >= 5, weekend: wd >= 5 };
}
