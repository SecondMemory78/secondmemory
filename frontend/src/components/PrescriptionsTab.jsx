import { useEffect, useState } from "react";
import { api } from "../api";
import { toast } from "../lib/toast";

export default function PrescriptionsTab({ id, disabled }) {
  const [items, setItems] = useState(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ drug_name: "", dose: "", regimen: "" });
  const [conflict, setConflict] = useState(null);   // предупреждение о конфликте с аллергией
  const [override, setOverride] = useState("");

  function load() { api.prescriptions(id).then((r) => setItems(r.items)).catch(() => setItems([])); }
  useEffect(() => { load(); }, [id]);

  async function save(withOverride) {
    const body = { drug_name: form.drug_name.trim(), dose: form.dose.trim(),
                   regimen: form.regimen.trim() };
    if (withOverride) body.override_reason = override.trim();
    if (!body.drug_name) return;
    const r = await api.prescribe(id, body).catch(() => null);
    if (!r) return toast("Не удалось сохранить назначение", "error");
    if (r.conflict && !r.saved) {
      // система не блокирует — показывает предупреждение и просит причину
      setConflict(r);
      return;
    }
    setAdding(false); setConflict(null); setOverride("");
    setForm({ drug_name: "", dose: "", regimen: "" });
    load();
  }

  async function cancel(rx) {
    const r = await api.cancelPrescription(rx.id).catch(() => null);
    if (!r) return toast("Не удалось отменить", "error");
    toast("Назначение отменено", "success"); load();
  }

  if (items === null) return <div className="sub">Загрузка назначений…</div>;
  const active = items.filter((x) => x.status === "active");
  const cancelled = items.filter((x) => x.status !== "active");

  return (
    <div>
      <div className="copyrow" style={{ marginBottom: 6 }}>
        <span className="lbl">Назначения</span>
        {!disabled && !adding && <button className="btn sm" onClick={() => setAdding(true)}>Добавить</button>}
      </div>

      {adding && (
        <div className="card" style={{ marginBottom: 10 }}>
          <input className="input" placeholder="Препарат (МНН или бренд)" value={form.drug_name}
                 style={{ marginBottom: 8 }} onChange={(e) => setForm({ ...form, drug_name: e.target.value })} />
          <input className="input" placeholder="Доза (напр. 0,4 мг)" value={form.dose}
                 style={{ marginBottom: 8 }} onChange={(e) => setForm({ ...form, dose: e.target.value })} />
          <input className="input" placeholder="Схема (напр. 1 раз в день)" value={form.regimen}
                 style={{ marginBottom: 8 }} onChange={(e) => setForm({ ...form, regimen: e.target.value })} />

          {conflict && (
            <div className="card" style={{ marginBottom: 8, borderLeft: "3px solid var(--dn)" }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                <i className="ti ti-alert-triangle dng" /> Возможный конфликт с аллергией
              </div>
              <div className="sub" style={{ marginBottom: 8 }}>{conflict.message}</div>
              <div className="sub" style={{ marginBottom: 4 }}>Система не запрещает — решение за вами. Укажите причину, чтобы всё равно назначить:</div>
              <input className="input" placeholder="Причина назначения несмотря на предупреждение"
                     value={override} style={{ marginBottom: 8 }} onChange={(e) => setOverride(e.target.value)} />
            </div>
          )}

          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn" onClick={() => { setAdding(false); setConflict(null); setOverride(""); }}>Отмена</button>
            {!conflict
              ? <button className="btn pri" onClick={() => save(false)}>Сохранить</button>
              : <button className="btn pri" disabled={!override.trim()} onClick={() => save(true)}>Назначить с причиной</button>}
          </div>
        </div>
      )}

      {active.length === 0 && !adding && <div className="sub" style={{ marginBottom: 8 }}>Активных назначений нет.</div>}

      {active.map((rx) => (
        <div key={rx.id} className="card" style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 13.5, fontWeight: 500 }}>{rx.drug_name}</div>
          <div className="sub" style={{ marginTop: 2 }}>
            {[rx.dose, rx.regimen].filter(Boolean).join(" · ") || "без деталей"}
          </div>
          {!disabled && (
            <div style={{ marginTop: 8 }}>
              <button className="btn sm" onClick={() => cancel(rx)}>Отменить</button>
            </div>
          )}
        </div>
      ))}

      {cancelled.length > 0 && (
        <>
          <div className="sub" style={{ margin: "10px 0 6px" }}>Отменённые</div>
          {cancelled.map((rx) => (
            <div key={rx.id} className="row" style={{ opacity: 0.7 }}>
              <div>
                <div style={{ fontSize: 13 }}>{rx.drug_name}</div>
                <div className="sub" style={{ marginTop: 2 }}>
                  отменено{rx.cancelled_at ? ` ${rx.cancelled_at.slice(0, 10)}` : ""}
                </div>
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
