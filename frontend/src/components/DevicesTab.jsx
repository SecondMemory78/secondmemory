import { useEffect, useState } from "react";
import { api } from "../api";
import { toast } from "../lib/toast";
import { fmtDate } from "../lib/dates";
import SourceAnswer from "./SourceAnswer";

const KIND_RU = { catheter: "Катетер", stent: "Стент", nephrostomy: "Нефростома",
                  implant: "Имплант" };
const ACTION_RU = { removed: "удалён", replaced: "заменён" };

export default function DevicesTab({ id, disabled }) {
  const [items, setItems] = useState(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ kind: "stent", side: "", device_label: "", due_at: "" });
  const [replaceOf, setReplaceOf] = useState(null);   // id заменяемого
  const [rform, setRform] = useState({ device_label: "", due_at: "" });

  function load() { api.devices(id).then((r) => setItems(r.items)).catch(() => setItems([])); }
  useEffect(() => { load(); }, [id]);

  async function add() {
    const body = { kind: form.kind, side: form.side, device_label: form.device_label.trim(),
                   due_at: form.due_at || null };
    const r = await api.addDevice(id, body).catch(() => null);
    if (!r) return toast("Не удалось добавить устройство", "error");
    setAdding(false); setForm({ kind: "stent", side: "", device_label: "", due_at: "" });
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
          {/* Сторона отдельным полем, а не текстом в метке: перепутать бок —
              самая дорогая ошибка здесь, и в памятку сторона должна попадать
              как данные, а не как часть подписи. */}
          <label className="fld">
            <span>Сторона</span>
            <select className="input" value={form.side}
                    onChange={(e) => setForm({ ...form, side: e.target.value })}>
              <option value="">не применимо</option>
              <option value="left">слева</option>
              <option value="right">справа</option>
              <option value="both">с обеих сторон</option>
            </select>
          </label>
          <input className="input" placeholder="Метка: номер, партия (необязательно)" value={form.device_label}
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
            {KIND_RU[d.kind] || d.kind}{d.side_label ? ` ${d.side_label}` : ""}{d.device_label ? ` · ${d.device_label}` : ""}
          </div>
          <div className="sub" style={{ marginTop: 2 }}>
            {d.due_at ? `Замена/удаление до ${fmtDate(d.due_at)}` : "Срок не задан"}
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
                  {ACTION_RU[d.closed_action] || "закрыт"}{d.closed_at ? ` ${fmtDate(d.closed_at)}` : ""}
                </div>
              </div>
            </div>
          ))}
        </>
      )}

      <ImplantLookup patientId={id} onSaved={load} />
    </div>
  );
}

