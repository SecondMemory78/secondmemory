import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api";
import { confirmAction } from "../lib/confirm";
import { WD, weekDays, todayISO, fmtDay, MONTHS_GEN } from "../lib/dates";

export default function Week() {
  const { offset } = useParams();
  const nav = useNavigate();
  const off = parseInt(offset ?? "0", 10) || 0;
  const days = useMemo(() => weekDays(off), [off]);
  const TODAY = todayISO();
  const [sel, setSel] = useState(days.find((d) => d.iso === TODAY)?.iso || days[0].iso);
  const [appts, setAppts] = useState([]);

  function loadAppts() {
    api.appointments(days[0].iso, days[6].iso).then(setAppts).catch(() => setAppts([]));
  }
  useEffect(() => { setSel(days.find((d) => d.iso === TODAY)?.iso || days[0].iso); }, [off]);
  useEffect(() => { loadAppts(); }, [off]);

  async function cancel(id) {
    if (!(await confirmAction({ title: "Отменить приём?", danger: true, confirmText: "Отменить приём", cancelText: "Назад" }))) return;
    await api.cancelAppointment(id); loadAppts();
  }
  const [edit, setEdit] = useState(null);
  async function saveEdit() {
    await api.updateAppointment(edit.id, {
      starts_at: `${edit.date}T${edit.time}:00`, reason: edit.reason, kind: edit.kind,
    });
    setEdit(null); loadAppts();
  }

  const dayAppts = appts.filter((a) => a.day === sel);
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
          return (
            <div key={d.iso} style={{ textAlign: "center", cursor: "pointer" }} onClick={() => setSel(d.iso)}>
              <div style={{ fontSize: 11, color: "var(--tm)", marginBottom: 5 }}>{WD[i]}</div>
              {selected ? (
                <div style={{ width: 30, height: 30, borderRadius: "50%", background: "var(--ac)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, margin: "0 auto" }}>{d.day}</div>
              ) : (
                <div style={{ fontSize: 13, padding: "6px 0", color: isToday ? "var(--act)" : "var(--tp)", fontWeight: isToday ? 600 : 400 }}>{d.day}</div>
              )}
              <div style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--ac)", margin: "3px auto 0", visibility: has ? "visible" : "hidden" }} />
            </div>
          );
        })}
      </div>

      <div className="sub" style={{ fontWeight: 500, marginBottom: 6 }}>
        {dayAppts.length ? `${dayAppts.length} приёма` : "Свободный день"}
      </div>

      {dayAppts.length === 0 && (
        <div className="empty"><i className="ti ti-calendar-off" /><div style={{ fontSize: 13, marginBottom: 8 }}>На этот день приёмов нет</div></div>
      )}
      {dayAppts.map((a) => (
        <div key={a.id}>
        <div className="row">
          <div style={{ display: "flex", gap: 12, cursor: "pointer" }} onClick={() => nav(`/patients/${a.patient_id}`)}>
            <span className="mono acc" style={{ minWidth: 42 }}>{a.time}</span>
            <div>
              <div style={{ fontSize: 13.5 }}>{a.patient_name}</div>
              <div className="sub">{a.kind === "primary" ? "первичный" : "повторный"} · {a.reason}</div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <i className="ti ti-pencil muted" style={{ cursor: "pointer" }} title="Перенести / изменить"
              onClick={() => setEdit(edit?.id === a.id ? null : { id: a.id, date: a.day, time: a.time, reason: a.reason, kind: a.kind })} />
            <i className="ti ti-x muted" style={{ cursor: "pointer" }} title="Отменить приём" onClick={() => cancel(a.id)} />
          </div>
        </div>
        {edit?.id === a.id && (
          <div className="card" style={{ margin: "4px 0 10px" }}>
            <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
              <input className="input" type="date" value={edit.date} onChange={(e) => setEdit({ ...edit, date: e.target.value })} style={{ flex: 1 }} />
              <input className="input" type="time" value={edit.time} onChange={(e) => setEdit({ ...edit, time: e.target.value })} style={{ width: 110 }} />
            </div>
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

      <div className="btnrow">
        <button className="btn pri block" onClick={() => nav(`/new-entry/${sel}`)}>
          <i className="ti ti-calendar-plus" /> Новый приём на {fmtDay(sel)}
        </button>
      </div>
    </>
  );
}
