// Настоящая видимая высота экрана.
//
// Зачем это нужно. На телефоне (особенно в Safari на iPhone) при появлении
// клавиатуры страница НЕ уменьшается: браузер оставляет её прежней высоты и
// сдвигает вверх, пряча низ под клавиатурой. Приложение об этом не знает и
// продолжает считать, что экран целый — поэтому нижнее меню уезжает за край,
// поле ввода оказывается под клавиатурой, а всплывающие окна встают не там.
//
// Здесь мы спрашиваем у браузера реальную видимую область (visualViewport) и
// кладём её в переменные CSS:
//   --app-h  — высота, в которую должно вписаться приложение;
//   --kb     — сколько снизу занято клавиатурой (0, когда её нет).
//
// Всё остальное оформление опирается на эти две переменные, а не на «100% экрана».

const root = document.documentElement;

function apply() {
  const vv = window.visualViewport;
  const h = vv ? vv.height : window.innerHeight;

  // Клавиатура — это разница между полной высотой окна и видимой областью.
  // Сдвиг страницы (offsetTop) сюда НЕ входит: он показывает, насколько
  // браузер прокрутил страницу, чтобы показать поле, и к высоте клавиатуры
  // отношения не имеет. Вычитание offsetTop давало ноль именно в Safari,
  // где страница как раз и сдвигается.
  let kb = 0;
  if (vv) {
    kb = Math.max(0, window.innerHeight - vv.height);
    if (kb < 60) kb = 0;        // мелкие колебания панелей браузера клавиатурой не считаем
  }

  root.style.setProperty("--app-h", Math.round(h) + "px");
  root.style.setProperty("--kb", Math.round(kb) + "px");
  root.classList.toggle("kb-open", kb > 0);
}

let pending = false;
function schedule() {
  if (pending) return;
  pending = true;
  requestAnimationFrame(() => { pending = false; apply(); });
}

export function startViewportWatch() {
  apply();
  const vv = window.visualViewport;
  if (vv) {
    vv.addEventListener("resize", schedule);
    vv.addEventListener("scroll", schedule);
  }
  window.addEventListener("resize", schedule);
  window.addEventListener("orientationchange", () => setTimeout(apply, 250));

  // Safari прячет клавиатуру не сообщая об этом сразу — подстраховываемся
  // после снятия фокуса с поля.
  document.addEventListener("focusout", () => setTimeout(apply, 120), true);
}

/** Прокрутить активное поле в видимую часть, когда клавиатура уже открыта. */
export function keepFocusVisible() {
  document.addEventListener("focusin", (e) => {
    const el = e.target;
    if (!el || !el.matches?.("input, textarea, select, [contenteditable]")) return;
    // ждём, пока клавиатура доедет и пересчитается высота
    setTimeout(() => {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
    }, 300);
  });
}
