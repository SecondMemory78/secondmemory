import { useEffect, useState } from "react";
import { api } from "../api";
import { fmtDate } from "../lib/dates";
import { toast } from "../lib/toast";
import { confirmAction } from "../lib/confirm";
import VoiceButton from "./VoiceButton";

// Категории из спецификации модуля «Назначения»: одна сущность и для лекарств,
// и для режима/контроля/ограничений.
const CATEGORIES = [
  ["drug", "Препарат"],
  ["fluid", "Питьевой режим"],
  ["diet", "Питание"],
  ["activity", "Активность"],
  ["care", "Уход"],
  ["selfcontrol", "Самоконтроль"],
  ["lab", "Анализы"],
  ["imaging", "Исследование"],
  ["procedure", "Процедура"],
  ["restriction", "Ограничение"],
  ["followup", "Повторный осмотр"],
  ["other", "Другое"],
];
const CAT = Object.fromEntries(CATEGORIES);

const FILTERS = [
  ["active", "Активные"],
  ["drug", "Медикаменты"],
  ["control", "Контроль"],
  ["regimen", "Режим"],
  ["done", "Завершённые"],
];

const SOURCE_RU = {
  doctor: "", document: "из документа", other_specialist: "другой специалист",
  patient_words: "со слов пациента", ai_extracted: "извлечено ИИ",
  ai_suggested: "предложение ИИ",
};

const EMPTY = {
  drug_name: "", dose: "", category: "drug", indication: "", instruction: "",
  route: "", frequency: "", duration: "", control: "", control_date: "",
  priority: "normal",
};

