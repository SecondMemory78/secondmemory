// Поиск фразы-основания в тексте документа.
//
// Зачем отдельным модулем: подсветку в браузере проверить нечем — демо-
// распознаватель отдаёт бланк без повествовательных находок. А логика тут
// неочевидная и легко ломается, поэтому она вынесена и проверяется
// scripts/check-docmatch.mjs.
//
// Сравниваем по «скелету» — только буквы и цифры. Распознавание по-разному
// расставляет пробелы, переносы и скобки, и точное совпадение почти никогда
// не срабатывает: «кист размерами до 40х32мм» в тексте может оказаться
// «кист\nразмерами до 40х32 мм».

export function skeleton(x) {
  return String(x || "").toLowerCase().replace(/[^0-9a-zа-яё]+/gi, "");
}

/** Границы фразы в исходном тексте: {from, to} или null, если не нашлась. */
export function findSpan(fullText, phrase) {
  const full = String(fullText || "");
  const needle = String(phrase || "").trim();
  if (!needle) return null;

  const sk = skeleton(full);
  const need = skeleton(needle);
  if (!need) return null;

  const at = sk.indexOf(need);
  if (at < 0) return null;

  // Позиции значимых символов исходника — по ним возвращаемся из «скелета»
  const map = [];
  for (let i = 0; i < full.length; i++) {
    if (/[0-9a-zа-яё]/i.test(full[i])) map.push(i);
  }
  const from = map[at];
  const to = map[Math.min(at + need.length - 1, map.length - 1)] + 1;
  if (from == null || to == null || to <= from) return null;
  return { from, to };
}
