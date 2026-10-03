// Проверка смахивания строк без браузера.
//
// Ошибка здесь дорогая: случайным движением можно удалить заметку. Поэтому
// проверяем именно пороги, а не вид.

import { ACTION_MIN, DESTRUCTIVE_MIN, isSwipe, resolveAction, rowOffset }
  from "../src/lib/swipeaction.js";

let bad = 0;
const check = (name, got, want) => {
  if (got !== want) { bad++; console.log("ПРОВАЛ:", name, "→", JSON.stringify(got)); }
};

check("дрожь пальца — не жест", isSwipe(8, 2), false);
check("прокрутка вниз — не жест", isSwipe(40, 60), false);
check("чистое движение вбок — жест", isSwipe(60, 10), true);

check("короткое смахивание ничего не делает", resolveAction(40, 5), "");
check("влево — выполнить", resolveAction(-ACTION_MIN, 5), "left");
check("вправо на том же пути НЕ удаляет", resolveAction(ACTION_MIN, 5), "");
check("вправо длинным движением — удалить", resolveAction(DESTRUCTIVE_MIN, 5), "right");
check("вертикальное движение ничего не делает", resolveAction(DESTRUCTIVE_MIN, 200), "");
check("удаление требует длиннее, чем выполнение", DESTRUCTIVE_MIN > ACTION_MIN, true);

check("строка не уезжает без движения", rowOffset(0), 0);
if (!(Math.abs(rowOffset(100)) < 100)) { bad++; console.log("ПРОВАЛ: строка едет без сопротивления"); }
if (Math.abs(rowOffset(10000)) > 141) { bad++; console.log("ПРОВАЛ: строка уезжает без предела"); }
check("направление сохраняется", rowOffset(-50) < 0, true);

console.log(bad === 0 ? "Всё верно." : `Ошибок: ${bad}`);
process.exit(bad === 0 ? 0 : 1);
