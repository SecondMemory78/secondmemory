import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { confirmAction } from "../lib/confirm";
import { WD, weekDays, todayISO, fmtDay, MONTHS_GEN } from "../lib/dates";
import { toast } from "../lib/toast";
import { fmtDateTime } from "../lib/dates";

export default function Week() {
  const { offset } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const off = parseInt(offset ?? "0", 10) || 0;
  const days = useMemo(() => weekDays(off), [off]);
  const TODAY = todayISO();
  const [sel, setSel] = useState(days.find((d) => d.iso === TODAY)?.iso || days[0].iso);
  const [appts, setAppts] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [taskDraft, setTaskDraft] = useState(null);   // null | {title, time}

  function loadAppts() {
    api.appointments(days[0].iso, days[6].iso).then(setAppts).catch(() => setAppts([]));
    api.remindersInRange(days[0].iso, days[6].iso).then(setTasks).catch(() => setTasks([]));
  }
  // открываем тот день, который выбрали в календаре, а не начало недели
  useEffect(() => {
    const wanted = params.get("day");
    const inWeek = wanted && days.some((d) => d.iso === wanted);
    setSel(inWeek ? wanted
                  : (days.find((d) => d.iso === TODAY)?.iso || days[0].iso));
  }, [off, params]);
  useEffect(() => { loadAppts(); }, [off]);

  async function setStatus(a, status) {
    try { await api.setAppointmentStatus(a.id, status); loadAppts(); }
    catch { toast("Не удалось изменить статус", "error"); }
  }

  async function addTask() {
    const title = (taskDraft.title || "").trim();
    if (!title) return;
    try {
      await api.createReminder({ title, due_at: `${sel}T${taskDraft.time || "09:00"}:00`, kind: "task" });
      setTaskDraft(null); loadAppts();
    } catch { toast("Не удалось создать задачу", "error"); }
  }

  async function cancel(id) {
    if (!(await confirmAction({ title: "Отменить приём?", danger: true, confirmText: "Отменить приём", cancelText: "Назад" }))) return;
    await api.cancelAppointment(id); loadAppts();
  }
  const [edit, setEdit] = useState(null);
  async function saveEdit() {
    await api.updateAppointment(edit.id, {
      starts_at: `${edit.date}T${edit.time}:00`, reason: edit.reason, kind: edit.kind,
      duration_min: edit.duration_min || 20,
    });
    setEdit(null); loadAppts();
  }

  const dayAppts = appts.filter((a) => a.day === sel);
  const dayTasks = tasks.filter((t) => t.day === sel)
                        .sort((a, b) => (a.time || "").localeCompare(b.time || ""));
  const label = `${days[0].day} ${MONTHS_GEN[days[0].month - 1]} – ${days[6].day} ${MONTHS_GEN[days[6].month - 1]}`;

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav("/calendar")} />
        <div className="ttl">Неделя</div>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 20, margin: "2px 0 12px" }}>
        <i className="ti ti-chevron-left muted" style={{ fontSize: 18, cursor: "pointer" }} onClick={() => nav(`/week/${off - 1}`)} />
        <span style={{ fontSize: 13.5, fontWeight: 500 }}>{label}</span>
        <i className="ti ti-chevron-right muted" style={{ fontSize: 18, cursor: "pointer" }} onClick={() => nav(`/week/${off + 1}`)} />
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14 }}>
        {days.map((d, i) => {
          const selected = d.iso === sel;
          const isToday = d.iso === TODAY;
          const has = appts.some((a) => a.day === d.iso);
          const hasTask = tasks.some((t) => t.day === d.iso);
          return (
            <div key={d.iso} style={{ textAlign: "center", cursor: "pointer" }} onClick={() => setSel(d.iso)}>
              <div style={{ fontSize: 11, color: "var(--tm)", marginBottom: 5 }}>{WD[i]}</div>
              {selected ? (
                <div style={{ width: 30, height: 30, borderRadius: "50%", background: "var(--ac)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, margin: "0 auto" }}>{d.day}</div>
              ) : (
                <div style={{ fontSize: 13, padding: "6px 0", color: isToday ? "var(--act)" : "var(--tp)", fontWeight: isToday ? 600 : 400 }}>{d.day}</div>
              )}
              <div style={{ display: "flex", gap: 2, justifyContent: "center", marginTop: 3, minHeight: 5 }}>
                {has && <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--ac)" }} />}
                {hasTask && <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--rm)" }} />}
              </div>
            </div>
          );
        })}
      </div>

      <div className="sub" style={{ fontWeight: 500, marginBottom: 6 }}>
        {dayAppts.length ? `${dayAppts.length} приёма` : "Приёмов нет"}
        {dayTasks.length ? ` · ${dayTasks.length} задач` : ""}
      </div>

      {dayAppts.length === 0 && dayTasks.length === 0 && (
        <div className="empty"><i className="ti ti-calendar-off" /><div style={{ fontSize: 13, marginBottom: 8 }}>На этот день ничего не запланировано</div></div>
      )}
      {dayAppts.map((a) => (
        <div key={a.id}>
        <div className="row">
          <div style={{ display: "flex", gap: 12, cursor: "pointer" }} onClick={() => nav(`/patients/${a.patient_id}`)}>
            <span className="mono acc" style={{ minWidth: 42 }}>{a.time}</span>
            <div>
              <div style={{ fontSize: 13.5 }}>
                {a.patient_name}
                {a.status === "done" && <span className="sub succ" style={{ marginLeft: 6 }}>· завершён</span>}
                {a.status === "no_show" && <span className="sub dng" style={{ marginLeft: 6 }}>· не пришёл</span>}
              </div>
              <div className="sub">
                {a.kind === "primary" ? "первичный" : "повторный"} · до {a.ends_time} ({a.duration_min} мин){a.reason ? ` · ${a.reason}` : ""}
              </div>
              {a.rescheduled_from && (
                <div className="sub" style={{ marginTop: 2 }}>
                  <i className="ti ti-arrow-move-right" style={{ fontSize: 12 }} /> перенесён с {fmtDateTime(a.rescheduled_from)}
                  {a.reschedule_count > 1 ? ` · переносов: ${a.reschedule_count}` : ""}
                </div>
              )}
            </div>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            {a.status === "planned" && (
              <>
                <i className="ti ti-check acc" style={{ cursor: "pointer" }} title="Завершить приём"
                   onClick={() => setStatus(a, "done")} />
                <i className="ti ti-user-x muted" style={{ cursor: "pointer" }} title="Не пришёл"
                   onClick={() => setStatus(a, "no_show")} />
              </>
            )}
            {a.status !== "planned" && (
              <i className="ti ti-arrow-back-up muted" style={{ cursor: "pointer" }} title="Вернуть в план"
                 onClick={() => setStatus(a, "planned")} />
            )}
            <i className="ti ti-pencil muted" style={{ cursor: "pointer" }} title="Перенести / изменить"
              onClick={() => setEdit(edit?.id === a.id ? null : { id: a.id, date: a.day, time: a.time, reason: a.reason, kind: a.kind, duration_min: a.duration_min })} />
            <i className="ti ti-x muted" style={{ cursor: "pointer" }} title="Отменить приём" onClick={() => cancel(a.id)} />
          </div>
        </div>
        {edit?.id === a.id && (
          <div className="card" style={{ margin: "4px 0 10px" }}>
            <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
              <input className="input" type="date" value={edit.date} onChange={(e) => setEdit({ ...edit, date: e.target.value })} style={{ flex: 1 }} />
              <input className="input" type="time" value={edit.time} onChange={(e) => setEdit({ ...edit, time: e.target.value })} style={{ width: 110 }} />
            </div>
            <input className="input" type="number" min="5" max="480" step="5" value={edit.duration_min || 20}
                   onChange={(e) => setEdit({ ...edit, duration_min: parseInt(e.target.value || "20", 10) })}
                   placeholder="Длительность, мин" style={{ marginBottom: 8 }} />
            <input className="input" value={edit.reason} onChange={(e) => setEdit({ ...edit, reason: e.target.value })} placeholder="Причина" style={{ marginBottom: 8 }} />
            <select className="input" value={edit.kind} onChange={(e) => setEdit({ ...edit, kind: e.target.value })} style={{ marginBottom: 8 }}>
              <option value="repeat">Повторный</option><option value="primary">Первичный</option>
            </select>
            <div className="btnrow">
              <button className="btn sm" style={{ flex: 1 }} onClick={() => setEdit(null)}>Отмена</button>
              <button className="btn pri sm" style={{ flex: 1 }} onClick={saveEdit}>Сохранить</button>
            </div>
          </div>
        )}
        </div>
      ))}

      {dayTasks.map((t) => (
        <div key={"t" + t.id} className="row" style={{ cursor: "pointer" }} onClick={() => nav("/tasks")}>
          <div style={{ display: "flex", gap: 12 }}>
            <span className="mono" style={{ minWidth: 42, color: "var(--rm)" }}>{t.time}</span>
            <div>
              <div style={{ fontSize: 13.5 }}><i className="ti ti-checkbox" style={{ color: "var(--rm)", marginRight: 4 }} />{t.title}</div>
              <div className="sub">задача{t.project && t.project !== "Входящие" ? ` · ${t.project}` : ""}</div>
            </div>
          </div>
          <i className="ti ti-chevron-right muted" />
        </div>
      ))}

      {taskDraft && (
        <div className="card" style={{ marginTop: 10 }}>
          <div className="sec-label" style={{ marginTop: 0 }}>Новая задача на {fmtDay(sel)}</div>
          <input className="input" placeholder="Что сделать" value={taskDraft.title} autoFocus
                 onChange={(e) => setTaskDraft({ ...taskDraft, title: e.target.value })}
                 onKeyDown={(e) => e.key === "Enter" && addTask()} style={{ marginBottom: 8 }} />
          <input className="input" type="time" value={taskDraft.time}
                 onChange={(e) => setTaskDraft({ ...taskDraft, time: e.target.value })} style={{ marginBottom: 8 }} />
          <div className="btnrow">
            <button className="btn sm" style={{ flex: 1 }} onClick={() => setTaskDraft(null)}>Отмена</button>
            <button className="btn pri sm" style={{ flex: 1 }} disabled={!taskDraft.title.trim()} onClick={addTask}>Создать</button>
          </div>
        </div>
      )}

      <div style={{ textAlign: "right", marginTop: 8 }}>
        <span className="acc" style={{ fontSize: 12, cursor: "pointer" }}
              onClick={() => api.schedulePdf(days[0].iso, days[6].iso).catch(() => toast("Не удалось сформировать", "error"))}>
          <i className="ti ti-printer" /> печать недели
        </span>
      </div>

      <div className="btnrow">
        <button className="btn pri" style={{ flex: 1 }} onClick={() => nav(`/new-entry/${sel}`)}>
          <i className="ti ti-calendar-plus" /> Приём
        </button>
        <button className="btn" style={{ flex: 1 }} onClick={() => setTaskDraft({ title: "", time: "09:00" })}>
          <i className="ti ti-checkbox" /> Задача
        </button>
      </div>
    </>
  );
}
