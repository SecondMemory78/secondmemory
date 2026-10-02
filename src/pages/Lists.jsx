import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Spinner } from "../components/Loading";

export default function Lists() {
  const nav = useNavigate();
  const [presets, setPresets] = useState(null);
  const [open, setOpen] = useState(null);       // раскрытый код списка
  const [items, setItems] = useState({});       // code -> items[]

  useEffect(() => { api.lists().then((r) => setPresets(r.presets)).catch(() => setPresets([])); }, []);

  async function toggle(code) {
    if (open === code) { setOpen(null); return; }
    setOpen(code);
    if (!items[code]) {
      const r = await api.list(code).catch(() => null);
      if (r) setItems((m) => ({ ...m, [code]: r.items }));
    }
  }

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav("/more")} />
        <div className="ttl">Списки пациентов</div>
      </div>
      <div className="sub" style={{ marginBottom: 12 }}>
        Готовые фильтры по подтверждённым данным и незавершённым действиям. Список только подсказывает — ничего не назначает.
      </div>

      {presets === null && <Spinner />}
      {presets && presets.length === 0 && <div className="sub">Списки недоступны.</div>}

      {presets && presets.map((p) => (
        <div key={p.code} className="card" style={{ marginBottom: 10 }}>
          <div className="row" style={{ cursor: "pointer", borderTop: "none", padding: "2px 0" }}
               onClick={() => toggle(p.code)}>
            <div>
              <div style={{ fontSize: 13.5, fontWeight: 500 }}>{p.title}</div>
              <div className="sub" style={{ marginTop: 2 }}>{p.code}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className={"badge" + (p.count ? " badge-warn" : "")}>{p.count}</span>
              <i className={"ti muted " + (open === p.code ? "ti-chevron-up" : "ti-chevron-down")} />
            </div>
          </div>

          {open === p.code && (
            <div style={{ marginTop: 4 }}>
              {!items[p.code] && <Spinner />}
              {items[p.code] && items[p.code].length === 0 && (
                <div className="sub" style={{ padding: "8px 0" }}>Сейчас в этом списке никого нет.</div>
              )}
              {items[p.code] && items[p.code].map((it) => (
                <div key={it.patient_id} className="row" style={{ cursor: "pointer" }}
                     onClick={() => nav(`/patients/${it.patient_id}`)}>
                  <div>
                    <div style={{ fontSize: 13.5, fontWeight: 500 }}>{it.name}</div>
                    <div className="sub" style={{ marginTop: 2 }}>
                      {it.reason}{it.due ? ` · срок ${it.due}` : ""}
                    </div>
                  </div>
                  <i className="ti ti-chevron-right muted" />
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </>
  );
}
