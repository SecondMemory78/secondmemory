import { useNavigate } from "react-router-dom";
import { useState } from "react";
import Onboarding from "../components/Onboarding";

const SECTIONS = [
  ["ti-shield-check", "Согласие 152-ФЗ", "Перед приёмом нового пациента оформите согласие на обработку персональных данных — без него приём вести нельзя. Три способа: бумажный бланк (распечатать, подписать, сфотографировать — ИИ проверит и сохранит только текст, не фото), электронно на устройстве, удалённо по QR/SMS. Статус виден в карте пациента (Сводка → «Согласие 152-ФЗ»)."],
  ["ti-user-plus", "Новый пациент и приём", "Вкладка «Пациенты» → «+», заполните форму. Или «Новый приём» на главной: можно начать приём сразу или запланировать. Всё, что вносите при открытом визите (заметки, показатели, назначения, документы), привязывается к этому визиту — см. вкладку «Визиты»."],
  ["ti-pill", "Назначения и аллергии", "В карте пациента → «Назначить»: укажите препарат и дозу. Если есть конфликт с аллергией, система покажет предупреждение с правилом перекрёстной реактивности и фенотипом — но не запретит: решение за вами, причина сохранится в журнале."],
  ["ti-activity", "Показатели и документы", "«Документ» — сфотографируйте бланк, система распознает значения; они попадают в карту как «ожидают подтверждения», пока вы их не подтвердите. Динамика показателей — во вкладке «Сводка»."],
  ["ti-bell", "Задачи и автослежение", "Вкладка «Задачи» — напоминания и контроли (можно голосом и в свободной форме: «контроль PSA через 3 месяца»). «Ещё → Автослежение» — триггеры: условие вроде «PSA > 4» само заводит контроль подходящим пациентам."],
  ["ti-lock", "Вход и безопасность", "На новом устройстве вход подтверждается кодом с почты. «Запомнить устройство» — не выходить при перезапуске. В «Ещё → Безопасность входа» можно задать PIN или биометрию для быстрой разблокировки."],
];

export default function Help() {
  const nav = useNavigate();
  const [replay, setReplay] = useState(false);
  return (
    <>
      {replay && <Onboarding onDone={() => setReplay(false)} />}
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav("/more")} />
        <div className="ttl">Помощь</div>
      </div>
      <div className="sub" style={{ marginBottom: 12 }}>Короткие ответы по основным функциям.</div>
      <div className="card" style={{ marginBottom: 10, display: "flex", gap: 10, alignItems: "center", cursor: "pointer" }}
           onClick={() => setReplay(true)}>
        <i className="ti ti-school acc" style={{ fontSize: 18 }} />
        <div>
          <div style={{ fontSize: 14, fontWeight: 500 }}>Пройти обучение заново</div>
          <div style={{ fontSize: 12.5, color: "var(--ts)" }}>5–7 минут на вымышленном пациенте</div>
        </div>
      </div>
      {SECTIONS.map(([ic, t, body]) => (
        <div key={t} className="card" style={{ marginBottom: 10 }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6 }}>
            <i className={"ti " + ic + " acc"} style={{ fontSize: 18 }} />
            <div style={{ fontSize: 14, fontWeight: 500 }}>{t}</div>
          </div>
          <div style={{ fontSize: 13, lineHeight: 1.6, color: "var(--ts)" }}>{body}</div>
        </div>
      ))}
      <div className="card" style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 13, lineHeight: 1.6 }}>Не нашли ответ? Напишите нам: <span className="acc" style={{ cursor: "pointer" }} onClick={() => nav("/support")}>поддержка</span>.</div>
      </div>
    </>
  );
}
