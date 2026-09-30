import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import Tip from "./Tip";
import { notifyAssistantResult } from "../lib/bus";

// Единая точка входа в ассистента — плавающая кнопка + нижняя панель.
// Тот же движок команд (route_command), что и на Главной. Доступна с любого экрана.
export default function AssistantFab() {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  // Переписка, а не разовый ответ: врач видит, что ассистент понял, и может
  // уточнить следующей фразой. Живёт, пока открыта шторка.
  const [log, setLog] = useState([]);          // [{mine, r}]
  const [rec, setRec] = useState(false);
  const mrRef = useRef(null);
  const chunksRef = useRef([]);

  function push(mine, r) { setLog((l) => [...l, { mine, r }]); }

  async function send() {
    if (!text.trim() || busy) return;
    const mine = text.trim();
    setText(""); setBusy(true);
    try {
      const r = await api.assistantCommand(mine);
      push(mine, r);
      notifyAssistantResult(r);          // открытый экран сразу перечитает данные
    } catch {
      push(mine, { message: "Не удалось выполнить команду", ok: false });
    } finally { setBusy(false); }
  }

  async function toggleRec() {
    if (rec && mrRef.current) { mrRef.current.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      mrRef.current = mr; chunksRef.current = [];
      mr.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRec(false); setBusy(true);
        try {
          const r = await api.assistantVoice(new Blob(chunksRef.current, { type: "audio/webm" }));
          push(r.transcript || "голосовая команда", r);
          notifyAssistantResult(r);
        } catch (e) {
          // Понятная причина вместо «ошибки сервера»: подготовка звука теперь
          // сама объясняет, что пошло не так.
          push("голосовая команда", { message: e?.message || "Не удалось распознать", ok: false });
        } finally { setBusy(false); }
      };
      mr.start(); setRec(true);
    } catch { setResult({ message: "Нет доступа к микрофону", ok: false }); }
  }

  function openEntity(r) {
    if (r.appointment_id) nav("/calendar");
    else if (r.reminder_id) nav("/tasks");
    else if (r.patient_id) nav("/patients/" + r.patient_id);
    close();
  }
  function close() { setOpen(false); setLog([]); setText(""); }

  const hasEntity = (result) => result && result.ok !== false
    && (result.appointment_id || result.reminder_id || result.patient_id);

  return (
    <>
      {/* Подсказка привязана к обёртке, а не к самой кнопке: кнопка плавающая,
          и обычная привязка поставила бы подсказку туда, где обёртка стоит в
          потоке — то есть мимо. Обёртка берёт координаты кнопки на себя. */}
      <Tip tipKey="tip:assistant" place="top" className="tip-fab" title="Ассистент — голосом и текстом"
           text="Скажите или напишите: «запиши Иванова на среду 15:00», «у Петрова ПСА 7,2». Видно, что ассистент понял и сделал, — можно уточнить следующей фразой. Записывает он только с вашего подтверждения.">
        <button className="asst-fab" onClick={() => setOpen(true)} title="Ассистент" aria-label="Ассистент">
          <i className="ti ti-sparkles" />
        </button>
      </Tip>

      {open && (
        <div className="asst-ov" onClick={close}>
          <div className="asst-sheet" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}><i className="ti ti-sparkles acc" /> Ассистент</div>
              <i className="ti ti-x muted" style={{ cursor: "pointer", fontSize: 18 }} onClick={close} />
            </div>
            {/* Примеры показываем, только пока разговора нет: иначе они
                превращаются в шум над каждой репликой. */}
            {log.length === 0 && (
              <div className="sub asst-hint">
                Скажите или напишите — можно несколько дел подряд:
                <div style={{ marginTop: 6, lineHeight: 1.7 }}>
                  • «запиши Иванова на 20 октября в 15 часов <b>и</b> Петрова на четверг в 10»<br />
                  • «назначь Иванову тадалафил 5 мг раз в день месяц»<br />
                  • «у Иванова ПСА 7,2»<br />
                  • «в карту Петрова: жалобы на никтурию»<br />
                  • «напомни через 20 минут позвонить»<br />
                  • «открой карту Иванова»
                </div>
              </div>
            )}

            <div className="asst-log">
              {log.map(({ mine, r }, i) => (
                <div key={i} className="asst-turn">
                  <div className="asst-mine">{mine}</div>
                  <div className={"asst-reply" + (r.ok === false ? " bad" : "")}>
                    <div style={{ whiteSpace: "pre-wrap" }}>
                      <i className={"ti " + (r.ok === false ? "ti-alert-circle dng" : "ti-check acc")} /> {r.message}
                    </div>
                    {r.suggest_create && r.surname && (
                      <div className="acc asst-act"
                           onClick={() => { setOpen(false); nav(`/start-visit?new=${encodeURIComponent(r.surname)}`); }}>
                        <i className="ti ti-user-plus" /> Создать карту «{r.surname}» →
                      </div>
                    )}
                    {hasEntity(r) && (
                      <div className="acc asst-act" onClick={() => openEntity(r)}>Открыть →</div>
                    )}
                  </div>
                </div>
              ))}
              {busy && <div className="sub asst-wait">Выполняю…</div>}
            </div>

            {/* Строка ввода прижата к низу шторки и поднимается с клавиатурой */}
            <div className="input asst-compose">
              <input value={text} onChange={(e) => setText(e.target.value)} autoFocus
                onKeyDown={(e) => e.key === "Enter" && send()}
                placeholder="Скажите или напишите…"
                style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)" }} />
              <button className="asst-mic-sm" onClick={toggleRec} title={rec ? "Остановить" : "Голосом"}
                      aria-label={rec ? "Остановить запись" : "Сказать голосом"}
                      style={{ background: rec ? "var(--dn)" : "var(--ac)" }}>
                <i className={"ti " + (rec ? "ti-player-stop" : "ti-microphone")} />
              </button>
              <button className="asst-send" disabled={busy || !text.trim()} onClick={send} aria-label="Выполнить">
                <i className="ti ti-send" />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
