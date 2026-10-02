import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { toast } from "../lib/toast";
import DrawCanvas from "../components/DrawCanvas";
import PatientPicker from "../components/PatientPicker";

// Правка заметки.
//
// Отдельный экран, а не окно поверх списка: у окна нет своей кнопки «назад»,
// и черновик терялся при любом промахе мимо него.
//
// Сохранение автоматическое. Врач не должен думать про кнопку «сохранить»:
// он записывает мысль между пациентами и уходит, не дочитав экран.

const SAVE_AFTER_MS = 1200;      // пауза в наборе, после которой сохраняем

export default function NoteEdit() {
  const { id } = useParams();
  const nav = useNavigate();
  const isNew = id === "new";

  const [note, setNote] = useState(isNew
    ? { title: "", text: "", folder: "", checklist: [], pinned: false }
    : null);
  const [saved, setSaved] = useState(isNew ? "" : "сохранено");
  const [folders, setFolders] = useState([]);
  const [drawOpen, setDrawOpen] = useState(false);
  const [pickOpen, setPickOpen] = useState(false);
  const noteId = useRef(isNew ? null : Number(id));
  const timer = useRef(null);
  const dirty = useRef(false);

  useEffect(() => {
    api.noteFolders().then((r) => setFolders(r.items || [])).catch(() => {});
    if (isNew) return;
    api.myNote(Number(id))
      .then((n) => setNote({ ...n, title: n.title_raw || "" }))
      .catch(() => { toast("Заметка не найдена", "error"); nav("/notes"); });
  }, [id]);

  // Сохранение по паузе в наборе — и обязательно при уходе с экрана:
  // иначе последние набранные слова теряются.
  useEffect(() => () => { if (dirty.current) save(true); }, []);

  function change(patch) {
    setNote((n) => {
      const next = { ...n, ...patch };
      dirty.current = true;
      setSaved("…");
      clearTimeout(timer.current);
      timer.current = setTimeout(() => save(false, next), SAVE_AFTER_MS);
      return next;
    });
  }

  async function save(silent, snapshot) {
    const n = snapshot || note;
    if (!n) return;
    const empty = !n.text?.trim() && !n.title?.trim() && !(n.checklist || []).length;
    if (empty) { setSaved(""); return; }     // пустое не сохраняем и не ругаемся
    const body = {
      title: n.title || "", text: n.text || "", folder: n.folder || "",
      checklist: n.checklist || [], pinned: !!n.pinned,
    };
    try {
      if (noteId.current) {
        await api.updateMyNoteFull(noteId.current, body);
      } else {
        const created = await api.createMyNoteFull(body);
        noteId.current = created.id;
      }
      dirty.current = false;
      if (!silent) setSaved("сохранено");
    } catch {
      if (!silent) setSaved("не сохранилось");
    }
  }

  // ── чек-лист ───────────────────────────────────────────────────────────────
  function setItem(i, patch) {
    const list = [...(note.checklist || [])];
    list[i] = { ...list[i], ...patch };
    change({ checklist: list });
  }
  function addItem() {
    change({ checklist: [...(note.checklist || []), { text: "", done: false }] });
  }
  function removeItem(i) {
    change({ checklist: (note.checklist || []).filter((_, k) => k !== i) });
  }

  async function toTask(i) {
    await save(true);                      // сначала сохраняем, иначе пункта ещё нет на сервере
    if (!noteId.current) return;
    const when = window.prompt("Срок задачи (дата и время, можно пусто)", "");
    if (when === null) return;
    const body = when.trim() ? new Date(when).toISOString() : null;
    const r = await api.noteItemToTask(noteId.current, i, body);
    if (r._error) { toast(r.detail || "Не удалось создать задачу", "error"); return; }
    setNote((n) => ({ ...n, checklist: r.note.checklist }));
    toast("Задача создана", "success");
  }

  async function openPicker() {
    await save(true);                 // сохраняем до выбора: переносить нечего, если не сохранено
    if (!noteId.current) { toast("Сначала напишите заметку", "error"); return; }
    setPickOpen(true);
  }

  async function toPatient(patient) {
    setPickOpen(false);
    const r = await api.noteToPatient(noteId.current, patient.id);
    if (r._error) { toast(r.detail || "Не удалось перенести", "error"); return; }
    toast(r.message, "success");
    setNote((n) => ({ ...n, patient_id: patient.id }));
  }

  async function toAssistant() {
    await save(true);
    if (!noteId.current) return;
    const r = await api.noteToAssistant(noteId.current);
    if (r._error) { toast(r.detail || "Не удалось разобрать", "error"); return; }
    toast(r.message || "Разобрано", r.ok === false ? "error" : "success");
  }

  if (!note) return <><div className="hd"><div className="ttl">Заметка</div></div></>;

  const done = (note.checklist || []).filter((x) => x.done).length;

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
        <div className="ttl" style={{ flex: 1 }}>Заметка</div>
        {/* Состояние сохранения вместо кнопки: врач видит, что всё цело */}
        <span className="sub">{saved}</span>
      </div>

      <input className="input note-title" placeholder="Название"
             value={note.title} onChange={(e) => change({ title: e.target.value })} />

      <textarea className="input note-body" rows={8} placeholder="Текст заметки"
                value={note.text} onChange={(e) => change({ text: e.target.value })} />

      <div className="sec-label">
        Список{(note.checklist || []).length ? ` · ${done} из ${note.checklist.length}` : ""}
      </div>
      {(note.checklist || []).map((it, i) => (
        <div key={i} className="row check-row">
          <i className={"ti " + (it.done ? "ti-checkbox" : "ti-square")}
             style={{ cursor: "pointer", color: it.done ? "var(--sc)" : "var(--tm)" }}
             onClick={() => setItem(i, { done: !it.done })} />
          <input className="input check-input" value={it.text} placeholder="Пункт"
                 style={{ textDecoration: it.done ? "line-through" : "none" }}
                 onChange={(e) => setItem(i, { text: e.target.value })} />
          {/* Пункт становится задачей осознанно и со сроком: иначе список
              просроченного забьётся пунктами без срока. */}
          {it.reminder_id
            ? <i className="ti ti-bell-check succ" title="Уже задача" />
            : <i className="ti ti-bell-plus muted" title="Сделать задачей"
                 style={{ cursor: "pointer" }} onClick={() => toTask(i)} />}
          <i className="ti ti-x muted" style={{ cursor: "pointer" }} onClick={() => removeItem(i)} />
        </div>
      ))}
      <button className="btn sm block" onClick={addItem}>
        <i className="ti ti-plus" /> Пункт списка
      </button>

      <div className="sec-label">Схема</div>
      {drawOpen ? (
        <DrawCanvas value={note.drawing || ""}
                    onChange={(png) => change({ drawing: png })}
                    onClose={() => setDrawOpen(false)} />
      ) : note.drawing ? (
        <div className="draw-preview" onClick={() => setDrawOpen(true)}>
          <img src={note.drawing} alt="Схема" />
          <div className="sub">нажмите, чтобы дорисовать</div>
        </div>
      ) : (
        <button className="btn sm block" onClick={() => setDrawOpen(true)}>
          <i className="ti ti-pencil" /> Нарисовать схему
        </button>
      )}

      <div className="sec-label">Папка</div>
      <input className="input" list="note-folders" placeholder="Без папки"
             value={note.folder} onChange={(e) => change({ folder: e.target.value })} />
      <datalist id="note-folders">
        {folders.map((f) => <option key={f.name} value={f.name} />)}
      </datalist>

      <div className="sec-label">Что с этим сделать</div>
      <div className="btnrow" style={{ marginBottom: 8 }}>
        <button className="btn sm" style={{ flex: 1 }} onClick={openPicker}>
          <i className="ti ti-user-plus" /> {note.patient_id ? "Перенести ещё раз" : "В карту пациента"}
        </button>
        <button className="btn sm" style={{ flex: 1 }} onClick={toAssistant}>
          <i className="ti ti-sparkles" /> Разобрать
        </button>
      </div>

      {pickOpen && (
        <PatientPicker title="В чью карту перенести заметку"
                       onPick={toPatient} onClose={() => setPickOpen(false)} />
      )}

      <div className="btnrow" style={{ marginTop: 8 }}>
        <button className="btn sm" style={{ flex: 1 }}
                onClick={() => change({ pinned: !note.pinned })}>
          <i className={"ti " + (note.pinned ? "ti-pin-filled" : "ti-pin")} />
          {note.pinned ? " Открепить" : " Закрепить"}
        </button>
      </div>
    </>
  );
}
