import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api";
import VoiceButton from "../components/VoiceButton";
import ProtocolTab from "../components/ProtocolTab";
import DevicesTab from "../components/DevicesTab";
import PrescriptionsTab from "../components/PrescriptionsTab";
import TrendChart from "../components/TrendChart";
import { Spinner } from "../components/Loading";
import Button from "../components/Button";
import { confirmAction } from "../lib/confirm";
import { loadLabels, plabel } from "../lib/params";
import Tip from "../components/Tip";
import { useTips } from "../lib/tips";

export default function PatientDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const fileRef = useRef(null);
  const [p, setP] = useState(null);
  const [tl, setTl] = useState({});
  const [pmeta, setPmeta] = useState({});
  useEffect(() => { api.paramMeta().then(setPmeta).catch(() => {}); }, []);
  const [obs, setObs] = useState(null);     // {code,name,value,unit,date,q} | null
  const [news, setNews] = useState(null);
  const [integrity, setIntegrity] = useState(null);
  const { show } = useTips();
  useEffect(() => { if (id) api.integrity(id).then(setIntegrity).catch(() => setIntegrity(null)); }, [id, tl]);
  useEffect(() => { if (integrity && integrity.count > 0) show("tip:integrity"); }, [integrity, show]);
  const [epForm, setEpForm] = useState(null);
  async function saveEpisode() {
    const b = { type: epForm.type, reason: epForm.reason, ward: epForm.ward,
                diagnosis_text: epForm.diagnosis_text,
                actual_admission_at: epForm.admission || null };
    await api.createEpisode(id, b);
    setEpForm(null); setEncs(await api.encounters(id).catch(() => []));
  }
  const [pdf, setPdf] = useState(null);   // {sections:Set, from, to} | null
  const SECTIONS = [["observations", "Показатели"], ["prescriptions", "Назначения"],
                    ["notes", "Заметки"], ["appointments", "Приёмы"], ["protocol", "Протокол"]];
  function openPdf() {
    setPdf({ sections: new Set(SECTIONS.map(([k]) => k)), from: "", to: "", busy: false });
  }
  function toggleSec(k) {
    const s = new Set(pdf.sections); s.has(k) ? s.delete(k) : s.add(k);
    setPdf({ ...pdf, sections: s });
  }
  async function downloadPdf() {
    setPdf({ ...pdf, busy: true });
    try {
      await api.exportPdf(id, { sections: [...pdf.sections], date_from: pdf.from, date_to: pdf.to });
      setPdf(null);
    } catch (e) { alert(e.message || "Ошибка"); setPdf({ ...pdf, busy: false }); }
  }
  useEffect(() => { if (id) api.whatsNew(id).then(setNews).catch(() => setNews(null)); }, [id, tl]);
  function openObs() {
    setObs({ code: "", name: "", value: "", unit: "", q: "",
             date: new Date().toISOString().slice(0, 10) });
  }
  async function saveObs() {
    if (!obs.code || obs.value === "") return;
    const body = {
      parameter_code: obs.code, value_num: parseFloat(String(obs.value).replace(",", ".")),
      unit: obs.unit, effective_date: obs.date, status: "confirmed",
    };
    try {
      await api.addObservation(id, body);
      setObs(null); setTl(await api.timeline(id));
    } catch (e) {
      if (e.status === 409 && e.detail?.ambiguous) {
        setEpPick({ episodes: e.detail.episodes, onPick: async (eid) => {
          await api.addObservation(id, body, eid); setObs(null); setEpPick(null); setTl(await api.timeline(id));
        } });
      } else throw e;
    }
  }
  const [safety, setSafety] = useState({ items: [], complete: true });
  const [notes, setNotes] = useState([]);
  const [tab, setTab] = useState("s");
  const [busy, setBusy] = useState("");
  const [showS, setShowS] = useState(false);
  const [lq, setLq] = useState("");
  const [activeEnc, setActiveEnc] = useState(null);
  const [encs, setEncs] = useState([]);
  const [openEnc, setOpenEnc] = useState(null);
  const [, setLabelTick] = useState(0);
  useEffect(() => { loadLabels().then(() => setLabelTick((t) => t + 1)); }, []);
  const [consent, setConsent] = useState({ consent_ok: true });
  const [consentOpen, setConsentOpen] = useState(false);
  const [rx, setRx] = useState(null);            // форма назначения | null
  const [noteDraft, setNoteDraft] = useState("");
  const [noteEdit, setNoteEdit] = useState(null);   // {id,text} | null
  const [patEdit, setPatEdit] = useState(null);
  async function savePatient() {
    await api.updatePatient(id, patEdit);
    setPatEdit(null); setP(await api.patient(id));
  }
  async function saveNoteEdit() {
    await api.editNote(id, noteEdit.id, noteEdit.text);
    setNoteEdit(null); setNotes(await api.notes(id));
  }
  async function removeNote(nid) {
    if (!(await confirmAction({ title: "Удалить заметку?", danger: true, confirmText: "Удалить" }))) return;
    await api.deleteNote(id, nid); setNotes(await api.notes(id));
  }
  async function noteToTask(n) {
    await api.noteToTask(id, n.id, "");
    alert("Создана задача из заметки — найдёте её в разделе «Задачи».");
  }

  function loadConsent() { if (id) api.consent(id).then(setConsent).catch(() => {}); }
  useEffect(() => { loadConsent(); }, [id]);
  const consentOk = consent.consent_ok !== false;
  async function revokeConsent() {
    if (!(await confirmAction({ title: "Отозвать согласие?", message: "Приём с этим пациентом будет заблокирован.", danger: true, confirmText: "Отозвать" }))) return;
    await api.revokeConsent(id); loadConsent();
  }
  const METHOD = { paper: "бумажный бланк", electronic: "электронно", remote: "удалённо" };

  useEffect(() => { if (id) api.activeEncounter(id).then(setActiveEnc).catch(() => {}); }, [id]);
  useEffect(() => { if (id && tab === "v") api.encounters(id).then(setEncs).catch(() => setEncs([])); }, [id, tab]);

  async function closeVisit() {
    if (!activeEnc) return;
    await api.closeEncounter(activeEnc.id);
    setActiveEnc(null);
  }
  async function toggleEnc(e) {
    if (openEnc?.id === e.id) { setOpenEnc(null); return; }
    setOpenEnc(await api.encounter(e.id));
  }

  async function loadAll() {
    setP(await api.patient(id));
    setTl(await api.timeline(id));
    setSafety(await api.safety(id));
    setNotes(await api.notes(id));
  }
  useEffect(() => { loadAll(); }, [id]);

  const pending = Object.entries(tl).flatMap(([code, arr]) =>
    arr.filter((x) => x.status === "pending").map((x) => ({ code, ...x }))
  );

  async function submitRx(overrideReason) {
    const body = { drug_name: rx.drug, dose: rx.dose };
    if (overrideReason) body.override_reason = overrideReason;
    const res = await api.prescribe(id, body);
    if (res.conflict && !res.saved) {
      setRx({ ...rx, warn: res });     // показать предупреждение + поле причины
      return;
    }
    setRx(null);
    load();
  }

  async function uploadDoc(e) {
    const file = e.target.files?.[0] || null;
    setBusy("Распознаю…");
    const r = await api.uploadDocument(id, file);
    setBusy("");
    e.target.value = "";
    if (r._error) {
      alert(r._status === 429 ? r.detail : "Не удалось распознать документ. " + (r.detail || ""));
      return;
    }
    if (r.match_status !== "ok") {
      alert(`Проверка документа: данные не совпадают (${r.match_status}).\nВ документе: ${r.extracted_name} ${r.extracted_dob}.\nДокумент не приложен.`);
    } else {
      alert(`Распознано значений: ${r.pending_values.length}. Ожидают подтверждения.`);
      setTl(await api.timeline(id));
    }
  }

  async function confirmObs(oid) {
    await api.confirmObs(oid);
    setTl(await api.timeline(id));
  }

  async function voiceNote(blob) {
    setBusy("Расшифровываю…");
    await api.transcribe(id, blob);
    setBusy("");
    setNotes(await api.notes(id));
    setTab("n");
  }

  async function typedNote() {
    const t = noteDraft.trim();
    if (!t) return;
    try {
      await api.addNote(id, t);
      setNoteDraft(""); setNotes(await api.notes(id));
    } catch (e) {
      if (e.status === 409 && e.detail?.ambiguous) {
        setEpPick({ episodes: e.detail.episodes, onPick: async (eid) => {
          await api.addNoteToEpisode(id, t, eid); setNoteDraft(""); setEpPick(null); setNotes(await api.notes(id));
        } });
      } else throw e;
    }
  }
  const [epPick, setEpPick] = useState(null);

  if (!p) return <Spinner label="Загружаю карту…" />;

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{p.short_name}</div>
          <div className="sub">{[p.age && p.age + " лет", p.diagnosis_code, p.diagnosis_text].filter(Boolean).join(" · ")}</div>
        </div>
        <i className="ti ti-file-download act" style={{ marginRight: 12 }} title="Выписка (PDF)" onClick={openPdf} />
        <i className="ti ti-pencil act" style={{ marginRight: 12 }} title="Изменить данные пациента"
          onClick={() => setPatEdit({ last_name: p.last_name, first_name: p.first_name, middle_name: p.middle_name || "", birth_date: p.birth_date || "", phone: p.phone || "" })} />
        <i className={"ti ti-search act"} onClick={() => setShowS(!showS)} title="Поиск по карте" />
      </div>

      {patEdit && (
        <div className="card" style={{ marginBottom: 10 }}>
          <div className="sec-label" style={{ marginTop: 0 }}>Данные пациента</div>
          <input className="input" placeholder="Фамилия" value={patEdit.last_name} onChange={(e) => setPatEdit({ ...patEdit, last_name: e.target.value })} style={{ marginBottom: 8 }} />
          <input className="input" placeholder="Имя" value={patEdit.first_name} onChange={(e) => setPatEdit({ ...patEdit, first_name: e.target.value })} style={{ marginBottom: 8 }} />
          <input className="input" placeholder="Отчество" value={patEdit.middle_name} onChange={(e) => setPatEdit({ ...patEdit, middle_name: e.target.value })} style={{ marginBottom: 8 }} />
          <input className="input" type="date" value={patEdit.birth_date || ""} onChange={(e) => setPatEdit({ ...patEdit, birth_date: e.target.value })} style={{ marginBottom: 8 }} />
          <input className="input" placeholder="Телефон" value={patEdit.phone} onChange={(e) => setPatEdit({ ...patEdit, phone: e.target.value })} style={{ marginBottom: 8 }} />
          <div className="btnrow">
            <button className="btn sm" style={{ flex: 1 }} onClick={() => setPatEdit(null)}>Отмена</button>
            <Button className="btn pri sm" style={{ flex: 1 }} onClick={savePatient}>Сохранить</Button>
          </div>
        </div>
      )}

      {showS && (
        <div className="input" style={{ display: "flex", alignItems: "center", gap: 8, margin: "4px 0 12px" }}>
          <i className="ti ti-search muted" />
          <input autoFocus value={lq} onChange={(e) => setLq(e.target.value)} placeholder="Поиск по карте пациента…"
            style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)" }} />
          {lq && <i className="ti ti-x muted" style={{ cursor: "pointer" }} onClick={() => setLq("")} />}
        </div>
      )}

      {lq.trim() && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="sub" style={{ fontWeight: 500, marginBottom: 6 }}>Найдено в карте</div>
          {localResults(tl, notes, lq).length === 0 && <div className="sub">Ничего не найдено.</div>}
          {localResults(tl, notes, lq).map((r, i) => (
            <div key={i} className="row">
              <div>
                <div style={{ fontSize: 13 }}>{r.title}</div>
                <div className="sub">{r.meta}</div>
              </div>
              <i className={"ti " + r.icon + " muted"} />
            </div>
          ))}
        </div>
      )}

      {!safety.complete && (
        <div className="banner b-dn"><i className="ti ti-alert-circle" /> Блок безопасности не завершён</div>
      )}
      {pending.length > 0 && (
        <div className="banner b-wn" onClick={() => setTab("s")}>
          <i className="ti ti-file-search" /> {pending.length} значение(ий) ожидает проверки
        </div>
      )}
      {busy && <div className="banner b-ac"><i className="ti ti-loader-2" /> {busy}</div>}

      {activeEnc && (
        <div className="banner b-ac" style={{ cursor: "default", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span><i className="ti ti-player-record-filled rmc" /> Идёт приём — записи привязываются к визиту</span>
          <span className="acc" style={{ cursor: "pointer", fontWeight: 500 }} onClick={closeVisit}>Завершить</span>
        </div>
      )}

      {!consentOk && (
        <div className="banner b-dn" style={{ cursor: "default", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span><i className="ti ti-shield-x" /> Согласие на обработку ПДн не получено — приём вести нельзя</span>
          <span style={{ cursor: "pointer", fontWeight: 600, textDecoration: "underline" }} onClick={() => setConsentOpen(true)}>Оформить</span>
        </div>
      )}
      {consentOpen && (
        <ConsentGate id={id} patient={p} onDone={() => { setConsentOpen(false); loadConsent(); }} onClose={() => setConsentOpen(false)} />
      )}

      {pdf && (
        <div className="card" style={{ marginBottom: 10 }}>
          <div className="sec-label" style={{ marginTop: 0 }}>Выписка (PDF)</div>
          <div className="sub" style={{ marginBottom: 8 }}>Выберите разделы и, при желании, период.</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
            {SECTIONS.map(([k, label]) => (
              <span key={k} onClick={() => toggleSec(k)} style={{ padding: "5px 10px", borderRadius: 8, fontSize: 12.5, cursor: "pointer",
                background: pdf.sections.has(k) ? "var(--acbg)" : "var(--s1)",
                border: ".5px solid " + (pdf.sections.has(k) ? "var(--ac)" : "var(--bd)"),
                color: pdf.sections.has(k) ? "var(--ac)" : "var(--tp)" }}>
                {pdf.sections.has(k) ? "✓ " : ""}{label}
              </span>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, marginBottom: 10, alignItems: "center" }}>
            <span className="sub">период:</span>
            <input className="input" type="date" value={pdf.from} onChange={(e) => setPdf({ ...pdf, from: e.target.value })} style={{ flex: 1 }} />
            <span className="sub">—</span>
            <input className="input" type="date" value={pdf.to} onChange={(e) => setPdf({ ...pdf, to: e.target.value })} style={{ flex: 1 }} />
          </div>
          <div className="btnrow">
            <button className="btn sm" style={{ flex: 1 }} onClick={() => setPdf(null)}>Отмена</button>
            <button className="btn pri sm" style={{ flex: 1 }} disabled={pdf.busy || pdf.sections.size === 0} onClick={downloadPdf}>
              {pdf.busy ? "Формирую…" : "Скачать PDF"}
            </button>
          </div>
        </div>
      )}

      {integrity && integrity.count > 0 && (
        <div className="card" style={{ marginBottom: 10, borderLeft: "3px solid var(--wn)" }}>
          <Tip tipKey="tip:integrity" place="bottom" title="Система только подсказывает"
               text="«Проверка карты» отмечает несоответствия в данных — неверные даты, значения вне диапазона, недостающие единицы. Ничего не меняется автоматически: цвет показывает уровень (красный — ошибка, жёлтый — уточнение, серый — не хватает сведений), решение за вами.">
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
            <i className="ti ti-shield-check wn" /> Проверка карты — {integrity.count}
          </div>
          </Tip>
          {integrity.findings.map((f, i) => {
            const col = f.level === "D" ? "var(--dn)" : f.level === "Q" ? "var(--wn)" : "var(--tm)";
            const ic = f.level === "D" ? "ti-alert-triangle" : f.level === "Q" ? "ti-help-circle" : "ti-info-circle";
            return (
              <div key={i} className="row" style={{ alignItems: "flex-start" }}>
                <span style={{ fontSize: 12.5 }}>
                  <i className={"ti " + ic} style={{ color: col, marginRight: 4 }} />
                  {f.message}
                  {f.refs?.parameter && <span className="sub"> · {plabel(f.refs.parameter)}</span>}
                  {f.refs?.date && <span className="sub"> · {f.refs.date.split("-").reverse().join(".")}</span>}
                </span>
                <span className="sub mono" style={{ fontSize: 10 }}>{f.rule}</span>
              </div>
            );
          })}
          <div className="sub" style={{ marginTop: 4, fontSize: 11 }}>Система только подсказывает — решение за вами, ничего не изменено автоматически.</div>
        </div>
      )}

      {news && news.has_news && (
        <div className="card" style={{ marginBottom: 10, borderLeft: "3px solid var(--ac)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}><i className="ti ti-history acc" /> С прошлого раза</div>
            {news.last_activity && <div className="sub">активность: {news.last_activity.split("-").reverse().join(".")}</div>}
          </div>
          {news.overdue.map((o) => (
            <div key={o.id} className="row" style={{ cursor: "pointer" }} onClick={() => nav("/tasks")}>
              <span style={{ fontSize: 13 }}><i className="ti ti-clock-exclamation dng" /> Просрочено: {o.title}{o.days ? ` (на ${o.days} дн.)` : ""}</span>
              <i className="ti ti-chevron-right muted" />
            </div>
          ))}
          {news.alerts.map((a) => (
            <div key={a.code} className="row">
              <span style={{ fontSize: 13 }}><i className="ti ti-activity dng" /> {a.name} выше порога</span>
              <span className="mono dng">{a.value} {a.unit} <span className="sub">(&gt; {a.threshold})</span></span>
            </div>
          ))}
          {news.pending_count > 0 && (
            <div className="row" onClick={() => setTab("s")} style={{ cursor: "pointer" }}>
              <span style={{ fontSize: 13 }}><i className="ti ti-file-alert wn" /> {news.pending_count} распознанных значений ждут подтверждения</span>
            </div>
          )}
          {news.open_tasks > 0 && news.overdue.length === 0 && (
            <div className="row" onClick={() => nav("/tasks")} style={{ cursor: "pointer" }}>
              <span style={{ fontSize: 13 }}><i className="ti ti-checkbox muted" /> Открытых задач: {news.open_tasks}</span>
            </div>
          )}
        </div>
      )}

      {epPick && (
        <div className="modal-ov" onClick={() => setEpPick(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">К какому эпизоду отнести запись?</div>
            <div className="modal-msg">У пациента несколько открытых эпизодов — выберите нужный.</div>
            <div style={{ marginTop: 12 }}>
              {epPick.episodes.map((e) => (
                <div key={e.id} className="row" style={{ cursor: "pointer" }} onClick={() => epPick.onPick(e.id)}>
                  <span style={{ fontSize: 13 }}>
                    {e.type === "hospitalization" ? "🛏 Госпитализация" : "Приём"}
                    {e.ward ? ` · палата ${e.ward}` : ""}{e.reason ? ` · ${e.reason}` : ""}
                  </span>
                  <i className="ti ti-chevron-right muted" />
                </div>
              ))}
            </div>
            <button className="btn block" style={{ marginTop: 12 }} onClick={() => setEpPick(null)}>Отмена</button>
          </div>
        </div>
      )}

      <div className="tabs">
        <div className={"t" + (tab === "s" ? " on" : "")} onClick={() => setTab("s")}>Сводка</div>
        <div className={"t" + (tab === "p" ? " on" : "")} onClick={() => setTab("p")}>Протокол</div>
        <div className={"t" + (tab === "d" ? " on" : "")} onClick={() => setTab("d")}>Устройства</div>
        <div className={"t" + (tab === "rx" ? " on" : "")} onClick={() => setTab("rx")}>Назначения</div>
        <div className={"t" + (tab === "v" ? " on" : "")} onClick={() => setTab("v")}>Визиты</div>
        <div className={"t" + (tab === "n" ? " on" : "")} onClick={() => setTab("n")}>Заметки</div>
      </div>

      {tab === "p" && <ProtocolTab id={id} disabled={!consentOk} />}

      {tab === "d" && <DevicesTab id={id} disabled={!consentOk} />}

      {tab === "rx" && <PrescriptionsTab id={id} disabled={!consentOk} />}

      {tab === "v" && (
        <>
          <button className="btn sm" style={{ width: "100%", marginBottom: 10, opacity: consentOk ? 1 : 0.5 }}
            disabled={!consentOk} onClick={() => consentOk && setEpForm({ type: "hospitalization", reason: "", ward: "", admission: "", diagnosis_code: "", diagnosis_text: "" })}>
            <i className="ti ti-plus" /> Новый эпизод (госпитализация/приём)
          </button>
          {epForm && (
            <div className="card" style={{ marginBottom: 10 }}>
              <div className="sec-label" style={{ marginTop: 0 }}>Новый эпизод</div>
              <select className="input" value={epForm.type} onChange={(e) => setEpForm({ ...epForm, type: e.target.value })} style={{ marginBottom: 8 }}>
                <option value="hospitalization">Госпитализация</option>
                <option value="visit">Приём</option>
              </select>
              <input className="input" placeholder="Причина / повод" value={epForm.reason} onChange={(e) => setEpForm({ ...epForm, reason: e.target.value })} style={{ marginBottom: 8 }} />
              {epForm.type === "hospitalization" && (
                <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                  <input className="input" type="datetime-local" value={epForm.admission} onChange={(e) => setEpForm({ ...epForm, admission: e.target.value })} style={{ flex: 1 }} title="Поступление" />
                  <input className="input" placeholder="Палата" value={epForm.ward} onChange={(e) => setEpForm({ ...epForm, ward: e.target.value })} style={{ width: 90 }} />
                </div>
              )}
              <input className="input" placeholder="Диагноз эпизода (текст)" value={epForm.diagnosis_text} onChange={(e) => setEpForm({ ...epForm, diagnosis_text: e.target.value })} style={{ marginBottom: 8 }} />
              <div className="btnrow">
                <button className="btn sm" style={{ flex: 1 }} onClick={() => setEpForm(null)}>Отмена</button>
                <Button className="btn pri sm" style={{ flex: 1 }} onClick={saveEpisode}>Создать</Button>
              </div>
            </div>
          )}
          {encs.length === 0 && <div className="sub" style={{ marginTop: 8 }}>Эпизодов пока нет.</div>}
          {encs.map((e) => (
            <div key={e.id}>
              <div className="row" style={{ cursor: "pointer" }} onClick={() => toggleEnc(e)}>
                <div>
                  <div style={{ fontSize: 13.5 }}>
                    {e.type === "hospitalization" ? <><i className="ti ti-bed acc" /> Госпитализация</> : "Приём"}
                    {" · "}{new Date(e.started_at).toLocaleDateString("ru-RU")}
                    {e.status === "open" && <span className="rmc" style={{ fontSize: 11, marginLeft: 8 }}>идёт</span>}
                    {e.day_of_stay && <span className="acc" style={{ fontSize: 11, marginLeft: 8 }}>{e.day_of_stay}-й день</span>}
                  </div>
                  <div className="sub">
                    {[e.ward && "палата " + e.ward, e.diagnosis_text || e.reason, summaryText(e.summary)].filter(Boolean).join(" · ")}
                  </div>
                </div>
                <i className={"ti " + (openEnc?.id === e.id ? "ti-chevron-down" : "ti-chevron-right") + " muted"} />
              </div>
              {openEnc?.id === e.id && (
                <div className="card" style={{ marginBottom: 8 }}>
                  {openEnc.notes?.map((n) => (
                    <div key={"n" + n.id} className="row"><div style={{ fontSize: 13 }}><i className="ti ti-note muted" /> {n.text}</div></div>
                  ))}
                  {openEnc.observations?.map((o) => (
                    <div key={"o" + o.id} className="row"><div style={{ fontSize: 13 }}><i className="ti ti-activity muted" /> {o.parameter_code}: {o.value_num ?? o.value_text} {o.unit}</div></div>
                  ))}
                  {openEnc.prescriptions?.map((p) => (
                    <div key={"p" + p.id} className="row"><div style={{ fontSize: 13 }}><i className="ti ti-pill muted" /> {p.drug_name} {p.dose}</div></div>
                  ))}
                  {openEnc.documents?.map((d) => (
                    <div key={"d" + d.id} className="row"><div className="sub"><i className="ti ti-file muted" /> документ распознан</div></div>
                  ))}
                  {(!openEnc.notes?.length && !openEnc.observations?.length && !openEnc.prescriptions?.length && !openEnc.documents?.length) &&
                    <div className="sub">В этот визит записей не вносилось.</div>}
                </div>
              )}
            </div>
          ))}
        </>
      )}

      {tab === "s" && (
        <>
          <DiagnosesBlock id={id} disabled={!consentOk} onChange={() => api.patient(id).then(setP).catch(() => {})} />
          <div className="row">
            <div>
              <div style={{ fontSize: 13 }}>Согласие 152-ФЗ</div>
              {consentOk
                ? <div className="sub succ">получено · {METHOD[consent.method] || consent.method || "—"}{consent.verified ? " · ИИ ✓" : ""}</div>
                : <div className="sub dng">не получено — приём заблокирован</div>}
            </div>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <span className="acc" style={{ fontSize: 12, cursor: "pointer" }} onClick={() => setConsentOpen(true)}>{consentOk ? "изменить" : "оформить"}</span>
              {consentOk && <span className="dng" style={{ fontSize: 12, cursor: "pointer" }} onClick={revokeConsent}>отозвать</span>}
            </div>
          </div>
          {pending.length > 0 && (
            <>
              <div className="sec-label" style={{ marginTop: 0 }}>Требует подтверждения</div>
              {pending.map((x) => (
                <div key={x.id} className="row">
                  <div>
                    <div className="mono" style={{ fontSize: 14 }}>{plabel(x.code)}: {x.value_num} {x.unit}</div>
                    <div className="sub">{x.date}</div>
                  </div>
                  <button className="btn sm pri" onClick={() => confirmObs(x.id)}>Подтвердить</button>
                </div>
              ))}
            </>
          )}

          <div className="sec-label">Динамика</div>
          {(() => {
            const codes = Object.keys(tl).filter((code) =>
              (tl[code] || []).some((x) => x.value_num != null));
            if (codes.length === 0) return <div className="sub">Пока нет числовых показателей.</div>;
            // сначала ключевые урологические, потом остальные
            const order = ["psa_total", "psa_free_ratio", "prostate_volume", "qmax", "residual_urine", "creatinine"];
            codes.sort((a, b) => {
              const ia = order.indexOf(a), ib = order.indexOf(b);
              return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
            });
            return codes.map((code) => (
              <TrendChart key={code} label={plabel(code)}
                points={(tl[code] || []).filter((x) => x.status === "confirmed")}
                unit={(pmeta[code] || {}).unit || (tl[code][0] || {}).unit || ""}
                threshold={(pmeta[code] || {}).threshold || ""} />
            ));
          })()}

          <div className="btnrow">
            <button className="btn sm" style={{ flex: 1, opacity: consentOk ? 1 : 0.5 }} disabled={!consentOk}
              onClick={() => consentOk && setRx({ drug: "", dose: "", warn: null })}><i className="ti ti-pill" /> Назначить</button>
            <button className="btn sm" style={{ flex: 1, opacity: consentOk ? 1 : 0.5 }} disabled={!consentOk}
              onClick={() => consentOk && openObs()}><i className="ti ti-plus" /> Показатель</button>
            <button className="btn sm" style={{ flex: 1, opacity: consentOk ? 1 : 0.5 }} disabled={!consentOk}
              onClick={() => consentOk && fileRef.current.click()}><i className="ti ti-camera" /> Документ</button>
          </div>
          {!consentOk && <div className="sub dng" style={{ marginTop: 4 }}>Действия приёма недоступны без согласия пациента.</div>}
          <input type="file" ref={fileRef} accept="image/*,.pdf" style={{ display: "none" }} onChange={uploadDoc} />

          {obs && (
            <div className="card" style={{ marginTop: 8 }}>
              <div className="sec-label" style={{ marginTop: 0 }}>Новый показатель</div>
              {!obs.code ? (
                <>
                  <input className="input" autoFocus placeholder="Название показателя (напр. PSA)" value={obs.q}
                    onChange={(e) => setObs({ ...obs, q: e.target.value })} style={{ marginBottom: 6 }} />
                  <div style={{ maxHeight: 160, overflowY: "auto" }}>
                    {Object.entries(pmeta)
                      .filter(([, m]) => m.name.toLowerCase().includes(obs.q.toLowerCase()))
                      .slice(0, 8)
                      .map(([code, m]) => (
                        <div key={code} className="row" style={{ cursor: "pointer" }}
                          onClick={() => setObs({ ...obs, code, name: m.name, unit: m.unit })}>
                          <span style={{ fontSize: 13 }}>{m.name}</span>
                          <span className="sub">{m.unit}</span>
                        </div>
                      ))}
                  </div>
                </>
              ) : (
                <>
                  <div className="row" style={{ borderTop: 0 }}>
                    <span style={{ fontSize: 13.5, fontWeight: 500 }}>{obs.name}</span>
                    <span className="acc" style={{ fontSize: 12, cursor: "pointer" }} onClick={() => setObs({ ...obs, code: "", name: "" })}>изменить</span>
                  </div>
                  <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                    <input className="input" type="number" inputMode="decimal" autoFocus placeholder="Значение" value={obs.value}
                      onChange={(e) => setObs({ ...obs, value: e.target.value })} style={{ flex: 1 }} />
                    <input className="input" placeholder="ед." value={obs.unit}
                      onChange={(e) => setObs({ ...obs, unit: e.target.value })} style={{ width: 80 }} />
                  </div>
                  <input className="input" type="date" value={obs.date}
                    onChange={(e) => setObs({ ...obs, date: e.target.value })} style={{ marginBottom: 8 }} />
                  {pmeta[obs.code]?.threshold && <div className="sub" style={{ marginBottom: 8 }}>Порог: {pmeta[obs.code].threshold}</div>}
                </>
              )}
              <div className="btnrow">
                <button className="btn sm" style={{ flex: 1 }} onClick={() => setObs(null)}>Отмена</button>
                <Button className="btn pri sm" style={{ flex: 1 }} disabled={!obs.code || obs.value === ""} onClick={saveObs}>Сохранить</Button>
              </div>
            </div>
          )}

          {rx && (
            <div className="card" style={{ marginTop: 8 }}>
              <div className="sec-label" style={{ marginTop: 0 }}>Новое назначение</div>
              <input className="input" placeholder="Препарат (МНН или бренд)" value={rx.drug}
                onChange={(e) => setRx({ ...rx, drug: e.target.value, warn: null })} style={{ marginBottom: 8 }} />
              <input className="input" placeholder="Доза и режим (напр. 0.4 мг на ночь)" value={rx.dose}
                onChange={(e) => setRx({ ...rx, dose: e.target.value })} style={{ marginBottom: 8 }} />
              {rx.warn && (
                <div className="banner b-dn" style={{ cursor: "default", display: "block" }}>
                  <div><i className="ti ti-alert-triangle" /> {rx.warn.message}</div>
                  {rx.warn.cross_rule && <div className="sub" style={{ marginTop: 4 }}>Перекрёстно: {rx.warn.cross_rule}</div>}
                  {rx.warn.phenotype && <div className="sub">Реакции: {rx.warn.phenotype}</div>}
                  <div className="sub" style={{ marginTop: 6 }}>Система не запрещает — решение за вами. Укажите причину:</div>
                  <input className="input" placeholder="Причина назначения при конфликте" value={rx.reason || ""}
                    onChange={(e) => setRx({ ...rx, reason: e.target.value })} style={{ marginTop: 6 }} />
                </div>
              )}
              <div className="btnrow" style={{ marginTop: 8 }}>
                <button className="btn sm" style={{ flex: 1 }} onClick={() => setRx(null)}>Отмена</button>
                {rx.warn ? (
                  <Button className="btn pri sm" style={{ flex: 1 }} disabled={!rx.reason} onClick={() => submitRx(rx.reason)}>Назначить с причиной</Button>
                ) : (
                  <Button className="btn pri sm" style={{ flex: 1 }} disabled={!rx.drug.trim()} onClick={() => submitRx()}>Назначить</Button>
                )}
              </div>
            </div>
          )}

          <PrivacyBlock id={id} nav={nav} />
        </>
      )}

      {tab === "n" && (
        <>
          {!consentOk && <div className="banner b-dn" style={{ cursor: "default" }}><i className="ti ti-shield-x" /> Заметки недоступны без согласия пациента</div>}
          <div className="btnrow" style={{ marginTop: 0, opacity: consentOk ? 1 : 0.5, pointerEvents: consentOk ? "auto" : "none" }}>
            <VoiceButton onResult={voiceNote} label="Заметка голосом" />
          </div>
          <div className="input" style={{ display: "flex", alignItems: "flex-end", gap: 8, marginTop: 8, opacity: consentOk ? 1 : 0.5 }}>
            <textarea value={noteDraft} onChange={(e) => setNoteDraft(e.target.value)} rows={1} disabled={!consentOk}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); typedNote(); } }}
              placeholder="Новая заметка…"
              style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)", resize: "none", maxHeight: 96 }} />
            <i className="ti ti-send acc" style={{ fontSize: 20, cursor: "pointer", opacity: noteDraft.trim() && consentOk ? 1 : 0.4 }} onClick={() => consentOk && typedNote()} />
          </div>
          {notes.length === 0 && <div className="sub" style={{ marginTop: 14 }}>Заметок пока нет.</div>}
          {notes.map((n) => (
            <div key={n.id} className="card" style={{ marginTop: 10 }}>
              <div className="sub" style={{ marginBottom: 6, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span>
                  <i className={"ti " + (n.source === "voice" ? "ti-microphone" : "ti-pencil")} style={{ fontSize: 12 }} />{" "}
                  {new Date(n.created_at).toLocaleString("ru-RU")}
                </span>
                {consentOk && (
                  <span style={{ display: "flex", gap: 12 }}>
                    <i className="ti ti-edit muted" title="Редактировать" style={{ cursor: "pointer" }} onClick={() => setNoteEdit({ id: n.id, text: n.text })} />
                    <i className="ti ti-subtask acc" title="Сделать задачу" style={{ cursor: "pointer" }} onClick={() => noteToTask(n)} />
                    <i className="ti ti-trash dng" title="Удалить" style={{ cursor: "pointer" }} onClick={() => removeNote(n.id)} />
                  </span>
                )}
              </div>
              {noteEdit?.id === n.id ? (
                <>
                  <textarea className="input" value={noteEdit.text} onChange={(e) => setNoteEdit({ ...noteEdit, text: e.target.value })}
                    style={{ minHeight: 60 }} />                  <div className="btnrow" style={{ marginTop: 8 }}>
                    <button className="btn sm" style={{ flex: 1 }} onClick={() => setNoteEdit(null)}>Отмена</button>
                    <Button className="btn pri sm" style={{ flex: 1 }} onClick={saveNoteEdit}>Сохранить</Button>
                  </div>
                </>
              ) : (
                <div style={{ fontSize: 13, lineHeight: 1.6 }}>{n.text}</div>
              )}
            </div>
          ))}
        </>
      )}
    </>
  );
}


function DiagnosesBlock({ id, onChange, disabled }) {
  const [list, setList] = useState([]);
  const [adding, setAdding] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState([]);
  const [showRemoved, setShowRemoved] = useState(false);

  function load() { api.diagnoses(id).then(setList).catch(() => setList([])); }
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    if (!adding) return;
    const t = setTimeout(() => { if (q.trim()) api.searchIcd(q.trim()).then((r) => setHits(r.items || [])); else setHits([]); }, 200);
    return () => clearTimeout(t);
  }, [q, adding]);

  async function pick(x) {
    await api.addDiagnosis(id, { code: x.code, title: x.title });
    setAdding(false); setQ(""); setHits([]); load(); onChange && onChange();
  }
  async function makePrimary(did) { await api.setPrimaryDiagnosis(id, did); load(); onChange && onChange(); }
  async function remove(did) { if (await confirmAction({ title: "Снять диагноз?", message: "Останется в истории.", confirmText: "Снять" })) { await api.removeDiagnosis(id, did); load(); onChange && onChange(); } }

  const active = list.filter((d) => d.status === "active");
  const removed = list.filter((d) => d.status === "removed");

  return (
    <>
      <div className="sec-label" style={{ marginTop: 0, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>Диагнозы</span>
        {!disabled && (
          <span className="acc" style={{ fontSize: 12, cursor: "pointer" }} onClick={() => setAdding(!adding)}>
            <i className="ti ti-plus" /> добавить
          </span>
        )}
      </div>

      {adding && (
        <div className="card" style={{ marginBottom: 8 }}>
          <div className="input" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <i className="ti ti-search muted" />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Код или название по МКБ-10 (напр. N40)…"
              style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)" }} />
          </div>
          {hits.map((x) => (
            <div key={x.code} className="row" style={{ cursor: "pointer" }} onClick={() => pick(x)}>
              <div><span className="mono acc">{x.code}</span> <span style={{ fontSize: 13 }}>{x.title}</span></div>
              <i className="ti ti-plus muted" />
            </div>
          ))}
          {q && hits.length === 0 && <div className="sub" style={{ marginTop: 6 }}>Ничего не найдено в урологическом срезе МКБ.</div>}
        </div>
      )}

      {active.length === 0 && <div className="sub">Диагнозы не указаны.</div>}
      {active.map((d) => (
        <div key={d.id} className="row">
          <div>
            <div style={{ fontSize: 13.5 }}>
              {d.is_primary && <i className="ti ti-star-filled" style={{ color: "var(--wn)", fontSize: 12, marginRight: 5 }} />}
              <span className="mono acc">{d.code}</span> {d.wording || d.title}
            </div>
            {d.is_primary && <div className="sub">основной</div>}
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            {!d.is_primary && <i className="ti ti-star muted" title="Сделать основным" style={{ cursor: "pointer" }} onClick={() => makePrimary(d.id)} />}
            <i className="ti ti-x muted" title="Снять диагноз" style={{ cursor: "pointer" }} onClick={() => remove(d.id)} />
          </div>
        </div>
      ))}

      {removed.length > 0 && (
        <>
          <div className="sub" style={{ marginTop: 6, cursor: "pointer" }} onClick={() => setShowRemoved(!showRemoved)}>
            <i className={"ti " + (showRemoved ? "ti-chevron-down" : "ti-chevron-right")} style={{ fontSize: 12 }} /> История диагнозов ({removed.length})
          </div>
          {showRemoved && removed.map((d) => (
            <div key={d.id} className="row"><div className="sub" style={{ textDecoration: "line-through" }}><span className="mono">{d.code}</span> {d.wording || d.title}</div></div>
          ))}
        </>
      )}
    </>
  );
}

function summaryText(s) {
  if (!s) return "";
  const parts = [];
  if (s.observations) parts.push(`${s.observations} показ.`);
  if (s.notes) parts.push(`${s.notes} замет.`);
  if (s.prescriptions) parts.push(`${s.prescriptions} назнач.`);
  if (s.documents) parts.push(`${s.documents} докум.`);
  return parts.length ? parts.join(" · ") : "без записей";
}

function PrivacyBlock({ id, nav }) {
  async function doExport() {
    const data = await api.exportPatient(id);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `patient_${id}_export.json`; a.click();
    URL.revokeObjectURL(url);
  }
  async function doErase() {
    if (!(await confirmAction({ title: "Удалить все данные пациента?", message: "Безвозвратно, восстановить будет нельзя.", danger: true, confirmText: "Удалить всё" }))) return;
    await api.erasePatient(id);
    nav("/patients");
  }
  return (
    <>
      <div className="sec-label">Данные пациента (152-ФЗ)</div>
      <div className="row">
        <div style={{ fontSize: 13 }}>Экспорт данных пациента</div>
        <i className="ti ti-file-download acc" style={{ fontSize: 18, cursor: "pointer" }} onClick={doExport} />
      </div>
      <div className="row">
        <div style={{ fontSize: 13 }} className="dng">Удалить данные пациента</div>
        <i className="ti ti-trash dng" style={{ fontSize: 18, cursor: "pointer" }} onClick={doErase} />
      </div>
    </>
  );
}

// Барьер согласия: выбор способа → шаг способа. Без согласия приём вести нельзя.
function ConsentGate({ id, patient, onDone, onClose }) {
  const [step, setStep] = useState("choose");   // choose | paper | electronic | remote
  const [agreed, setAgreed] = useState(false);
  const [formText, setFormText] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => { api.consentForm(id).then((r) => setFormText(r.text)).catch(() => {}); }, [id]);

  async function paperPhoto(e) {
    const file = e.target.files?.[0]; if (!file) return;
    setBusy(true);
    const r = await api.consentPaper(id, file); setBusy(false);
    setResult(r);
    if (r.consent_ok) setTimeout(onDone, 1200);
  }
  async function electronic() {
    setBusy(true); const r = await api.consentElectronic(id); setBusy(false);
    if (r.consent_ok) onDone();
  }
  async function remote() {
    setBusy(true); const r = await api.consentRemote(id); setBusy(false);
    if (r.consent_ok) onDone();
  }
  function printForm() {
    const w = window.open("", "_blank");
    if (w) { w.document.write(`<pre style="font:14px/1.6 Golos Text,Arial;white-space:pre-wrap;padding:32px">${formText}</pre>`); w.document.close(); w.print(); }
  }

  return (
    <div className="card" style={{ marginBottom: 10, border: ".5px solid var(--ac)" }}>
      <div className="sec-label" style={{ marginTop: 0, display: "flex", justifyContent: "space-between" }}>
        <span>Согласие на обработку ПДн (152-ФЗ)</span>
        <i className="ti ti-x muted" style={{ cursor: "pointer" }} onClick={onClose} />
      </div>

      {step === "choose" && (
        <>
          <div className="sub" style={{ marginBottom: 8 }}>Выберите способ получения согласия:</div>
          {[["paper", "ti-file-text", "Бумажный бланк", "распечатать, подписать, сфотографировать"],
            ["electronic", "ti-device-tablet", "Электронно на устройстве", "пациент подписывает здесь"],
            ["remote", "ti-qrcode", "Удалённо (QR / SMS)", "пациент подписывает на своём телефоне"]].map(([m, ic, t, sub]) => (
            <div key={m} className="row" style={{ cursor: "pointer" }} onClick={() => setStep(m)}>
              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <i className={"ti " + ic + " acc"} style={{ fontSize: 18 }} />
                <div><div style={{ fontSize: 13.5 }}>{t}</div><div className="sub">{sub}</div></div>
              </div>
              <i className="ti ti-chevron-right muted" />
            </div>
          ))}
        </>
      )}

      {step === "paper" && (
        <>
          <i className="ti ti-arrow-left back" onClick={() => setStep("choose")} />
          <div className="sub" style={{ margin: "6px 0" }}>Выдайте пациенту наш бланк, соберите подпись, затем сфотографируйте. ИИ проверит корректность; хранится только распознанный текст, фото не сохраняется.</div>
          <button className="btn block" onClick={printForm} style={{ marginBottom: 8 }}><i className="ti ti-printer" /> Распечатать бланк</button>
          <button className="btn pri block" disabled={busy} onClick={() => fileRef.current.click()}>
            <i className="ti ti-camera" /> {busy ? "Проверяю…" : "Сфотографировать подписанный бланк"}
          </button>
          <input type="file" ref={fileRef} accept="image/*" style={{ display: "none" }} onChange={paperPhoto} />
          {result && (
            <div className={"banner " + (result.consent_ok ? "b-ac" : "b-dn")} style={{ marginTop: 10, cursor: "default", display: "block" }}>
              <div><i className={"ti " + (result.consent_ok ? "ti-circle-check" : "ti-alert-triangle")} /> {result.consent_ok ? "Согласие подтверждено ИИ" : "Бланк не прошёл проверку"}</div>
              <div className="sub" style={{ marginTop: 4 }}>{result.verify_note}</div>
            </div>
          )}
        </>
      )}

      {step === "electronic" && (
        <>
          <i className="ti ti-arrow-left back" onClick={() => setStep("choose")} />
          <div className="card" style={{ maxHeight: 160, overflowY: "auto", fontSize: 12, margin: "8px 0", background: "var(--s1)" }}>{formText}</div>
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 13, marginBottom: 10, cursor: "pointer" }}>
            <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} style={{ marginTop: 2 }} />
            Пациент ознакомлен с текстом и даёт согласие на обработку персональных данных
          </label>
          <button className="btn pri block" disabled={!agreed || busy} onClick={electronic}><i className="ti ti-signature" /> Подписать согласие</button>
        </>
      )}

      {step === "remote" && (
        <>
          <i className="ti ti-arrow-left back" onClick={() => setStep("choose")} />
          <div className="sub" style={{ margin: "6px 0" }}>Покажите пациенту QR-код или отправьте ссылку — он подпишет согласие на своём телефоне.</div>
          <div style={{ textAlign: "center", padding: 16 }}><i className="ti ti-qrcode" style={{ fontSize: 96, color: "var(--tp)" }} /></div>
          <button className="btn pri block" disabled={busy} onClick={remote}><i className="ti ti-check" /> Пациент подписал</button>
        </>
      )}
    </div>
  );
}

function localResults(tl, notes, q) {
  const s = q.trim().toLowerCase();
  const out = [];
  for (const [code, arr] of Object.entries(tl || {})) {
    const name = plabel(code).toLowerCase();
    if (name.includes(s) || code.includes(s)) {
      for (const x of arr) {
        out.push({ title: `${plabel(code)}: ${x.value_num ?? x.value_text} ${x.unit || ""}`, meta: x.date || "", icon: "ti-activity" });
      }
    }
  }
  for (const n of notes || []) {
    if ((n.text || "").toLowerCase().includes(s)) {
      out.push({ title: n.text, meta: new Date(n.created_at).toLocaleDateString("ru-RU"), icon: "ti-note" });
    }
  }
  return out;
}
