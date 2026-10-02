import { useState, useRef } from "react";
import { useLocation } from "react-router-dom";
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

  // ── снимок из шторки ──────────────────────────────────────────────────────
  const loc = useLocation();
  const fileRef = useRef(null);
  const [shot, setShot] = useState(null);     // предложение по снимку

  // Чья карта открыта — подсказка разбору. Не решение: врачу приносят чужие
  // бумаги прямо на приёме, поэтому выбор всё равно подтверждает он.
  const openPatientId = (() => {
    const m = loc.pathname.match(/^\/patients\/(\d+)/);
    return m ? Number(m[1]) : null;
  })();

  async function pickPhoto(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true); setShot({ status: "wait" });
    const r = await api.captureUpload(file, openPatientId);
    setBusy(false);
    if (r._error) { setShot(null); push("фото", { message: r.detail || "Не удалось отправить снимок", ok: false }); return; }
    pollShot(r.capture_id, 0);
  }

  async function pollShot(cid, tries) {
    if (tries > 40) { setShot({ status: "slow" }); return; }
    try {
      const got = await api.captureResult(cid);
      if (got.ocr_status === "queued") { setTimeout(() => pollShot(cid, tries + 1), 3000); return; }
      if (got.ocr_status === "failed") { setShot({ status: "failed" }); return; }
      setShot({ status: "ready", ...got });
    } catch { setTimeout(() => pollShot(cid, tries + 1), 3000); }
  }

  async function acceptShot(kind) {
    const body = { kind };
    if (kind === "document") body.patient_id = shot.proposal?.patient_id;
    const r = await api.captureAccept(shot.capture_id, body);
    setShot(null);
    if (r._error) { push("фото", { message: r.detail || "Не удалось", ok: false }); return; }
    push("фото", r);
    notifyAssistantResult(r);
  }

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

            {/* Куда положить снимок. Спрашиваем ВСЕГДА, даже когда карта
                открыта и фамилия совпала: врачу приносят чужие бумаги прямо
                на приёме, а разделить смешанные истории потом нельзя. */}
            {shot && (
              <div className="card asst-shot">
                {shot.status === "wait" && <div className="sub"><i className="ti ti-loader" /> Снимок принят, разбираю…</div>}
                {shot.status === "slow" && <div className="sub wn">Распознавание затянулось — попробуйте ещё раз.</div>}
                {shot.status === "failed" && (
                  <div className="sub dng">Не удалось разобрать. Переснимите: текст должен быть
                    в фокусе и целиком в кадре.</div>
                )}
                {shot.status === "ready" && (
                  <>
                    {shot.proposal?.mismatch && (
                      <div className="sub dng" style={{ marginBottom: 6 }}>
                        Открыта карта {shot.proposal.mismatch.context}, а в документе
                        {" "}{shot.proposal.mismatch.in_text}. Проверьте, чей это документ.
                      </div>
                    )}
                    <div style={{ fontSize: 13.5, marginBottom: 6 }}>
                      {shot.proposal?.patient_name
                        ? <>Похоже на документ: <b>{shot.proposal.patient_name}</b>
                            <span className="sub"> · {shot.proposal.patient_from}</span></>
                        : "Не понял, чей это документ."}
                    </div>
                    <div className="sub" style={{ marginBottom: 8, maxHeight: 60, overflow: "hidden" }}>
                      {shot.text?.slice(0, 160) || "— текст не распознан —"}
                    </div>
                    <div className="btnrow">
                      {shot.proposal?.patient_id && (
                        <button className="btn pri sm" style={{ flex: 1 }}
                                onClick={() => acceptShot("document")}>
                          В карту
                        </button>
                      )}
                      <button className="btn sm" style={{ flex: 1 }}
                              onClick={() => acceptShot("task")}>Заметка себе</button>
                      <button className="btn sm" onClick={() => setShot(null)}>Отмена</button>
                    </div>
                    {shot.proposal?.patient_id && (
                      <div className="sub" style={{ marginTop: 6 }}>
                        Другой пациент — откройте его карту и приложите снимок оттуда.
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {/* Строка ввода прижата к низу шторки и поднимается с клавиатурой */}
            <div className="input asst-compose">
              {/* Скрепка слева: врач хочет одно действие, а не переход на
                  отдельный экран. Снимок разбирается тем же механизмом, что
                  и «Снимок в дело» — второй копии распознавания нет. */}
              <input ref={fileRef} type="file" accept="image/*" capture="environment"
                     style={{ display: "none" }} onChange={pickPhoto} />
              <button className="asst-clip" onClick={() => fileRef.current.click()}
                      title="Приложить фото" aria-label="Приложить фото">
                <i className="ti ti-paperclip" />
              </button>
              <input value={text} onChange={(e) => setText(e.target.value)} autoFocus
                onKeyDown={(e) => e.key === "Enter" && send()}
                placeholder="Скажите или напишите…"
                style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)" }} />
              <button className="asst-mic-sm" onClick={toggleRec} title={rec ? "Остановить" : "Голосом"}
                      aria-label={rec ? "Остановить запись" : "Сказать голосом"}
                      style={{ background: rec ? "var(--dns)" : "var(--ac)" }}>
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
