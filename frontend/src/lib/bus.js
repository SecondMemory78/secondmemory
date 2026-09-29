// Оповещение экранов об изменении данных.
//
// Ассистент создаёт записи «сбоку» (из плавающей кнопки, с Главной, голосом),
// и открытый экран об этом не знал — приходилось обновлять страницу вручную.
// Здесь один общий сигнал: кто создал — сообщает, кто показывает — перечитывает.

const EVENT = "sm:data-changed";

/**
 * @param {string} scope — что изменилось: "patient" | "tasks" | "calendar" | "notes"
 * @param {object} detail — например { patient_id: 12 }
 */
export function dataChanged(scope, detail = {}) {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { scope, ...detail } }));
}

/** Подписка. Возвращает функцию отписки — удобно возвращать прямо из useEffect. */
export function onDataChanged(handler) {
  const fn = (e) => handler(e.detail || {});
  window.addEventListener(EVENT, fn);
  return () => window.removeEventListener(EVENT, fn);
}

/** Сигнал по результату команды ассистента — по тому, что он реально создал. */
export function notifyAssistantResult(res) {
  if (!res) return;
  if (res.patient_id) dataChanged("patient", { patient_id: res.patient_id });
  if (res.reminder_id) dataChanged("tasks");
  if (res.appointment_id) dataChanged("calendar");
}
