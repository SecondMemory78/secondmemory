import { useRef, useState } from "react";
import { dragHandlers, point } from "../lib/dragevents";
import { resolveAction, rowOffset } from "../lib/swipeaction";

// Строка списка, которую можно смахнуть.
//
// Жест вспомогательный: всё, что он делает, доступно и обычным нажатием.
// Поэтому ошибиться им не страшно — но удалить случайно всё равно нельзя,
// для разрушительного действия путь длиннее (см. lib/swipeaction).

export default function SwipeRow({ onRight, onLeft,
                                   leftLabel = "Выполнено", leftIcon = "ti-check",
                                   rightLabel = "Удалить", rightIcon = "ti-trash",
                                   children }) {
  const [dx, setDx] = useState(0);
  // Сработавшая строка доезжает до края: объявляем здесь, рядом с остальным
  // состоянием. Объявление ниже по файлу роняет экран — обращение к
  // переменной до инициализации.
  const [fired, setFired] = useState(false);
  const from = useRef(null);
  const moved = useRef(false);

  const pt = point;

  function start(e) {
    const t = pt(e);
    from.current = t ? { x: t.clientX ?? t.x, y: t.clientY ?? t.y } : null;
    moved.current = false;
  }

  function move(e) {
    const t = pt(e);
    if (!from.current || !t) return;
    const ddx = (t.clientX ?? t.x) - from.current.x;
    const ddy = (t.clientY ?? t.y) - from.current.y;
    // Вертикаль побеждает: человек листает список, а не смахивает строку
    if (Math.abs(ddy) > Math.abs(ddx)) { setDx(0); return; }
    moved.current = true;
    setDx(ddx);
  }

  function end(e) {
    const t = pt(e);
    const f = from.current;
    from.current = null;
    if (!f || !t || !moved.current) { setDx(0); return; }

    const tx = t.clientX ?? t.x, ty = t.clientY ?? t.y;
    const what = resolveAction(tx - f.x, ty - f.y);
    const handler = what === "right" ? onRight : what === "left" ? onLeft : null;
    if (!handler) { setDx(0); return; }   // не дотянул — строка плавно вернётся

    // Сработало: строка доезжает до края и только потом вызывается действие.
    // Если убрать её мгновенно, жест выглядит как сбой, а не как результат.
    setFired(true);
    setDx(what === "left" ? -320 : 320);
    setTimeout(() => { handler(); setFired(false); setDx(0); }, 160);
  }

  // Пока палец на экране — тянем с сопротивлением; после срабатывания даём
  // строке уехать целиком.
  const offset = fired ? dx : rowOffset(dx);

  return (
    <div className="swipe-row" {...dragHandlers({ down: start, move, up: end })}>
      {/* Подложка с действием видна ровно настолько, насколько уехала строка */}
      {/* Подложка зависит от направления: вправо — зелёное «выполнено»,
          влево — красное «удалить». Человек видит, что будет, до того как
          отпустит палец. */}
      {/* Красным помечаем разрушительную сторону — сейчас это вправо. Цвет
          идёт за смыслом, а не за направлением. */}
      {offset !== 0 && (
        <div className={"swipe-row-action" + (offset > 0 ? " dng" : "")}
             style={{ [offset < 0 ? "right" : "left"]: 0, width: Math.abs(offset) }}>
          <i className={"ti " + (offset < 0 ? leftIcon : rightIcon)} />
          {Math.abs(offset) > 72 && <span>{offset < 0 ? leftLabel : rightLabel}</span>}
        </div>
      )}
      <div className="swipe-row-body" style={{ transform: `translateX(${offset}px)` }}>
        {children}
      </div>
    </div>
  );
}
