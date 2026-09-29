import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fmtDay } from "../lib/dates";
import { api } from "../api";
import TimeField from "../components/TimeField";

/**
 * Единый экран записи на приём. Объединяет «начать сейчас» и «запланировать»
 * в один поток: выбираешь пациента (нового или из картотеки) и время,
 * затем — одно из двух действий внизу.
 */
export default function NewEntry() {
  const { date } = useParams();
  const nav = useNavigate();
  const dateISO = date;

  const [tab, setTab] = useState("new");        // new | base
  const [time, setTime] = useState("09:00");
  const [form, setForm] = useState({ last_name: "", first_name: "", middle_name: "", birth_date: "", sex: "м", phone: "", diagnosis_code: "" });
  const [list, setList] = useState([]);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.patients("").then(setList).catch(() => {}); }, []);
  const upd = (k, v) => setForm({ ...form, [k]: v });

  async function resolvePatient() {
    if (tab === "base") return selected;
    if (!form.last_name.trim()) { alert("Укажите фамилию пациента."); return null; }
    const body = { ...form };
    if (!body.birth_date) delete body.birth_date;
    return await api.createPatient(body);
  }

  async function act(startNow) {
    const p = await resolvePatient();
    if (!p) { if (tab === "base") alert("Выберите пациента из списка."); return; }
    setBusy(true);
    await api.createAppointment({
      patient_id: p.id, starts_at: `${dateISO}T${time}:00`,
      kind: tab === "new" ? "primary" : "repeat",
      reason: startNow ? "приём" : "запланирован",
    });
    if (startNow) {
      // визит стартуем, только если согласие уже есть; иначе карта покажет барьер согласия
      try { await api.startEncounter(p.id, "приём"); await api.startSession(p.id); } catch (e) { /* нет согласия — оформит в карте */ }
      nav(`/patients/${p.id}`);
    } else {
      nav("/calendar");
    }
  }

  const filtered = q ? list.filter((p) => `${p.last_name} ${p.first_name}`.toLowerCase().includes(q.toLowerCase())) : list;

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
        <div className="ttl">Новый приём</div>
      </div>
      <div className="sub" style={{ marginBottom: 14 }}>{fmtDay(dateISO)}</div>

      <div className="tabs">
        <div className={"t" + (tab === "new" ? " on" : "")} onClick={() => setTab("new")}>Новый пациент</div>
        <div className={"t" + (tab === "base" ? " on" : "")} onClick={() => setTab("base")}>Из картотеки</div>
      </div>

      {tab === "new" ? (
        <>
          <F label="Фамилия"><input className="input" value={form.last_name} onChange={(e) => upd("last_name", e.target.value)} /></F>
          <div style={{ display: "flex", gap: 8 }}>
            <F label="Имя" flex><input className="input" value={form.first_name} onChange={(e) => upd("first_name", e.target.value)} /></F>
            <F label="Отчество" flex><input className="input" value={form.middle_name} onChange={(e) => upd("middle_name", e.target.value)} /></F>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <F label="Дата рождения" flex><input className="input" type="date" value={form.birth_date} onChange={(e) => upd("birth_date", e.target.value)} /></F>
            <F label="Диагноз (МКБ-10)" flex><input className="input" placeholder="N40.0" value={form.diagnosis_code} onChange={(e) => upd("diagnosis_code", e.target.value)} /></F>
          </div>
        </>
      ) : (
        <>
          <div className="input" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <i className="ti ti-search muted" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск пациента…"
              style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)" }} />
          </div>
          {filtered.map((p) => (
            <div key={p.id} className="row" style={{ cursor: "pointer", background: selected?.id === p.id ? "var(--acbg)" : "transparent", borderRadius: 8, paddingLeft: 8, paddingRight: 8 }}
              onClick={() => setSelected(p)}>
              <div style={{ display: "flex", gap: 11, alignItems: "center" }}>
                <div className="avatar">{(p.last_name[0] || "") + (p.first_name[0] || "")}</div>
                <div>
                  <div style={{ fontSize: 13.5 }}>{p.last_name} {p.first_name} {p.middle_name}</div>
                  <div className="sub">{[p.age && p.age + " лет", p.diagnosis_code].filter(Boolean).join(" · ")}</div>
                </div>
              </div>
              {selected?.id === p.id && <i className="ti ti-check acc" />}
            </div>
          ))}
        </>
      )}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 16 }}>
        <span className="sub" style={{ fontWeight: 500 }}>Время приёма</span>
        <TimeField value={time} onChange={setTime} />
      </div>

      <div className="btnrow">
        <button className="btn pri" style={{ flex: 1 }} disabled={busy} onClick={() => act(true)}>
          <i className="ti ti-player-play" /> Начать сейчас
        </button>
        <button className="btn" style={{ flex: 1 }} disabled={busy} onClick={() => act(false)}>
          <i className="ti ti-calendar-plus" /> Запланировать · {time}
        </button>
      </div>
      <div className="muted" style={{ fontSize: 11, textAlign: "center", marginTop: 10 }}>
        «Начать сейчас» — открыть карту и вести приём. «Запланировать» — поставить в расписание.
      </div>
    </>
  );
}

function F({ label, children, flex }) {
  return (
    <div style={{ flex: flex ? 1 : undefined, marginBottom: 10 }}>
      <div className="sub" style={{ marginBottom: 5 }}>{label}</div>
      {children}
    </div>
  );
}
