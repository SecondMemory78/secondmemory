import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { toast } from "../lib/toast";

// Снимок направления или бумажки → дело.
//
// Главное здесь — что ничего не создаётся, пока врач не нажал. Распознавание
// ошибается в датах и фамилиях, а задача с неверным сроком хуже, чем её
// отсутствие: врач на неё рассчитывает и не перепроверяет.

export default function Capture() {
  const nav = useNavigate();
  const fileRef = useRef(null);
  const [state, setState] = useState("idle");   // idle | wait | ready | failed
  const [res, setRes] = useState(null);
  const [form, setForm] = useState({ kind: "task", title: "", due_at: "" });

  async function pick(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setState("wait"); setRes(null);
    const r = await api.captureUpload(file);
    if (r._error) { setState("failed"); toast(r.detail || "Не удалось отправить снимок", "error"); return; }
    poll(r.capture_id, 0);
  }

  async function poll(id, tries) {
    if (tries > 40) { setState("failed"); return; }   // примерно две минуты
    try {
      const got = await api.captureResult(id);
      if (got.ocr_status === "queued") { setTimeout(() => poll(id, tries + 1), 3000); return; }
      if (got.ocr_status === "failed") { setState("failed"); setRes(got); return; }
      setRes(got);
      setForm({
        kind: got.proposal?.kind || "task",
        title: got.proposal?.title || "",
        due_at: got.proposal?.due_at ? String(got.proposal.due_at).slice(0, 16) : "",
      });
      setState("ready");
    } catch { setTimeout(() => poll(id, tries + 1), 3000); }
  }

  async function accept() {
    const body = { kind: form.kind, title: form.title };
    if (form.due_at) body.due_at = form.due_at;
    if (res?.proposal?.patient_id) body.patient_id = res.proposal.patient_id;
    const r = await api.captureAccept(res.capture_id, body);
    if (r._error) { toast(r.detail || "Не удалось создать", "error"); return; }
    toast(r.message || "Создано", "success");
    nav(form.kind === "appointment" ? "/calendar" : "/tasks");
  }

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
        <div className="ttl" style={{ flex: 1 }}>Снимок в дело</div>
      </div>

      <div className="sub" style={{ marginBottom: 14 }}>
        Сфотографируйте направление, памятку или экран — разберу и предложу
        задачу или запись. Ничего не создаётся, пока вы не подтвердите.
      </div>

      <input ref={fileRef} type="file" accept="image/*" capture="environment"
             style={{ display: "none" }} onChange={pick} />

      {state === "idle" && (
        <button className="btn pri block" onClick={() => fileRef.current.click()}>
          <i className="ti ti-camera" /> Сфотографировать
        </button>
      )}

      {state === "wait" && (
        <div className="card">
          <div className="sub"><i className="ti ti-loader" /> Снимок принят, разбираю.
            Можно свернуть — результат дождётся.</div>
        </div>
      )}

      {state === "failed" && (
        <div className="card">
          <div className="sub dng">
            Не удалось разобрать снимок. Попробуйте переснять: текст должен быть
            в фокусе и целиком в кадре.
          </div>
          <button className="btn block" style={{ marginTop: 10 }}
                  onClick={() => { setState("idle"); setRes(null); }}>Ещё раз</button>
        </div>
      )}

      {state === "ready" && (
        <>
          <div className="sec-label" style={{ marginTop: 0 }}>Что предлагаю</div>

          <div className="tabs" style={{ marginBottom: 12 }}>
            <div className={"t" + (form.kind === "task" ? " on" : "")}
                 onClick={() => setForm({ ...form, kind: "task" })}>Задача</div>
            <div className={"t" + (form.kind === "appointment" ? " on" : "")}
                 onClick={() => setForm({ ...form, kind: "appointment" })}>Запись на приём</div>
          </div>

          <label className="fld">
            <span>Что сделать</span>
            <input className="input" value={form.title}
                   onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </label>

          <label className="fld">
            <span>Срок {form.kind === "appointment" ? "(обязательно)" : "(необязательно)"}</span>
            <input className="input" type="datetime-local" value={form.due_at}
                   onChange={(e) => setForm({ ...form, due_at: e.target.value })} />
          </label>

          {res.proposal?.patient_name && (
            <div className="sub" style={{ marginBottom: 10 }}>
              Пациент: {res.proposal.patient_name}
            </div>
          )}
          {res.proposal?.ambiguous_patients?.length > 0 && (
            /* Тёзки: выбирать за врача нельзя — истории смешать нельзя */
            <div className="banner b-wn" style={{ marginBottom: 10, display: "block" }}>
              Нашлось несколько однофамильцев — пациента выберите в карте,
              я не буду угадывать.
            </div>
          )}

          <div className="btnrow">
            <button className="btn" style={{ flex: 1 }}
                    onClick={() => { setState("idle"); setRes(null); }}>Отмена</button>
            <button className="btn pri" style={{ flex: 1 }} disabled={!form.title.trim()}
                    onClick={accept}>Создать</button>
          </div>

          <div className="sec-label">Что прочитал</div>
          <div className="card">
            <div className="sub" style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
              {res.text || "— пусто —"}
            </div>
          </div>
        </>
      )}
    </>
  );
}
