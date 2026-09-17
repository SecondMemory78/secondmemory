import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";

const OPS = [">", "<", ">=", "<="];

export default function Search() {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const [q, setQ] = useState(sp.get("q") || "");
  const [found, setFound] = useState([]);
  const [showCohort, setShowCohort] = useState(false);
  const [paramList, setParamList] = useState([{ code: "psa_total", name: "PSA общий" }]);

  useEffect(() => {
    api.commonParams(60).then((r) => { if (r.items?.length) setParamList(r.items); }).catch(() => {});
  }, []);

  // срез по картотеке
  const [dx, setDx] = useState("");
  const [param, setParam] = useState("psa_total");
  const [op, setOp] = useState(">");
  const [thr, setThr] = useState("4.0");
  const [cohort, setCohort] = useState(null);

  useEffect(() => {
    const t = setTimeout(() => {
      if (q.trim()) api.patients(q.trim()).then(setFound).catch(() => setFound([]));
      else setFound([]);
    }, 200);
    return () => clearTimeout(t);
  }, [q]);

  async function runCohort() {
    const body = { parameter_code: param, op, threshold: parseFloat(thr) };
    if (dx.trim()) body.diagnosis_code = dx.trim();
    setCohort(await api.cohort(body));
  }

  async function saveTrigger() {
    const body = { parameter_code: param, op, threshold: parseFloat(thr) };
    if (dx.trim()) body.diagnosis_code = dx.trim();
    const t = await api.createTrigger(body);
    alert(`Триггер создан: ${t.name}. Найдено сейчас: ${t.matches}. Управление — в «Ещё → Автослежение».`);
  }

  return (
    <>
      <div className="hd"><i className="ti ti-arrow-left back" onClick={() => nav(-1)} /><div className="ttl">Поиск</div></div>

      <div className="input" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <i className="ti ti-search muted" />
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Пациент или диагноз (напр. ДГПЖ, N40.0)…"
          style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)" }} />
      </div>

      {found.map((p) => (
        <div key={p.id} className="row" style={{ cursor: "pointer" }} onClick={() => nav(`/patients/${p.id}`)}>
          <div style={{ display: "flex", gap: 11, alignItems: "center" }}>
            <div className="avatar">{(p.last_name[0] || "") + (p.first_name[0] || "")}</div>
            <div>
              <div style={{ fontSize: 13.5 }}>{p.last_name} {p.first_name} {p.middle_name}</div>
              <div className="sub">{[p.age && p.age + " лет", p.diagnosis_code, p.diagnosis_text].filter(Boolean).join(" · ")}</div>
            </div>
          </div>
          <i className="ti ti-chevron-right muted" />
        </div>
      ))}
      {q && found.length === 0 && <div className="sub" style={{ marginTop: 6 }}>Ничего не найдено.</div>}

      <div className="sec-label" style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }} onClick={() => setShowCohort(!showCohort)}>
        <i className={"ti " + (showCohort ? "ti-chevron-down" : "ti-chevron-right")} style={{ fontSize: 13 }} />
        Срез по картотеке
      </div>

      {showCohort && (
        <div className="card">
          <F label="Диагноз (МКБ-10, необязательно)"><input className="input" placeholder="N40.0" value={dx} onChange={(e) => setDx(e.target.value)} /></F>
          <div className="sub" style={{ margin: "10px 0 5px" }}>Показатель</div>
          <div style={{ display: "flex", gap: 6 }}>
            <select className="input" value={param} onChange={(e) => setParam(e.target.value)}>
              {paramList.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
            </select>
            <select className="input" style={{ width: 64 }} value={op} onChange={(e) => setOp(e.target.value)}>
              {OPS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
            <input className="input" style={{ width: 80 }} value={thr} onChange={(e) => setThr(e.target.value)} />
          </div>
          <button className="btn pri block" style={{ marginTop: 12 }} onClick={runCohort}>Показать</button>

          {cohort && (
            <>
              <div className="sub" style={{ marginTop: 12, marginBottom: 4 }}>Найдено: {cohort.length}</div>
              {cohort.map((p) => (
                <div key={p.id} className="row" style={{ cursor: "pointer" }} onClick={() => nav(`/patients/${p.id}`)}>
                  <div style={{ fontSize: 13.5 }}>{p.short_name} · {p.age} лет</div>
                  <div className="mono warn">{p.key_value}</div>
                </div>
              ))}
              <button className="btn block" style={{ marginTop: 12 }} onClick={saveTrigger}>
                <i className="ti ti-bell-plus" /> Следить за этим условием (триггер)
              </button>
            </>
          )}
        </div>
      )}
    </>
  );
}

function F({ label, children }) {
  return <div><div className="sub" style={{ marginBottom: 5 }}>{label}</div>{children}</div>;
}
