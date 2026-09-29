// Лёгкие всплывающие уведомления (тосты). Поддерживают опциональную кнопку действия
// (напр. «Отменить»): toast("Готово", "success", { label: "Отменить", onAction: fn }).
// Одно и то же сообщение не показываем повторно: страница делает несколько
// запросов сразу, и при обрыве связи врач видел три одинаковых плашки подряд.
const _recent = new Map();
const DEDUPE_MS = 4000;

export function toast(msg, type = "info", opts = {}) {
  const now = Date.now();
  for (const [key, at] of _recent) if (now - at > DEDUPE_MS) _recent.delete(key);
  const key = `${type}:${msg}`;
  if (!opts.force && _recent.has(key)) return;      // дубль в пределах окна
  _recent.set(key, now);

  window.dispatchEvent(new CustomEvent("sm:toast", {
    detail: { msg, type, id: now + Math.random(), label: opts.label, onAction: opts.onAction },
  }));
}
