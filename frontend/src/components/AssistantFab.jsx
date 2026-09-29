import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { notifyAssistantResult } from "../lib/bus";

// Единая точка входа в ассистента — плавающая кнопка + нижняя панель.
// Тот же движок команд (route_command), что и на Главной. Доступна с любого экрана.
export default function AssistantFab() {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);   // {message, ok, entity_type, entity_id}
  const [rec, setRec] = useState(false);
  const mrRef = useRef(null);
  const chunksRef = useRef([]);

  async function send() {
    if (!text.trim() || busy) return;
    setBusy(true); setResult(null);
    try {
      const r = await api.assistantCommand(text.trim());
      setText("");
      setResult(r);
      notifyAssistantResult(r);          // открытый экран сразу перечитает данные
    } catch {
      setResult({ message: "Не удалось выполнить команду", ok: false });
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
        setRec(false); setBusy(true); setResult(null);
        try {
          const r = await api.assistantVoice(new Blob(chunksRef.current, { type: "audio/webm" }));
          setResult(r);
          notifyAssistantResult(r);
        } catch { setResult({ message: "Не удалось распознать", ok: false }); }
        finally { setBusy(false); }
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
  function close() { setOpen(false); setResult(null); setText(""); }

  const hasEntity = result && result.ok !== false
    && (result.appointment_id || result.reminder_id || result.patient_id);

  return (
    <>
      <button className="asst-fab" onClick={() => setOpen(true)} title="Ассистент" aria-label="Ассистент">
        <i className="ti ti-sparkles" />
      </button>

      {open && (
        <div className="asst-ov" onClick={close}>
          <div className="asst-sheet" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}><i className="ti ti-sparkles acc" /> Ассистент</div>
              <i className="ti ti-x muted" style={{ cursor: "pointer", fontSize: 18 }} onClick={close} />
            </div>
            <div className="sub" style={{ marginBottom: 10 }}>
              Скажите или напишите — можно несколько дел подряд:
              <div className="sub" style={{ marginTop: 6, lineHeight: 1.7 }}>
                • «запиши Иванова на 20 октября в 15 часов <b>и</b> Петрова на четверг в 10»<br />
                • «назначь Иванову тадалафил 5 мг раз в день месяц»<br />
                • «у Иванова ПСА 7,2»<br />
                • «в карту Петрова: жалобы на никтурию»<br />
                • «напомни через 20 минут позвонить» · «контроль ПСА каждые 3 месяца»<br />
                • «открой карту Иванова»
              </div>
            </div>

            <div className="input" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              <i className="ti ti-keyboard muted" />
              <input value={text} onChange={(e) => setText(e.target.value)} autoFocus
                onKeyDown={(e) => e.key === "Enter" && send()}
                placeholder="Команда ассистенту…"
                style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)" }} />
              <button className="asst-mic-sm" onClick={toggleRec} title={rec ? "Остановить" : "Голосом"}
                      style={{ background: rec ? "var(--dn)" : "var(--ac)" }}>
                <i className={"ti " + (rec ? "ti-player-stop" : "ti-microphone")} />
              </button>
            </div>

            <button className="btn pri block" disabled={busy || !text.trim()} onClick={send}>
              {busy ? "Выполняю…" : "Выполнить"}
            </button>

            {result && (
              <div className="card" style={{ marginTop: 12, borderLeft: "3px solid " + (result.ok === false ? "var(--dn)" : "var(--ac)") }}>
                {/* при нескольких командах в сообщении перечень — переносы важны */}
                <div style={{ fontSize: 13.5, whiteSpace: "pre-wrap" }}>
                  <i className={"ti " + (result.ok === false ? "ti-alert-circle dng" : "ti-check acc")} /> {result.message}
                </div>
                {result.transcript && <div className="sub" style={{ marginTop: 4 }}>Распознано: «{result.transcript}»</div>}
                {result.suggest_create && result.surname && (
                  <div className="acc" style={{ fontSize: 12.5, marginTop: 8, cursor: "pointer" }}
                       onClick={() => { setOpen(false);
                                        nav(`/start-visit?new=${encodeURIComponent(result.surname)}`); }}>
                    <i className="ti ti-user-plus" /> Создать карту «{result.surname}» →
                  </div>
                )}
                {hasEntity && (
                  <div className="acc" style={{ fontSize: 12.5, marginTop: 8, cursor: "pointer" }} onClick={() => openEntity(result)}>
                    Открыть →
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
