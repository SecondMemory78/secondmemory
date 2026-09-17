import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

export default function StartVisit() {
  const nav = useNavigate();
  const [session, setSession] = useState(null);
  const [list, setList] = useState([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.activeSession().then(setSession).catch(() => setSession({ active: false }));
    api.patients("").then(setList).catch(() => setList([]));
  }, []);

  async function start(pid) {
    await api.startEncounter(pid, "приём");
    await api.startSession(pid);
    nav(`/patients/${pid}`);
  }

  const filtered = q
    ? list.filter((p) => `${p.last_name} ${p.first_name}`.toLowerCase().includes(q.toLowerCase()))
    : list;

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
        <div className="ttl">Начать приём</div>
      </div>

      {session?.active && (
        <div className="card" style={{ margin: "6px 0 16px" }}>
          <div style={{ display: "flex", gap: 9, alignItems: "flex-start", marginBottom: 12 }}>
            <i className="ti ti-history acc" style={{ fontSize: 19, marginTop: 1 }} />
            <div>
              <div style={{ fontSize: 13.5, fontWeight: 500 }}>Продолжить приём?</div>
              <div className="sub" style={{ marginTop: 2 }}>
                Вы работали с пациентом {session.patient_name} — пауза {session.idle_minutes} мин
              </div>
            </div>
          </div>
          <div className="btnrow" style={{ marginTop: 0 }}>
            <button className="btn pri" style={{ flex: 1 }} onClick={() => nav(`/patients/${session.patient_id}`)}>Продолжить</button>
            <button className="btn" onClick={() => setSession({ active: false })}>Новый пациент</button>
          </div>
        </div>
      )}

      <div className="sub" style={{ fontWeight: 500, marginBottom: 8 }}>С кем начинаем приём?</div>
      <div className="input" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <i className="ti ti-search muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск пациента…"
          style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)" }} />
      </div>
      {filtered.map((p) => (
        <div key={p.id} className="row" style={{ cursor: "pointer" }} onClick={() => start(p.id)}>
          <div style={{ display: "flex", gap: 11, alignItems: "center" }}>
            <div className="avatar">{(p.last_name[0] || "") + (p.first_name[0] || "")}</div>
            <div>
              <div style={{ fontSize: 13.5 }}>{p.last_name} {p.first_name} {p.middle_name}</div>
              <div className="sub">{[p.age && p.age + " лет", p.diagnosis_code].filter(Boolean).join(" · ")}</div>
            </div>
          </div>
          <i className="ti ti-chevron-right muted" />
        </div>
      ))}
    </>
  );
}
