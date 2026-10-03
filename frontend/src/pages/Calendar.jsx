import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { dayKind, loadYear } from "../lib/holidays";
import { useSwipe } from "../lib/useSwipe";
import { WD, monthMatrix, monthRange, monthLabel, todayISO, weekOffsetOfISO, fmtDay } from "../lib/dates";
import { toast } from "../lib/toast";
import { onDataChanged } from "../lib/bus";

export default function Calendar() {
  const nav = useNavigate();
  const now = new Date();
  const [y, setY] = useState(now.getFullYear());
  const [m, setM] = useState(now.getMonth() + 1);
  const [appts, setAppts] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [sel, setSel] = useState(todayISO());
  const [taskDraft, setTaskDraft] = useState(null);   // null | {title, time}

  function loadMonth() {
    const [from, to] = monthRange(y, m);
    api.appointments(from, to).then(setAppts).catch(() => setAppts([]));
    api.remindersInRange(from, to).then(setTasks).catch(() => setTasks([]));
  }
  useEffect(() => { loadMonth(); }, [y, m]);
  useEffect(() => onDataChanged((d) => {
    if (d.scope === "calendar" || d.scope === "tasks") loadMonth();
  }), [y, m]);

  async function addTask() {
    const title = (taskDraft.title || "").trim();
    if (!title) return;
    const due = `${sel}T${taskDraft.time || "09:00"}:00`;
    try {
      await api.createReminder({ title, due_at: due, kind: "task" });
      setTaskDraft(null); loadMonth();
    } catch { toast("Не удалось создать задачу", "error"); }
  }

  const byDay = {};
  for (const a of appts) (byDay[a.day] ??= []).push(a);
  const taskByDay = {};
  for (const t of tasks) (taskByDay[t.day] ??= []).push(t);
  const dayAppts = (byDay[sel] || []).sort((a, b) => a.time.localeCompare(b.time));
  const dayTasks = (taskByDay[sel] || []).sort((a, b) => (a.time || "").localeCompare(b.time || ""));
  const weeks = monthMatrix(y, m);

  // Листание пальцем: в календаре это самый ожидаемый жест, без него экран
  // ощущается веб-страницей. Стрелки остаются — привычка у всех разная.
  // Направление нужно, чтобы содержимое приезжало с той стороны, куда ушёл
  // палец: иначе переключение читается как подмена, а не как переход.
  const [dir, setDir] = useState(1);
  const swipe = useSwipe((d) => { setDir(d); shift(d); });

  // Выходные и праздники: то же правило, что на Главной. Раньше оно жило
  // только там, и в календаре суббота ничем не отличалась от вторника.
  const [holidays, setHolidays] = useState(null);
  useEffect(() => { loadYear(y).then(setHolidays); }, [y]);
  const TODAY = todayISO();

  function shift(delta) {
    let nm = m + delta, ny = y;
    if (nm < 1) { nm = 12; ny--; } if (nm > 12) { nm = 1; ny++; }
    setY(ny); setM(nm);
  }

  return (
    <>
      <div className="hd"><div className="ttl">Календарь</div></div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 20, margin: "4px 0 14px" }}>
        <i className="ti ti-chevron-left muted period-arrow" onClick={() => shift(-1)} />
        <span style={{ fontSize: 15, fontWeight: 500 }}>{monthLabel(y, m)}</span>
        <i className="ti ti-chevron-right muted period-arrow" onClick={() => shift(1)} />
      </div>

      {/* Жест на сетке месяца: листать естественно по числам */}
      <div className="swipe-area" {...swipe}>
      {/* key по месяцу перезапускает анимацию: без него браузер считает, что
          элемент тот же, и движения не будет вовсе. */}
      <div key={`${y}-${m}`} className={dir > 0 ? "slide-fwd" : "slide-back"}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", marginBottom: 6 }}>
        {WD.map((d) => <div key={d} style={{ textAlign: "center", fontSize: 11, color: "var(--tm)" }}>{d}</div>)}
      </div>
      </div>

      {weeks.map((row, wi) => (
        <div key={wi} style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: 3, marginBottom: 3 }}>
          {row.map((c, i) => {
            const isToday = c.iso === TODAY;
            const isSel = c.iso === sel;
            const cnt = c.cur ? (byDay[c.iso]?.length || 0) : 0;
            const k = dayKind(c.iso, holidays);
            const tcnt = c.cur ? (taskByDay[c.iso]?.length || 0) : 0;
            return (
              <div key={i} onClick={() => c.cur && setSel(c.iso)}
                onDoubleClick={() => c.cur && nav(`/week/${weekOffsetOfISO(c.iso)}?day=${c.iso}`)}
                style={{ minHeight: 46, borderRadius: 10, padding: "5px 0 4px", textAlign: "center", cursor: c.cur ? "pointer" : "default",
                  background: isSel ? "var(--acbg)" : (k.off && c.cur ? "var(--s1)" : "transparent"),
                  border: isSel ? ".5px solid var(--ac)" : ".5px solid transparent" }}
                title={k.label || undefined}>
                {isToday ? (
                  <div style={{ width: 24, height: 24, borderRadius: "50%", background: "var(--ac)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12.5, margin: "0 auto" }}>{c.day}</div>
                ) : (
                  <div style={{ fontSize: 12.5,
                    // Праздник — красным: он требует внимания, в отличие от
                    // обычной субботы, у которой только подложка.
                    color: !c.cur ? "var(--tm)" : (k.holiday ? "var(--dn)" : "var(--tp)"),
                    fontWeight: k.holiday ? 600 : 400,
                    opacity: c.cur ? 1 : 0.45 }}>{c.day}</div>
                )}
                <div style={{ display: "flex", flexDirection: "column", gap: 2, alignItems: "center", marginTop: 4 }}>
                  {Array.from({ length: Math.min(cnt, 2) }).map((_, k) => (
                    <span key={"a" + k} style={{ width: 14, height: 3, borderRadius: 2, background: "var(--ac)" }} />
                  ))}
                  {Array.from({ length: Math.min(tcnt, 2) }).map((_, k) => (
                    <span key={"t" + k} style={{ width: 14, height: 3, borderRadius: 2, background: "var(--rm)" }} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ))}
      </div>

      <div className="sec-label" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>{fmtDay(sel)} · {dayAppts.length ? dayAppts.length + " приёма" : "приёмов нет"}{dayTasks.length ? ` · ${dayTasks.length} задач` : ""}</span>
        <span style={{ display: "flex", gap: 12 }}>
          <span className="acc" style={{ fontSize: 12, cursor: "pointer" }}
                onClick={() => api.schedulePdf(sel, sel).catch(() => toast("Не удалось сформировать", "error"))}>
            <i className="ti ti-printer" /> печать
          </span>
          <span className="acc" style={{ fontSize: 12, cursor: "pointer" }} onClick={() => nav(`/week/${weekOffsetOfISO(sel)}?day=${sel}`)}>открыть неделю →</span>
        </span>
      </div>

      {dayAppts.length === 0 && dayTasks.length === 0 && <div className="sub">На этот день ничего не запланировано.</div>}
      {dayAppts.map((a) => (
        <div key={a.id} className="row" style={{ cursor: "pointer" }} onClick={() => nav(`/patients/${a.patient_id}`)}>
          <div style={{ display: "flex", gap: 12 }}>
            <span className="mono acc" style={{ minWidth: 42 }}>{a.time}</span>
            <div>
              <div style={{ fontSize: 13.5 }}>{a.patient_name}</div>
              <div className="sub">{a.kind === "primary" ? "первичный" : "повторный"} · {a.reason}</div>
            </div>
          </div>
          <i className="ti ti-chevron-right muted" />
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
