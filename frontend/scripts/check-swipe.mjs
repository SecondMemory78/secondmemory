// Проверка распознавания жеста «листнуть» — без браузера.
//   node scripts/check-swipe.mjs
const { swipeDirection } = await import("../src/lib/swipe.js");

let bad = 0;
const check = (name, got, want) => {
  const ok = got === want;
  if (!ok) bad++;
  console.log(`${ok ? "OK  " : "ПЛОХО"} ${name}${ok ? "" : ` — ожидали ${want}, получили ${got}`}`);
};
const sw = (dx, dy = 0) => swipeDirection({ x: 200, y: 300 }, { x: 200 + dx, y: 300 + dy });

check("палец влево — вперёд",            sw(-120), 1);
check("палец вправо — назад",            sw(120), -1);
check("ровно на границе — не жест",      sw(-47), 0);
check("чуть за границей — жест",         sw(-49), 1);
check("дрожь пальца при нажатии",        sw(-6, 3), 0);
check("прокрутка текста вниз",           sw(-60, -200), 0);
check("прокрутка вверх",                 sw(50, 300), 0);
check("по диагонали, но горизонталь сильнее", sw(-150, 60), 1);
check("нет точки начала",                swipeDirection(null, { x: 0, y: 0 }), 0);
check("нет точки конца",                 swipeDirection({ x: 0, y: 0 }, null), 0);

console.log(bad ? `\nОШИБОК: ${bad}` : "\nВсё верно.");
process.exit(bad ? 1 : 0);
