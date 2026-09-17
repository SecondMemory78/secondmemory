import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { WD, monthMatrix, monthRange, monthLabel, todayISO, weekOffsetOfISO, fmtDay } from "../lib/dates";

export default function Calendar() {
  const nav = useNavigate();
  const now = new Date();
  const [y, setY] = useState(now.getFullYear());
  const [m, setM] = useState(now.getMonth() + 1);
  const [appts, setAppts] = useState([]);
  const [sel, setSel] = useState(todayISO());

  useEffect(() => {
    const [from, to] = monthRange(y, m);
    api.appointments(from, to).then(setAppts).catch(() => setAppts([]));
  }, [y, m]);

  const byDay = {};
  for (const a of appts) (byDay[a.day] ??= []).push(a);
  const dayAppts = (byDay[sel] || []).sort((a, b) => a.time.localeCompare(b.time));
  const weeks = monthMatrix(y, m);
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
        <i className="ti ti-chevron-left muted" style={{ fontSize: 18, cursor: "pointer" }} onClick={() => shift(-1)} />
        <span style={{ fontSize: 15, fontWeight: 500 }}>{monthLabel(y, m)}</span>
        <i className="ti ti-chevron-right muted" style={{ fontSize: 18, cursor: "pointer" }} onClick={() => shift(1)} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", marginBottom: 6 }}>
        {WD.map((d) => <div key={d} style={{ textAlign: "center", fontSize: 11, color: "var(--tm)" }}>{d}</div>)}
      </div>

      {weeks.map((row, wi) => (
        <div key={wi} style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: 3, marginBottom: 3 }}>
          {row.map((c, i) => {
            const isToday = c.iso === TODAY;
            const isSel = c.iso === sel;
            const cnt = c.cur ? (byDay[c.iso]?.length || 0) : 0;
            return (
              <div key={i} onClick={() => c.cur && setSel(c.iso)}
                onDoubleClick={() => c.cur && nav(`/week/${weekOffsetOfISO(c.iso)}`)}
                style={{ minHeight: 46, borderRadius: 10, padding: "5px 0 4px", textAlign: "center", cursor: c.cur ? "pointer" : "default",
                  background: isSel ? "var(--acbg)" : "transparent", border: isSel ? ".5px solid var(--ac)" : ".5px solid transparent" }}>
                {isToday ? (
                  <div style={{ width: 24, height: 24, borderRadius: "50%", background: "var(--ac)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12.5, margin: "0 auto" }}>{c.day}</div>
                ) : (
                  <div style={{ fontSize: 12.5, color: c.cur ? "var(--tp)" : "var(--tm)", opacity: c.cur ? 1 : 0.45 }}>{c.day}</div>
                )}
                <div style={{ display: "flex", flexDirection: "column", gap: 2, alignItems: "center", marginTop: 4 }}>
                  {Array.from({ length: Math.min(cnt, 3) }).map((_, k) => (
                    <span key={k} style={{ width: 14, height: 3, borderRadius: 2, background: "var(--ac)" }} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ))}

      <div className="sec-label" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>{fmtDay(sel)} · {dayAppts.length ? dayAppts.length + " приёма" : "свободно"}</span>
        <span className="acc" style={{ fontSize: 12, cursor: "pointer" }} onClick={() => nav(`/week/${weekOffsetOfISO(sel)}`)}>открыть неделю →</span>
      </div>

      {dayAppts.length === 0 && <div className="sub">На этот день приёмов нет.</div>}
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

      <div className="btnrow">
        <button className="btn pri block" onClick={() => nav(`/new-entry/${sel}`)}>
          <i className="ti ti-calendar-plus" /> Новый приём на {fmtDay(sel)}
        </button>
      </div>
    </>
  );
}
