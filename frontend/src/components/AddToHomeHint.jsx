import { useState } from "react";
import { isStandalone, detectPlatform } from "../lib/push";

// Подсказка «добавьте на экран Домой».
//
// На iPhone уведомления работают ТОЛЬКО если приложение добавлено на домашний
// экран — в обычной вкладке Safari их не будет. Это ограничение Apple.
// Раньше объяснение существовало, но показывалось лишь тому, кто сам дошёл до
// «Ещё → Уведомления» и нажал «Разрешить». Врач, который просто работает, не
// увидел бы его никогда — и не получил бы ни одного напоминания.
//
// Поэтому подсказываем сами, но не в лоб при первом входе (там уже обучение),
// а в момент, когда напоминание действительно понадобилось: врач создал задачу
// или напоминание. Тогда совет отвечает на возникший вопрос.

const KEY = "sm_a2hs_hidden";

export function shouldShowAddToHome() {
  if (localStorage.getItem(KEY)) return false;
  return detectPlatform() === "ios" && !isStandalone();
}

export default function AddToHomeHint({ onClose }) {
  const [open, setOpen] = useState(false);

  function hide() {
    localStorage.setItem(KEY, "1");
    onClose?.();
  }

  return (
    <div className="banner b-ac a2hs" style={{ display: "block", cursor: "default" }}>
      <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
        <i className="ti ti-device-mobile-share" style={{ marginTop: 1 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <b>Чтобы напоминания приходили, добавьте приложение на экран «Домой»</b>
          <div className="sub" style={{ marginTop: 4 }}>
            В обычной вкладке Safari уведомления не работают — так устроен iPhone.
          </div>
          {open && (
            <div className="sub" style={{ marginTop: 8, lineHeight: 1.7 }}>
              1. Нажмите «Поделиться» внизу Safari — квадрат со стрелкой вверх.<br />
              2. Выберите «На экран „Домой“».<br />
              3. Откройте приложение с новой иконки.
            </div>
          )}
          <div className="btnrow" style={{ marginTop: 10 }}>
            <button className="btn sm" onClick={() => setOpen((v) => !v)}>
              {open ? "Свернуть" : "Как это сделать"}
            </button>
            <button className="btn sm ghost" onClick={hide}>Не сейчас</button>
          </div>
        </div>
      </div>
    </div>
  );
}
