// Жест «листнуть» как готовый набор обработчиков.
//
// Разбор жеста живёт в lib/swipe.js и проверяется без браузера. Здесь только
// привязка к событиям, одинаковая для всех экранов: иначе каждый экран заведёт
// свой порог, и листание будет ощущаться по-разному.
//
// Какие события слушать, решает lib/dragevents: указатель, если браузер умеет,
// иначе касания. Слушать оба нельзя — обработчики срабатывают дважды и гасят
// друг друга.

import { useRef } from "react";
import { dragHandlers, point } from "./dragevents";
import { swipeDirection } from "./swipe";

export function useSwipe(onSwipe) {
  const from = useRef(null);

  function begin(x, y) { from.current = { x, y }; }

  function finish(x, y) {
    const f = from.current;
    from.current = null;
    if (!f) return;
    const dir = swipeDirection(f, { x, y });
    if (dir) onSwipe(dir);
  }

  return dragHandlers({
    down: (e) => { const p = point(e); if (p) begin(p.x, p.y); },
    up: (e) => { const p = point(e); if (p) finish(p.x, p.y); },
    // Палец ушёл за пределы — жест не состоялся. Иначе случайное касание края
    // экрана листало бы месяц.
    cancel: () => { from.current = null; },
  });
}
