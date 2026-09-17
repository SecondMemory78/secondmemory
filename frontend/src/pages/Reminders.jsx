import { useEffect, useState } from "react";
import { api } from "../api";
import { Empty } from "../components/Loading";
import { confirmAction } from "../lib/confirm";
import { toast } from "../lib/toast";
import VoiceButton from "../components/VoiceButton";

const PRI = { 1: "var(--dn)", 2: "var(--wn)", 3: "var(--ac)", 4: "var(--tm)" };
// цвет по типу: приём-контроль — синий, обычная задача/звонок — фиолетовый (как напоминание)
const kindColor = (k) => (k === "control" || k === "appointment") ? "var(--ac)" : "var(--rm)";

export default function Reminders() {
  const [list, setList] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState("");
  const [mode, setMode] = useState("sections"); // sections | dates
  const [tab, setTab] = useState("active");     // active | done
  const [fading, setFading] = useState({});     // id → true (анимация ухода)

  function load() {
    api.reminders(tab === "done" ? "done" : "open").then(setList).catch(() => setList([]));
  }
  useEffect(() => { load(); }, [tab]);

  async function quickAdd() {
    if (!text.trim()) return;
    await api.quickReminder(text.trim(), null);
    setText(""); load();
  }
  async function voiceAdd(blob) {
    setBusy("Расшифровываю…"); await api.voiceReminder(null, blob); setBusy(""); load();
  }
  async function done(id) {
    setFading((f) => ({ ...f, [id]: true }));   // зачёркиваем и плавно убираем
    await api.reminderDone(id);
    setTimeout(() => { load(); setFading((f) => { const n = { ...f }; delete n[id]; return n; }); }, 320);
    toast("Задача выполнена", "success", { label: "Отменить", onAction: async () => { await api.reminderReopen(id); load(); } });
  }
  async function reopen(id) { await api.reminderReopen(id); load(); }
  async function postpone(id) { await api.reminderPostpone(id, 1); load(); }

  const [edit, setEdit] = useState(null);   // {id,title,due,priority,project,offsets}
  async function openEdit(r) {
    setEdit({ id: r.id, title: r.title, due: r.due_at ? r.due_at.slice(0, 10) : "",
              priority: r.priority, project: r.project, offsets: [],
              repeat_unit: r.repeat_unit || "", repeat_interval: r.repeat_interval || 1 });
    if (r.due_at) {
      const a = await api.eventAlerts("reminder", r.id).catch(() => []);
      setEdit((e) => e && e.id === r.id ? { ...e, offsets: a.map((x) => x.offset_minutes) } : e);
    }
  }
  function plusDays(n) {
    const d = new Date(); d.setDate(d.getDate() + n);
    return d.toISOString().slice(0, 10);
  }
  async function saveEdit() {
    await api.updateReminder(edit.id, { title: edit.title, due_at: edit.due,
                                        priority: edit.priority, project: edit.project,
                                        repeat_unit: edit.repeat_unit, repeat_interval: edit.repeat_interval });
    if (edit.due) await api.setReminderAlerts(edit.id, edit.offsets || []);
    setEdit(null); load();
  }
  async function removeReminder(id) {
    if (!(await confirmAction({ title: "Удалить задачу?", danger: true, confirmText: "Удалить" }))) return;
    await api.deleteReminder(id); setEdit(null); load();
  }

  // группировка
  const groups = {};
  if (mode === "sections") {
    for (const r of list) (groups[r.project || "Входящие"] ??= []).push(r);
  } else {
    for (const r of list) {
      const g = bucket(r);
      (groups[g] ??= []).push(r);
    }
  }
  const order = mode === "sections"
    ? Object.keys(groups).sort((a) => (a === "Входящие" ? -1 : 0))
    : ["Просрочено", "Сегодня", "Завтра", "Позже", "Без срока"].filter((k) => groups[k]);

  return (
    <>
      <div className="hd"><div className="ttl">Задачи</div></div>

      <div className="tabs" style={{ marginBottom: 10 }}>
        <div className={"t" + (tab === "active" ? " on" : "")} onClick={() => setTab("active")}>Активные</div>
        <div className={"t" + (tab === "done" ? " on" : "")} onClick={() => setTab("done")}>Выполненные</div>
      </div>

      {tab === "active" && (<>
      <div className="input" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <i className="ti ti-sparkles muted" />
        <input value={text} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && quickAdd()}
          placeholder="«созвон с командой в четверг #Работа»"
          style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)" }} />
      </div>
      <div className="btnrow" style={{ marginTop: 0 }}>
        <button className="btn sm pri" onClick={quickAdd}>Добавить</button>
        <VoiceButton onResult={voiceAdd} label="Голосом" />
      </div>
      <div className="sub" style={{ marginTop: 8 }}>Первый #тег — раздел (напр. #Работа, #Контроли).</div>
      {busy && <div className="banner b-ac" style={{ marginTop: 10 }}><i className="ti ti-loader-2" /> {busy}</div>}
      </>)}

      <div className="tabs" style={{ marginTop: 14 }}>
        <div className={"t" + (mode === "sections" ? " on" : "")} onClick={() => setMode("sections")}>По разделам</div>
        <div className={"t" + (mode === "dates" ? " on" : "")} onClick={() => setMode("dates")}>По датам</div>
      </div>

      {order.length === 0 && <Empty icon="ti-checklist" title="Задач нет" sub="Добавьте задачу голосом или текстом выше" />}
      {order.map((g) => (
        <div key={g}>
          <div className="sec-label" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            {mode === "sections" && <i className="ti ti-hash" style={{ fontSize: 12 }} />}{g}
            <span className="muted" style={{ fontWeight: 400 }}>· {groups[g].length}</span>
          </div>
          {groups[g].map((r) => (
            <div key={r.id} style={{ transition: "opacity .3s, transform .3s", opacity: fading[r.id] ? 0 : 1, transform: fading[r.id] ? "translateX(8px)" : "none" }}>
            <div className="row">
              <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                <span className="pri-dot" style={{ background: kindColor(r.kind), marginTop: 5 }} title={r.kind} />
                <div>
                  <div style={{ fontSize: 13.5, textDecoration: (fading[r.id] || tab === "done") ? "line-through" : "none", color: tab === "done" ? "var(--tm)" : "var(--tp)" }}>
                    {r.title}
                    {(r.repeat_unit || r.repeat_days) ? <i className="ti ti-repeat muted" style={{ fontSize: 13, marginLeft: 6, verticalAlign: -1 }} title="повторяется" /> : null}
                    {r.priority <= 2 ? <i className="ti ti-flag-filled" style={{ fontSize: 12, marginLeft: 6, color: PRI[r.priority] }} /> : null}
                  </div>
                  <div className="sub">
                    {due(r)}
                    {mode === "dates" && r.project !== "Входящие" ? " · #" + r.project : ""}
                    {r.labels ? " · " + r.labels.split(",").map((l) => "#" + l).join(" ") : ""}
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                {tab === "done" ? (
                  <span className="acc" style={{ fontSize: 12.5, cursor: "pointer" }} onClick={() => reopen(r.id)}>Вернуть</span>
                ) : (<>
                  <i className="ti ti-pencil muted" title="Перенести / изменить" style={{ fontSize: 17, cursor: "pointer" }} onClick={() => (edit?.id === r.id ? setEdit(null) : openEdit(r))} />
                  <i className="ti ti-circle-check muted" style={{ fontSize: 20, cursor: "pointer" }} onClick={() => done(r.id)} />
                </>)}
              </div>
            </div>
            {edit?.id === r.id && (
              <div className="card" style={{ margin: "4px 0 10px" }}>
                <input className="input" value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} style={{ marginBottom: 8 }} />
                <div className="sub" style={{ marginBottom: 4 }}>Перенести на:</div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
                  {[["Сегодня", plusDays(0)], ["Завтра", plusDays(1)], ["Через неделю", plusDays(7)], ["Убрать срок", ""]].map(([lbl, val]) => (
                    <span key={lbl} className="chip" style={{ padding: "5px 10px", borderRadius: 8, background: edit.due === val ? "var(--acbg)" : "var(--s1)", border: ".5px solid " + (edit.due === val ? "var(--ac)" : "var(--bd)"), fontSize: 12, cursor: "pointer" }} onClick={() => setEdit({ ...edit, due: val })}>{lbl}</span>
                  ))}
                </div>
                <input className="input" type="date" value={edit.due} onChange={(e) => setEdit({ ...edit, due: e.target.value })} style={{ marginBottom: 8 }} />
                <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                  <select className="input" value={edit.priority} onChange={(e) => setEdit({ ...edit, priority: Number(e.target.value) })} style={{ flex: 1 }}>
                    <option value={1}>Срочно (P1)</option><option value={2}>Важно (P2)</option>
                    <option value={3}>Средне (P3)</option><option value={4}>Обычный (P4)</option>
                  </select>
                  <input className="input" value={edit.project} onChange={(e) => setEdit({ ...edit, project: e.target.value })} placeholder="Раздел" style={{ flex: 1 }} />
                </div>
                {edit.due && (
                  <div style={{ marginBottom: 8 }}>
                    <div className="sub" style={{ marginBottom: 4 }}>Напомнить за:</div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {[5, 15, 30, 60, 1440].map((m) => {
                        const on = (edit.offsets || []).includes(m);
                        const lbl = m === 1440 ? "1 день" : m >= 60 ? m / 60 + " ч" : m + " мин";
                        return (
                          <span key={m} className="chip" style={{ padding: "5px 10px", borderRadius: 8,
                            background: on ? "var(--acbg)" : "var(--s1)", border: ".5px solid " + (on ? "var(--ac)" : "var(--bd)"),
                            fontSize: 12, cursor: "pointer", color: on ? "var(--ac)" : "var(--tp)" }}
                            onClick={() => setEdit({ ...edit, offsets: on ? edit.offsets.filter((x) => x !== m) : [...(edit.offsets || []), m] })}>
                            {on ? "✓ " : ""}{lbl}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                )}
                <div style={{ marginBottom: 8 }}>
                  <div className="sub" style={{ marginBottom: 4 }}>Повторять:</div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <select className="input" value={edit.repeat_unit || ""} style={{ flex: 1 }}
                      onChange={(e) => setEdit({ ...edit, repeat_unit: e.target.value })}>
                      <option value="">Не повторять</option>
                      <option value="day">Каждый день</option>
                      <option value="week">Каждую неделю</option>
                      <option value="month">Каждый месяц</option>
                      <option value="year">Каждый год</option>
                    </select>
                    {edit.repeat_unit && (
                      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <span className="sub">каждые</span>
                        <input className="input" type="number" min="1" style={{ width: 56 }}
                          value={edit.repeat_interval || 1}
                          onChange={(e) => setEdit({ ...edit, repeat_interval: Math.max(1, Number(e.target.value) || 1) })} />
                        <span className="sub">{{ day: "дн.", week: "нед.", month: "мес.", year: "лет" }[edit.repeat_unit]}</span>
                      </div>
                    )}
                  </div>
                  {edit.repeat_unit && !edit.due && <div className="sub dng" style={{ marginTop: 4, fontSize: 11 }}>Укажите дату — от неё считается следующий повтор.</div>}
                </div>
                <div className="btnrow">
                  <button className="btn sm dng" style={{ flex: 1 }} onClick={() => removeReminder(r.id)}><i className="ti ti-trash" /> Удалить</button>
                  <button className="btn pri sm" style={{ flex: 1 }} onClick={saveEdit}>Сохранить</button>
                </div>
              </div>
            )}
            </div>
          ))}
        </div>
      ))}
    </>
  );
}

function bucket(r) {
  if (!r.due_at) return "Без срока";
  const days = Math.floor((new Date(new Date(r.due_at).setHours(0, 0, 0, 0)) - new Date(new Date().setHours(0, 0, 0, 0))) / 86400000);
  if (days < 0) return "Просрочено";
  if (days === 0) return "Сегодня";
  if (days === 1) return "Завтра";
  return "Позже";
}
function due(r) {
  if (!r.due_at) return "без срока";
  const d = new Date(r.due_at);
  const days = Math.floor((new Date(new Date(d).setHours(0, 0, 0, 0)) - new Date(new Date().setHours(0, 0, 0, 0))) / 86400000);
  if (days < 0) return `просрочено ${-days} дн.`;
  if (days === 0) return "сегодня";
  if (days === 1) return "завтра";
  return d.toLocaleDateString("ru-RU");
}
