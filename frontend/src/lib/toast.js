// Лёгкие всплывающие уведомления (тосты). Поддерживают опциональную кнопку действия
// (напр. «Отменить»): toast("Готово", "success", { label: "Отменить", onAction: fn }).
export function toast(msg, type = "info", opts = {}) {
  window.dispatchEvent(new CustomEvent("sm:toast", {
    detail: { msg, type, id: Date.now() + Math.random(), label: opts.label, onAction: opts.onAction },
  }));
}
