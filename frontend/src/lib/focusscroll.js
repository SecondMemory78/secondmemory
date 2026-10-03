// Прокрутка к полю, на которое встал курсор.
//
// Зачем. На экранах, где поля лежат в потоке (карта пациента, протокол,
// назначения, выписка), врач нажимает на поле внизу экрана — и оно оказывается
// под клавиатурой. Браузер иногда прокручивает сам, иногда нет: в Safari это
// зависит от того, успел ли он пересчитать видимую область, и предсказать
// невозможно.
//
// Поэтому прокручиваем сами, но только когда поле ДЕЙСТВИТЕЛЬНО закрыто:
// лишняя прокрутка раздражает сильнее, чем её отсутствие.

const MARGIN = 12;          // запас под полем, чтобы оно не липло к клавиатуре

/** Закрыто ли поле видимой областью. Вынесено отдельно, чтобы проверять без
 *  браузера: клавиатуру в headless не вызвать, а ошибка тут тихая — врач
 *  нажимает на поле и не видит, куда печатает. */
export function isHiddenByKeyboard(rectBottom, visibleBottom, margin = MARGIN) {
  return rectBottom > visibleBottom - margin;
}

let armed = false;

export function enableFocusScroll() {
  if (armed) return;
  armed = true;

  document.addEventListener("focusin", (e) => {
    const el = e.target;
    if (!el || !el.matches || !el.matches("input, textarea, select")) return;
    // Поля внутри шторки и окон пропускаем: они прижаты к низу и уже учтены
    if (el.closest(".asst-ov, .modal-ov, .chat-compose")) return;

    // Ждём, пока браузер покажет клавиатуру и пересчитает видимую область.
    // Без задержки мы меряем старые размеры и прокручиваем не туда.
    setTimeout(() => {
      const vv = window.visualViewport;
      const visibleBottom = vv ? vv.height : window.innerHeight;
      const r = el.getBoundingClientRect();
      if (!isHiddenByKeyboard(r.bottom, visibleBottom)) return;   // видно — не дёргаем
      el.scrollIntoView({ block: "center", behavior: "smooth" });
    }, 220);
  });
}
