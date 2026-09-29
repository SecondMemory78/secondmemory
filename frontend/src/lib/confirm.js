// Единый диалог подтверждения. Возвращает Promise<boolean>.
// Использование: if (!(await confirmAction({ title: "Удалить?", danger: true }))) return;
export function confirmAction(opts = {}) {
  return new Promise((resolve) => {
    window.dispatchEvent(new CustomEvent("sm:confirm", { detail: { ...opts, resolve } }));
  });
}
