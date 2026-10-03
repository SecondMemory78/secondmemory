import { useRef, useState } from "react";
import { dragHandlers, point } from "../lib/dragevents";
import { pullOffset, pullProgress, pullTriggered } from "../lib/pulltorefresh";

// Обёртка «потянуть вниз, чтобы обновить».
//
// Жест работает только когда список прокручен в самый верх — иначе врач,
// листая вверх по длинному списку пациентов, вызывал бы обновление каждый раз.
// Сам разбор вынесен в lib/pulltorefresh и проверяется без браузера.

export default function PullToRefresh({ onRefresh, children }) {
  const [dy, setDy] = useState(0);
  const [busy, setBusy] = useState(false);
  const from = useRef(null);
  const box = useRef(null);

  function atTop() {
    // Ищем ближайший прокручиваемый контейнер: в приложении это .scroll
    const sc = box.current?.closest(".scroll");
    return !sc || sc.scrollTop <= 0;
  }

  function start(e) {
    if (busy || !atTop()) { from.current = null; return; }
    from.current = point(e)?.y ?? null;
  }

  function move(e) {
    if (from.current == null) return;
    const y = point(e)?.y ?? 0;
    const delta = y - from.current;
    if (delta <= 0) { setDy(0); return; }
    setDy(delta);
  }

  async function end() {
    const delta = dy;
    from.current = null;
    setDy(0);
    if (!pullTriggered(delta) || busy) return;
    setBusy(true);
    try { await onRefresh?.(); } finally { setBusy(false); }
  }

  const progress = pullProgress(dy);
  const offset = busy ? 34 : pullOffset(dy);

  return (
    <div ref={box} {...dragHandlers({ down: start, move, up: end })}>
      {/* Подсказка появляется по мере оттягивания: человек должен понимать,
          что жест засчитан, ещё до того как отпустит палец. */}
      {/* Стрелка поворачивается по мере оттягивания и превращается в
          крутящийся значок: человек видит, что жест засчитан, ещё до того как
          отпустит палец. Текст оставляем — значок без подписи угадывать. */}
      <div className="ptr-hint" style={{ height: offset, opacity: busy ? 1 : progress }}>
        <i className={"ti " + (busy ? "ti-loader-2 ptr-spin" : "ti-arrow-down")}
           style={{ transform: busy ? "none" : `rotate(${progress * 180}deg)`,
                    transition: "transform .12s ease" }} />
        <span>{busy ? "Обновляю…" : progress >= 1 ? "Отпустите" : "Потяните"}</span>
      </div>
      <div style={{ transform: `translateY(${busy ? 0 : 0}px)` }}>{children}</div>
    </div>
  );
}
