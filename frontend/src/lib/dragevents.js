// Обработчики перетаскивания: либо указатель, либо касания — но не оба сразу.
//
// Почему не оба. Браузер на телефоне шлёт и touch-, и pointer-события на одно
// движение. Если слушать оба, обработчики срабатывают дважды: один начинает
// жест, второй его тут же обнуляет. Так у нас и сломались касания, когда мы
// добавили поддержку указателя «на всякий случай».
//
// Поэтому выбираем один набор: касания там, где они есть (телефон, планшет),
// указатель там, где их нет (компьютер с мышью).

// На устройстве с касаниями слушаем ИМЕННО касания. События указателя при
// начале прокрутки браузер отменяет (pointercancel), и вертикальный жест
// «потянуть вниз» не доходит до конца — проверено: до обёртки доезжают
// pointerdown и pointermove, а pointerup не приходит вовсе.
// Указатель оставляем там, где касаний нет: мышь и стилус на компьютере.
const HAS_TOUCH = typeof window !== "undefined" &&
  ("ontouchstart" in window || navigator.maxTouchPoints > 0);

/** Координаты из события любого типа. */
export function point(e) {
  if (e.clientX != null) return { x: e.clientX, y: e.clientY };
  const t = e.touches?.[0] || e.changedTouches?.[0];
  return t ? { x: t.clientX, y: t.clientY } : null;
}

/** Набор обработчиков для элемента: {down, move, up, cancel}. */
export function dragHandlers({ down, move, up, cancel }) {
  if (HAS_TOUCH) {
    return {
      onTouchStart: down,
      onTouchMove: move,
      onTouchEnd: up,
      onTouchCancel: cancel || up,
    };
  }
  return {
    onPointerDown: down,
    onPointerMove: move,
    onPointerUp: up,
    onPointerCancel: cancel || up,
  };
}