// Справка по имплантам и МР-совместимости. Допуск НЕ выдаётся — только
// что проверить и уточнить перед МРТ (см. services/implant_check.py).
function ImplantLookup({ patientId, onSaved }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [open, setOpen] = useState(false);
  const [ask, setAsk] = useState([]);       // что уточнить у пациента
  const [form, setForm] = useState(null);   // быстрая запись в карту

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) { setRes(null); return; }
    const t = setTimeout(() => {
      api.implantReference(term).then(setRes).catch(() => setRes(null));
      // вопросы по типу устройства — подсказка врачу прямо в момент работы
      api.implantQuestions(term).then((r) => setAsk(r.items || [])).catch(() => setAsk([]));
    }, 400);
    return () => clearTimeout(t);
  }, [q]);

  const MR_RU = { unknown: "МР-статус неизвестен", safe: "со слов: МРТ можно",
                  conditional: "со слов: МРТ с условиями", unsafe: "со слов: МРТ нельзя" };

  async function saveFromWords() {
    const label = form.label.trim();
    if (!label) return;
    const note = [form.model && `модель: ${form.model}`, MR_RU[form.mr]]
      .filter(Boolean).join(" · ");
    try {
      await api.addDevice(patientId, {
        kind: "implant",
        device_label: label,
        installed_at: form.since || null,
        // происхождение факта фиксируем в примечании: документом не подтверждено
        note: [note, "со слов пациента"].filter(Boolean).join(" · "),
      });
      setForm(null); onSaved && onSaved();
      toast("Записано со слов пациента", "success");
    } catch { toast("Не удалось записать", "error"); }
  }

  return (
    <>
      <div className="sec-label" style={{ cursor: "pointer" }} onClick={() => setOpen((v) => !v)}>
        Имплант и МРТ — справка
        <i className={"ti " + (open ? "ti-chevron-up" : "ti-chevron-down")} style={{ marginLeft: 6 }} />
      </div>
      {open && (
        <div>
          <div className="sub" style={{ marginBottom: 8 }}>
            Поиск по модели, артикулу или названию. Допуск к МРТ система не выдаёт —
            нужна точная модель, полная система и актуальная инструкция производителя.
          </div>
          <input className="input" placeholder="Напр. ACCOLADE, L310, кохлеарный" value={q}
                 onChange={(e) => setQ(e.target.value)} style={{ marginBottom: 8 }} />
          {res?.found && (
            <>
              <div className="banner" style={{ display: "block", background: "var(--wnbg)", color: "var(--tp)", marginBottom: 8 }}>
                <i className="ti ti-alert-triangle wn" /> {res.message}
              </div>
              {res.devices.slice(0, 4).map((d) => (
                <div key={d.id} className="card" style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 500 }}>{d.name_ru || d.family}</div>
                  <div className="sub" style={{ marginTop: 2 }}>
                    {[d.manufacturer, d.model, d.device_type].filter(Boolean).join(" · ")}
                  </div>
                  <div className="row" style={{ paddingBottom: 4 }}>
                    <span className="sub">МР-статус</span>
                    <span style={{ fontSize: 12.5 }}>{d.mr_status}{d.field ? ` · ${d.field}` : ""}</span>
                  </div>
                  {d.warning && <div className="sub" style={{ marginTop: 4 }}>{d.warning}</div>}
                  {d.clarify && <div className="sub" style={{ marginTop: 4 }}><b>Уточнить:</b> {d.clarify}</div>}
                  {d.rf_status && <div className="sub" style={{ marginTop: 4, opacity: 0.85 }}>РФ: {d.rf_status}</div>}
                  {d.source && <div className="sub" style={{ marginTop: 4, fontSize: 11, opacity: 0.8 }}>Источник: {d.source}</div>}
                </div>
              ))}
            </>
          )}
          {ask.length > 0 && (
            <div className="card" style={{ marginBottom: 8, background: "var(--s1)" }}>
              <div className="sub" style={{ marginBottom: 6 }}>
                Что уточнить у пациента (это вопросы, а не МР-статус — категория
                устройства статус не определяет)
              </div>
              {ask.map((a, i) => (
                <div key={i} className="row" style={{ alignItems: "flex-start" }}>
                  <div>
                    <div style={{ fontSize: 13 }}>{a.ask}</div>
                    {a.needed && <div className="sub" style={{ marginTop: 2 }}>{a.needed}</div>}
                    {a.document && <div className="sub" style={{ marginTop: 2 }}>Документ: {a.document}</div>}
                  </div>
                  <span className="sub" style={{ fontSize: 11 }}>{a.area}</span>
                </div>
              ))}
              {!form && (
                <button className="btn sm block" style={{ marginTop: 8 }}
                        onClick={() => setForm({ label: q.trim(), model: "", since: "",
                                                 mr: "unknown" })}>
                  Записать в карту со слов пациента
                </button>
              )}
            </div>
          )}

          {form && (
            <div className="card" style={{ marginBottom: 8 }}>
              <div className="sec-label" style={{ marginTop: 0 }}>Запись со слов пациента</div>
              <div className="sub" style={{ marginBottom: 8 }}>
                Сохраним как «со слов пациента» — это не подтверждённый документом факт.
              </div>
              <input className="input" style={{ marginBottom: 8 }} value={form.label}
                     placeholder="Устройство (как назвал пациент)"
                     onChange={(e) => setForm({ ...form, label: e.target.value })} />
              <input className="input" style={{ marginBottom: 8 }} value={form.model}
                     placeholder="Модель / производитель, если известны"
                     onChange={(e) => setForm({ ...form, model: e.target.value })} />
              <div className="sub" style={{ marginBottom: 4 }}>Дата установки</div>
              <input className="input" type="date" style={{ marginBottom: 8 }} value={form.since}
                     onChange={(e) => setForm({ ...form, since: e.target.value })} />
              <div className="sub" style={{ marginBottom: 4 }}>МР-совместимость со слов пациента</div>
              <select className="input" style={{ marginBottom: 8 }} value={form.mr}
                      onChange={(e) => setForm({ ...form, mr: e.target.value })}>
                <option value="unknown">неизвестно</option>
                <option value="safe">говорит, что можно МРТ</option>
                <option value="conditional">можно с условиями</option>
                <option value="unsafe">говорит, что нельзя</option>
              </select>
              <div className="btnrow">
                <button className="btn sm" style={{ flex: 1 }} onClick={() => setForm(null)}>Отмена</button>
                <button className="btn pri sm" style={{ flex: 1 }} disabled={!form.label.trim()}
                        onClick={saveFromWords}>Записать</button>
              </div>
            </div>
          )}

          {q.trim().length >= 2 && res && !res.found && (
            <>
              <div className="sub">Нет данных по этому запросу — это не означает «безопасно». Уточните по инструкции модели.</div>
              <SourceAnswer question={`${q.trim()} МРТ совместимость инструкция производителя`}
                            title="В источниках (наших данных нет)" />
            </>
          )}
        </div>
      )}
    </>
  );
}