export default function PrescriptionsTab({ id, disabled }) {
  const [items, setItems] = useState(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [conflict, setConflict] = useState(null);
  const [override, setOverride] = useState("");
  const [filter, setFilter] = useState("active");
  const [open, setOpen] = useState(null);          // раскрытая карточка
  const [history, setHistory] = useState({});      // id -> история изменений
  const [dict, setDict] = useState(null);          // предпросмотр диктовки
  const [dictText, setDictText] = useState("");
  const [picked, setPicked] = useState({});        // какие записи сохранять
  const [busy, setBusy] = useState(false);

  function load() { api.prescriptions(id).then((r) => setItems(r.items)).catch(() => setItems([])); }
  useEffect(() => { load(); }, [id]);

  async function save(withOverride) {
    const body = { ...form, drug_name: form.drug_name.trim() };
    if (!body.control_date) delete body.control_date;
    if (withOverride) body.override_reason = override.trim();
    if (!body.drug_name) return;
    const r = await api.prescribe(id, body).catch(() => null);
    if (!r) return toast("Не удалось сохранить назначение", "error");
    if (r.conflict && !r.saved) { setConflict(r); return; }   // предупреждаем, не блокируем
    setAdding(false); setConflict(null); setOverride(""); setForm(EMPTY);
    load();
  }

  // Диктовка нескольких назначений: показываем разбор, сохраняем только
  // отмеченные. Всё идёт как предложение ИИ — активным станет после врача.
  async function dictate(opts) {
    setBusy(true); setDict(null);
    try {
      const r = await api.dictatePrescriptions(id, opts);
      setDict(r);
      setPicked(Object.fromEntries(r.items.map((_, i) => [i, true])));
    } catch (e) {
      toast(e.detail || "Не удалось разобрать диктовку", "error");
    } finally { setBusy(false); }
  }

  async function saveDictated() {
    const chosen = dict.items.filter((_, i) => picked[i]);
    if (!chosen.length) return;
    setBusy(true);
    try {
      for (const it of chosen) {
        await api.prescribe(id, { ...it, source: "ai_suggested" }).catch(() => null);
      }
      setDict(null); setDictText(""); load();
      toast(`Добавлено предложений: ${chosen.length}. Подтвердите нужные.`, "success");
    } finally { setBusy(false); }
  }

  async function confirm(rx) {
    await api.confirmPrescription(id, rx.id).catch(() => toast("Не удалось подтвердить", "error"));
    load();
  }

  async function cancel(rx) {
    if (!(await confirmAction({ title: "Отменить назначение?", danger: true,
                                confirmText: "Отменить" }))) return;
    await api.updatePrescription(id, rx.id, { status: "cancelled", reason: "отменено врачом" })
      .catch(() => toast("Не удалось отменить", "error"));
    load();
  }

  async function complete(rx) {
    await api.updatePrescription(id, rx.id, { status: "done", reason: "выполнено" })
      .catch(() => toast("Не удалось отметить", "error"));
    load();
  }

  async function showHistory(rx) {
    if (history[rx.id]) { setHistory({ ...history, [rx.id]: null }); return; }
    const h = await api.prescriptionHistory(id, rx.id).catch(() => ({ items: [] }));
    setHistory({ ...history, [rx.id]: h.items });
  }

  if (items === null) return <div className="sub">Загрузка назначений…</div>;

  const shown = items.filter((x) => {
    if (filter === "active") return x.status === "active" || x.status === "planned";
    if (filter === "drug") return x.category === "drug" && x.status !== "cancelled";
    if (filter === "control") return ["lab", "imaging", "selfcontrol", "followup"].includes(x.category);
    if (filter === "regimen") return ["fluid", "diet", "activity", "care", "restriction"].includes(x.category);
    return x.status === "done" || x.status === "cancelled";
  });

  return (
    <div>
      <div className="tabs" style={{ marginTop: 0 }}>
        {FILTERS.map(([k, label]) => (
          <div key={k} className={"t" + (filter === k ? " on" : "")} onClick={() => setFilter(k)}>{label}</div>
        ))}
      </div>

      {!adding && (
        <button className="btn pri block" disabled={disabled} onClick={() => setAdding(true)}
                style={{ marginBottom: 12 }}>
          <i className="ti ti-plus" /> Добавить назначение
        </button>
      )}

      {!adding && !dict && (
        <div className="card" style={{ marginBottom: 12, opacity: disabled ? 0.5 : 1 }}>
          <div className="sub" style={{ marginBottom: 8 }}>
            Продиктуйте несколько назначений подряд — разберу на отдельные записи
            и покажу состав. Ничего не сохранится без вашего подтверждения.
          </div>
          <textarea className="input" rows={2} value={dictText} disabled={disabled || busy}
                    onChange={(e) => setDictText(e.target.value)}
                    placeholder="Напр.: тадалафил 5 мг раз в день месяц, питьевой режим до двух литров, контроль через месяц"
                    style={{ resize: "vertical", marginBottom: 8 }} />
          <div className="btnrow" style={{ marginTop: 0 }}>
            <button className="btn sm" style={{ flex: 1 }}
                    disabled={disabled || busy || !dictText.trim()}
                    onClick={() => dictate({ text: dictText })}>
              {busy ? "Разбираю…" : "Разобрать"}
            </button>
            {!disabled && <VoiceButton label="Продиктовать" onResult={(blob) => dictate({ blob })} />}
          </div>
        </div>
      )}

      {dict && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="sec-label" style={{ marginTop: 0 }}>
            Распознано назначений: {dict.items.length}
          </div>
          <div className="sub" style={{ marginBottom: 8 }}>
            {dict.source === "ии" ? "Разобрано ИИ" : "Разобрано по ключевым словам"} · {dict.status}
          </div>
          {dict.transcript && (
            <div className="sub" style={{ marginBottom: 8 }}>Распознано: «{dict.transcript}»</div>
          )}
          {dict.items.length === 0 && <div className="sub dng">Не удалось выделить назначения.</div>}

          {dict.items.map((it, i) => (
            <label key={i} className="row" style={{ alignItems: "flex-start", cursor: "pointer" }}>
              <div style={{ display: "flex", gap: 9 }}>
                <input type="checkbox" checked={!!picked[i]} style={{ marginTop: 3 }}
                       onChange={(e) => setPicked({ ...picked, [i]: e.target.checked })} />
                <div>
                  <div style={{ fontSize: 13.5 }}>{it.drug_name}{it.dose ? ` · ${it.dose}` : ""}</div>
                  <div className="sub">
                    {CAT[it.category] || it.category}
                    {it.frequency ? ` · ${it.frequency}` : ""}
                    {it.duration ? ` · ${it.duration}` : ""}
                  </div>
                </div>
              </div>
            </label>
          ))}

          <div className="btnrow">
            <button className="btn sm" style={{ flex: 1 }} onClick={() => { setDict(null); setDictText(""); }}>
              Отмена
            </button>
            <button className="btn pri sm" style={{ flex: 1 }} disabled={busy || !dict.items.length}
                    onClick={saveDictated}>
              Добавить отмеченные
            </button>
          </div>
          <div className="sub" style={{ marginTop: 6 }}>
            Записи добавятся как предложения — станут действующими после вашего подтверждения.
          </div>
        </div>
      )}

      {adding && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="sec-label" style={{ marginTop: 0 }}>Новое назначение</div>

          <select className="input" value={form.category} style={{ marginBottom: 8 }}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}>
            {CATEGORIES.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>

          <input className="input" style={{ marginBottom: 8 }} value={form.drug_name}
                 placeholder={form.category === "drug" ? "Препарат (МНН или бренд)" : "Что назначено"}
                 onChange={(e) => setForm({ ...form, drug_name: e.target.value })} />

          {form.category === "drug" && (
            <>
              <input className="input" style={{ marginBottom: 8 }} value={form.dose}
                     placeholder="Доза (напр. 0.4 мг)"
                     onChange={(e) => setForm({ ...form, dose: e.target.value })} />
              <input className="input" style={{ marginBottom: 8 }} value={form.route}
                     placeholder="Путь введения (внутрь, в/м, местно)"
                     onChange={(e) => setForm({ ...form, route: e.target.value })} />
            </>
          )}

          <input className="input" style={{ marginBottom: 8 }} value={form.indication}
                 placeholder="Зачем — показание"
                 onChange={(e) => setForm({ ...form, indication: e.target.value })} />
          <input className="input" style={{ marginBottom: 8 }} value={form.instruction}
                 placeholder="Как выполнять"
                 onChange={(e) => setForm({ ...form, instruction: e.target.value })} />
          <input className="input" style={{ marginBottom: 8 }} value={form.frequency}
                 placeholder="Как часто (1 раз/сут, по требованию)"
                 onChange={(e) => setForm({ ...form, frequency: e.target.value })} />
          <input className="input" style={{ marginBottom: 8 }} value={form.duration}
                 placeholder="Как долго (30 дней, постоянно)"
                 onChange={(e) => setForm({ ...form, duration: e.target.value })} />
          <input className="input" style={{ marginBottom: 8 }} value={form.control}
                 placeholder="Чем контролировать результат"
                 onChange={(e) => setForm({ ...form, control: e.target.value })} />
          <div className="sub" style={{ marginBottom: 4 }}>Контрольная дата</div>
          <input className="input" type="date" style={{ marginBottom: 8 }} value={form.control_date}
                 onChange={(e) => setForm({ ...form, control_date: e.target.value })} />

          {conflict && (
            <div className="banner b-dn" style={{ display: "block", marginBottom: 8 }}>
              <div style={{ fontSize: 13 }}><i className="ti ti-alert-triangle" /> {conflict.message}</div>
              <div className="sub" style={{ marginTop: 4 }}>
                Система не запрещает — укажите причину, если назначаете осознанно.
              </div>
              <input className="input" style={{ marginTop: 8 }} value={override}
                     placeholder="Причина назначения вопреки предупреждению"
                     onChange={(e) => setOverride(e.target.value)} />
            </div>
          )}

          <div className="btnrow">
            <button className="btn sm" style={{ flex: 1 }}
                    onClick={() => { setAdding(false); setConflict(null); setForm(EMPTY); }}>
              Отмена
            </button>
            <button className="btn pri sm" style={{ flex: 1 }} disabled={!form.drug_name.trim()}
                    onClick={() => save(!!conflict)}>
              {conflict ? "Всё равно назначить" : "Назначить"}
            </button>
          </div>
        </div>
      )}

      {shown.length === 0 && <div className="sub">В этом разделе пусто.</div>}

      {shown.map((rx) => (
        <div key={rx.id} className="card" style={{ marginBottom: 8,
             borderLeft: rx.confirmed ? undefined : "3px solid var(--wn)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13.5, fontWeight: 500 }}>
                {rx.drug_name}{rx.dose ? ` · ${rx.dose}` : ""}
              </div>
              <div className="sub" style={{ marginTop: 2 }}>
                {CAT[rx.category] || rx.category}
                {rx.frequency ? ` · ${rx.frequency}` : ""}
                {rx.duration ? ` · ${rx.duration}` : ""}
                {rx.status === "cancelled" && " · отменено"}
                {rx.status === "done" && " · выполнено"}
              </div>
              {!rx.confirmed && (
                <div className="sub wn" style={{ marginTop: 2 }}>
                  {SOURCE_RU[rx.source] || "требует подтверждения"} — не действует, пока не подтвердите
                </div>
              )}
            </div>
            <i className={"ti " + (open === rx.id ? "ti-chevron-up" : "ti-chevron-down") + " muted"}
               style={{ cursor: "pointer" }} onClick={() => setOpen(open === rx.id ? null : rx.id)} />
          </div>

          {open === rx.id && (
            <div style={{ marginTop: 8 }}>
              {rx.indication && <div className="row"><span className="sub">Зачем</span><span style={{ fontSize: 12.5 }}>{rx.indication}</span></div>}
              {rx.instruction && <div className="row"><span className="sub">Как</span><span style={{ fontSize: 12.5 }}>{rx.instruction}</span></div>}
              {rx.route && <div className="row"><span className="sub">Путь</span><span style={{ fontSize: 12.5 }}>{rx.route}</span></div>}
              {rx.control && <div className="row"><span className="sub">Контроль</span><span style={{ fontSize: 12.5 }}>{rx.control}</span></div>}
              {rx.control_date && <div className="row"><span className="sub">Контрольная дата</span><span style={{ fontSize: 12.5 }}>{fmtDate(rx.control_date)}</span></div>}
              {rx.cancel_reason && <div className="row"><span className="sub">Причина отмены</span><span style={{ fontSize: 12.5 }}>{rx.cancel_reason}</span></div>}
              <div className="row"><span className="sub">Назначено</span><span style={{ fontSize: 12.5 }}>{fmtDate(rx.created_at)}</span></div>

              <div className="btnrow" style={{ marginTop: 8 }}>
                {!rx.confirmed && (
                  <button className="btn pri sm" style={{ flex: 1 }} disabled={disabled}
                          onClick={() => confirm(rx)}>Подтвердить</button>
                )}
                {rx.status === "active" && (
                  <button className="btn sm" style={{ flex: 1 }} disabled={disabled}
                          onClick={() => complete(rx)}>Выполнено</button>
                )}
                {rx.status !== "cancelled" && (
                  <button className="btn sm dng" style={{ flex: 1 }} disabled={disabled}
                          onClick={() => cancel(rx)}>Отменить</button>
                )}
              </div>

              <div className="acc" style={{ fontSize: 12, cursor: "pointer", marginTop: 8 }}
                   onClick={() => showHistory(rx)}>
                {history[rx.id] ? "скрыть историю" : "история изменений"}
              </div>
              {history[rx.id] && (
                history[rx.id].length === 0
                  ? <div className="sub" style={{ marginTop: 4 }}>Изменений не было.</div>
                  : history[rx.id].map((h) => (
                      <div key={h.id} className="sub" style={{ marginTop: 4 }}>
                        {fmtDate(h.changed_at)}{h.reason ? ` · ${h.reason}` : ""}
                      </div>
                    ))
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
