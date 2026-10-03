// Проверка жеста «потянуть вниз» без браузера.
//
// Сам жест руками проверять дорого, а ошибка тихая: либо обновление
// срабатывает от случайного касания, либо не срабатывает вовсе.

import { PULL_TRIGGER, PULL_MAX, pullProgress, pullTriggered, pullOffset }
  from "../src/lib/pulltorefresh.js";

let bad = 0;
const check = (name, got, want) => {
  if (got !== want) { bad++; console.log("ПРОВАЛ:", name, "→", got, "ожидалось", want); }
};

check("случайное касание не считается жестом", pullTriggered(10), false);
check("половина пути ещё не жест", pullTriggered(PULL_TRIGGER / 2), false);
check("полный путь — жест", pullTriggered(PULL_TRIGGER), true);
check("движение вверх игнорируется", pullTriggered(-50), false);

check("подсказка не показывается без движения", pullProgress(0), 0);
check("подсказка на половине", pullProgress(PULL_TRIGGER / 2), 0.5);
check("подсказка не превышает единицы", pullProgress(PULL_TRIGGER * 3), 1);

check("смещение не уходит в минус", pullOffset(-20), 0);
check("смещение имеет предел", pullOffset(10000), PULL_MAX);
if (!(pullOffset(100) < 100)) { bad++; console.log("ПРОВАЛ: содержимое тянется без сопротивления"); }

console.log(bad === 0 ? "Всё верно." : `Ошибок: ${bad}`);
process.exit(bad === 0 ? 0 : 1);
