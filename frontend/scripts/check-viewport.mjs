// Проверка расчёта видимой высоты и клавиатуры — без браузера и без библиотек.
//
//   node scripts/check-viewport.mjs
//
// Зачем отдельный скрипт: на телефоне это поведение руками проверяется только
// «открыл клавиатуру — посмотрел», а сломать его можно одной строкой. Здесь
// подставляем фальшивый браузер и проверяем четыре случая, включая тот, на
// котором расчёт уже один раз ошибался (Safari сдвигает страницу вместо
// уменьшения — вычитать этот сдвиг нельзя).

const style = new Map();
const classes = new Set();

const root = {
  style: {
    setProperty: (k, v) => style.set(k, v),
    getPropertyValue: (k) => style.get(k) ?? "",
  },
  classList: { toggle: (c, on) => (on ? classes.add(c) : classes.delete(c)) },
};

const listeners = {};
globalThis.document = {
  documentElement: root,
  addEventListener: () => {},
};
globalThis.window = {
  innerHeight: 844,
  visualViewport: {
    height: 844,
    offsetTop: 0,
    addEventListener: (t, f) => (listeners[t] = f),
  },
  addEventListener: () => {},
};
globalThis.requestAnimationFrame = (f) => { f(); return 1; };

const { startViewportWatch } = await import("../src/lib/viewport.js");
startViewportWatch();

function set({ height, offsetTop = 0 }) {
  Object.assign(window.visualViewport, { height, offsetTop });
  listeners.resize?.();
  return {
    h: style.get("--app-h"),
    kb: style.get("--kb"),
    open: classes.has("kb-open"),
  };
}

let failed = 0;
function check(name, got, want) {
  const ok = got.h === want.h && got.kb === want.kb && got.open === want.open;
  if (!ok) failed++;
  console.log(`${ok ? "OK  " : "ПЛОХО"} ${name}`,
              ok ? "" : `— ожидали ${JSON.stringify(want)}, получили ${JSON.stringify(got)}`);
}

check("без клавиатуры",
      set({ height: 844 }), { h: "844px", kb: "0px", open: false });

check("клавиатура открыта",
      set({ height: 508 }), { h: "508px", kb: "336px", open: true });

check("панель браузера (50px) — не клавиатура",
      set({ height: 794 }), { h: "794px", kb: "0px", open: false });

check("Safari: страница сдвинута, а не уменьшена",
      set({ height: 508, offsetTop: 336 }), { h: "508px", kb: "336px", open: true });

check("клавиатура закрыта",
      set({ height: 844, offsetTop: 0 }), { h: "844px", kb: "0px", open: false });

console.log(failed ? `\nОШИБОК: ${failed}` : "\nВсё верно.");
process.exit(failed ? 1 : 0);
