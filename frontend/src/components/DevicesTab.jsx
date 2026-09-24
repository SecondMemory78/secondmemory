import { useEffect, useState } from "react";
import { api } from "../api";
import { toast } from "../lib/toast";

const KIND_RU = { catheter: "Катетер", stent: "Стент", nephrostomy: "Нефростома" };
const ACTION_RU = { removed: "удалён", replaced: "заменён" };

export default function DevicesTab({ id, disabled }) {
  const [items, setItems] = useState(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ kind: "stent", device_label: "", due_at: "" });
  const [replaceOf, setReplaceOf] = useState(null);   // id заменяемого
  const [rform, setRform] = useState({ device_label: "", due_at: "" });

  function load() { api.devices(id).then((r) => setItems(r.items)).catch(() => setItems([])); }
  useEffect(() => { load(); }, [id]);

  async function add() {
    const body = { kind: form.kind, device_label: form.device_label.trim(),
                   due_at: form.due_at || null };
    const r = await api.addDevice(id, body).catch(() => null);
    if (!r) return toast("Не удалось добавить устройство", "error");
    setAdding(false); setForm({ kind: "stent", device_label: "", due_at: "" });
    load();
  }

  async function close(d) {
    const r = await api.closeDevice(id, d.id, { action: "removed" }).catch(() => null);
    if (!r) return toast("Не удалось снять устройство", "error");
    toast("Устройство снято", "success"); load();
  }

  async function doReplace(d) {
    const body = { device_label: rform.device_label.trim() || d.device_label,
                   due_at: rform.due_at || null };
    const r = await api.replaceDevice(id, d.id, body).catch(() => null);
    if (!r) return toast("Не удалось заменить устройство", "error");
    toast("Устройство заменено", "success");
    setReplaceOf(null); setRform({ device_label: "", due_at: "" }); load();
  }

  if (items === null) return <div className="sub">Загрузка устройств…</div>;

  const active = items.filter((d) => d.active);
  const closed = items.filter((d) => !d.active);

  return (
    <div>
      <div className="copyrow" style={{ marginBottom: 6 }}>
        <span className="lbl">Устройства</span>
        {!disabled && !adding && (
          <button className="btn sm" onClick={() => setAdding(true)}>Добавить</button>
        )}
      </div>

      {adding && (
        <div className="card" style={{ marginBottom: 10 }}>
          <select className="input" value={form.kind} style={{ marginBottom: 8 }}
                  onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            <option value="stent">Стент</option>
            <option value="catheter">Катетер</option>
            <option value="nephrostomy">Нефростома</option>
          </select>
          <input className="input" placeholder="Метка (напр. «стент справа»)" value={form.device_label}
                 style={{ marginBottom: 8 }} onChange={(e) => setForm({ ...form, device_label: e.target.value })} />
          <div className="sub" style={{ marginBottom: 4 }}>Плановая замена/удаление (можно не указывать)</div>
          <input className="input" type="date" value={form.due_at} style={{ marginBottom: 8 }}
                 onChange={(e) => setForm({ ...form, due_at: e.target.value })} />
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn" onClick={() => setAdding(false)}>Отмена</button>
            <button className="btn pri" onClick={add}>Сохранить</button>
          </div>
        </div>
      )}

      {active.length === 0 && !adding && <div className="sub" style={{ marginBottom: 8 }}>Активных устройств нет.</div>}

      {active.map((d) => (
        <div key={d.id} className="card" style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 13.5, fontWeight: 500 }}>
            {KIND_RU[d.kind] || d.kind}{d.device_label ? ` · ${d.device_label}` : ""}
          </div>
          <div className="sub" style={{ marginTop: 2 }}>
            {d.due_at ? `Замена/удаление до ${d.due_at}` : "Срок не задан"}
            {d.installed_at ? ` · установлен ${d.installed_at}` : ""}
          </div>
          {!disabled && replaceOf !== d.id && (
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button className="btn sm" onClick={() => close(d)}>Снять</button>
              <button className="btn sm" onClick={() => { setReplaceOf(d.id); setRform({ device_label: "", due_at: "" }); }}>Заменить</button>
            </div>
          )}
          {replaceOf === d.id && (
            <div style={{ marginTop: 8 }}>
              <div className="sub" style={{ marginBottom: 4 }}>Новое устройство (тип тот же: {KIND_RU[d.kind]})</div>
              <input className="input" placeholder="Метка нового изделия" value={rform.device_label}
                     style={{ marginBottom: 8 }} onChange={(e) => setRform({ ...rform, device_label: e.target.value })} />
              <input className="input" type="date" value={rform.due_at} style={{ marginBottom: 8 }}
                     onChange={(e) => setRform({ ...rform, due_at: e.target.value })} />
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn" onClick={() => setReplaceOf(null)}>Отмена</button>
                <button className="btn pri" onClick={() => doReplace(d)}>Заменить</button>
              </div>
            </div>
          )}
        </div>
      ))}

      {closed.length > 0 && (
        <>
          <div className="sub" style={{ margin: "10px 0 6px" }}>История</div>
          {closed.map((d) => (
            <div key={d.id} className="row" style={{ opacity: 0.7 }}>
              <div>
                <div style={{ fontSize: 13 }}>{KIND_RU[d.kind] || d.kind}{d.device_label ? ` · ${d.device_label}` : ""}</div>
                <div className="sub" style={{ marginTop: 2 }}>
                  {ACTION_RU[d.closed_action] || "закрыт"}{d.closed_at ? ` ${d.closed_at}` : ""}
                </div>
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
