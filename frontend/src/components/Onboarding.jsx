import { useState } from "react";
import { api } from "../api";

// 7 экранов онбординга — тексты дословно из ТЗ §31 «Онбординг и короткая инструкция».
// Показывается один раз при первом входе; повторно доступен из «Помощи».
const SCREENS = [
  {
    title: "Что делает приложение",
    body: "Это ваша рабочая память: пациенты, документы, история и следующие действия. Вы можете писать, диктовать или фотографировать. Медицинские сведения из распознавания сначала проверяются.",
    hint: "Дальше вы попробуете всё на вымышленном пациенте — эти учебные данные не попадут в вашу рабочую базу.",
  },
  {
    title: "Кого вы ведёте",
    body: "Сначала найдите человека по ФИО и дате рождения. Если есть несколько вариантов, выберите по уточняющим данным. Новую карточку создавайте, когда нужного человека действительно нет.",
    hint: "Поиск сравнивает точно — тёзки не смешиваются.",
  },
  {
    title: "К какому обращению относится запись",
    body: "У пациента одна история, но приёмы и госпитализации — отдельные обращения. Укажите фактическое поступление; план выписки добавьте, когда он появится.",
    hint: "Одна карта — много эпизодов. Данные не путаются между приёмами.",
  },
  {
    title: "Как добавить сведения",
    body: "В карточке нажмите Фото, Голос или Текст. При общей диктовке называйте нового пациента перед его сведениями.",
    hint: "Статусы записи: «На устройстве» → «Загружено» → «На проверке» → «Подтверждено».",
  },
  {
    title: "Как проверить и исправить",
    body: "Нажмите на факт, чтобы увидеть источник. Исправляйте конкретное поле или скажите: «исправь дату поступления этого пациента». Проверьте, что меняется, и подтвердите.",
    hint: "Система только подсказывает несоответствия — решение всегда за вами.",
  },
  {
    title: "Как управлять делами",
    body: "Для напоминания назовите действие, пациента, дату и время. В разделе «Сегодня» видны сроки и вопросы. Вечером отметьте выполненное и назовите, что перенести.",
    hint: "Напоминания приходят по вашему местному времени, с учётом тихих часов.",
  },
  {
    title: "Что делать при ошибке",
    body: "Во «Входящих» выберите ответ, уточните или отложите. Незагруженная запись остаётся только на телефоне. Экстренная помощь — по обычному клиническому порядку.",
    hint: "Проверьте, что уведомления разрешены — иначе напоминания не придут.",
  },
];

const MEMO = [
  ["Добавить", "карточка → эпизод → Фото / Голос / Текст"],
  ["Найти", "поиск или «Покажи результаты этого пациента»"],
  ["Изменить", "факт → исправить → подтвердить"],
  ["Контролировать", "«Сегодня», списки и «Входящие»"],
  ["Вечером", "ответить на список и проверить итог изменений"],
];

export default function Onboarding({ onDone }) {
  const [step, setStep] = useState(0);       // 0..6 экраны, 7 — памятка
  const [busy, setBusy] = useState(false);
  const total = SCREENS.length;
  const onMemo = step >= total;

  async function start() {
    // «Начать на примере» — создаём учебного пациента (идемпотентно на бэке)
    setBusy(true);
    try { await api.sandboxStart(); } catch { /* не блокируем обучение из-за сети */ }
    setBusy(false);
    setStep(1);
  }

  async function finish() {
    setBusy(true);
    try { await api.sandboxFinish(true); } catch { /* прогресс всё равно закроем локально */ }
    setBusy(false);
    onDone?.();
  }

  async function skip() {
    setBusy(true);
    try { await api.sandboxFinish(false); } catch { /* игнор */ }
    setBusy(false);
    onDone?.();
  }

  const s = SCREENS[Math.min(step, total - 1)];

  return (
    <div className="ob-overlay" role="dialog" aria-modal="true" aria-label="Обучение">
      <div className="ob-card">
        <div className="ob-top">
          <span className="ob-count muted">
            {onMemo ? "Памятка" : `Шаг ${step + 1} из ${total}`}
          </span>
          {!onMemo && (
            <button className="ob-skip muted" onClick={skip} disabled={busy}>Пропустить</button>
          )}
        </div>

        {!onMemo ? (
          <>
            <h2 className="ob-title">{s.title}</h2>
            <p className="ob-body">{s.body}</p>
            {s.hint && <p className="ob-hint">{s.hint}</p>}
          </>
        ) : (
          <>
            <h2 className="ob-title">Памятка после обучения</h2>
            <div className="ob-memo">
              {MEMO.map(([k, v]) => (
                <div className="ob-memo-row" key={k}>
                  <b>{k}:</b> <span>{v}</span>
                </div>
              ))}
            </div>
            <p className="ob-hint">Всё это всегда под рукой в разделе «Помощь» — там же можно повторить обучение.</p>
          </>
        )}

        <div className="ob-dots">
          {SCREENS.map((_, i) => (
            <span key={i} className={"ob-dot" + (i === step ? " on" : "")} />
          ))}
          <span className={"ob-dot" + (onMemo ? " on" : "")} />
        </div>

        <div className="ob-nav">
          {step === 0 && (
            <button className="btn pri block ob-cta" onClick={start} disabled={busy}>
              Начать на примере
            </button>
          )}
          {step > 0 && !onMemo && (
            <>
              <button className="btn" onClick={() => setStep(step - 1)} disabled={busy}>Назад</button>
              <button className="btn pri" onClick={() => setStep(step + 1)} disabled={busy}>Далее</button>
            </>
          )}
          {onMemo && (
            <>
              <button className="btn" onClick={() => setStep(total - 1)} disabled={busy}>Назад</button>
              <button className="btn pri" onClick={finish} disabled={busy}>Готово</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
