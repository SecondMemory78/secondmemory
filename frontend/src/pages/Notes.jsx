import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { SkeletonList, Empty } from "../components/Loading";
import { fmtDateTime, fmtDate } from "../lib/dates";
import { confirmAction } from "../lib/confirm";
import { toast } from "../lib/toast";

export default function Notes() {
  const nav = useNavigate();
  const [tab, setTab] = useState("my");        // my | all
  const [q, setQ] = useState("");
  const [mine, setMine] = useState(null);
  const [all, setAll] = useState(null);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(null); // {id, text}
  const [busy, setBusy] = useState(false);

  function loadMine(query = q) {
    api.myNotes(query).then((r) => setMine(r.items)).catch(() => setMine([]));
  }
  function loadAll(query = q) {
    api.allPatientNotes(query).then((r) => setAll(r.items)).catch(() => setAll([]));
  }

  useEffect(() => {
    const t = setTimeout(() => (tab === "my" ? loadMine() : loadAll()), 300);
    return () => clearTimeout(t);
  }, [tab, q]);

  async function add() {
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      await api.createMyNote(text);
      setDraft(""); loadMine();
    } catch { toast("Не удалось сохранить заметку", "error"); }
    finally { setBusy(false); }
  }

  async function saveEdit() {
    const text = editing.text.trim();
    if (!text) return;
    try {
      await api.updateMyNote(editing.id, text, editing.pinned);
      setEditing(null); loadMine();
    } catch { toast("Не удалось изменить", "error"); }
  }

  async function togglePin(n) {
    await api.pinMyNote(n.id).catch(() => {});
    loadMine();
  }

  async function remove(n) {
    if (!(await confirmAction({ title: "Удалить заметку?", confirmText: "Удалить" }))) return;
    await api.deleteMyNote(n.id).catch(() => {});
    loadMine();
    // мягкое удаление — даём вернуть, если нажали случайно
    toast("Заметка удалена", "info", {
      label: "Отменить",
      onAction: async () => { await api.restoreMyNote(n.id).catch(() => {}); loadMine(); },
    });
  }

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav("/more")} />
        <div className="ttl">Заметки</div>
      </div>

      <div className="tabs">
        <div className={"t" + (tab === "my" ? " on" : "")} onClick={() => setTab("my")}>Мои заметки</div>
        <div className={"t" + (tab === "all" ? " on" : "")} onClick={() => setTab("all")}>По пациентам</div>
      </div>

      <div className="input" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <i className="ti ti-search muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)}
          placeholder={tab === "my" ? "Поиск по заметкам" : "Поиск по тексту или пациенту"}
          style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)" }} />
      </div>

      {tab === "my" && (
        <>
          <div className="card" style={{ marginBottom: 12 }}>
            <textarea className="input" rows={3} value={draft} onChange={(e) => setDraft(e.target.value)}
              placeholder="Новая заметка — мысль, напоминание себе, что уточнить"
              style={{ resize: "vertical", marginBottom: 8 }} />
            <button className="btn pri block" disabled={!draft.trim() || busy} onClick={add}>
              <i className="ti ti-plus" /> Добавить
            </button>
          </div>

          {mine === null && <SkeletonList rows={4} />}
          {mine !== null && mine.length === 0 && (
            <Empty icon="ti-notes" title={q ? "Ничего не найдено" : "Заметок пока нет"}
                   sub={q ? "Измените запрос" : "Здесь только ваши личные заметки — пациенты их не касаются"} />
          )}

          {(mine || []).map((n) => (
            <div key={n.id} className="card" style={{ marginBottom: 8 }}>
              {editing?.id === n.id ? (
                <>
                  <textarea className="input" rows={3} value={editing.text}
                    onChange={(e) => setEditing({ ...editing, text: e.target.value })}
                    style={{ resize: "vertical", marginBottom: 8 }} />
                  <div className="btnrow">
                    <button className="btn sm" style={{ flex: 1 }} onClick={() => setEditing(null)}>Отмена</button>
                    <button className="btn pri sm" style={{ flex: 1 }} onClick={saveEdit}>Сохранить</button>
                  </div>
                </>
              ) : (
                <>
                  <div style={{ fontSize: 13.5, whiteSpace: "pre-wrap" }}>
                    {n.pinned && <i className="ti ti-pin acc" style={{ marginRight: 5 }} />}
                    {n.text}
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
                    <span className="sub">{fmtDateTime(n.updated_at)}</span>
                    <span style={{ display: "flex", gap: 12 }}>
                      <span className="acc" style={{ fontSize: 12, cursor: "pointer" }} onClick={() => togglePin(n)}>
                        {n.pinned ? "открепить" : "закрепить"}
                      </span>
                      <span className="acc" style={{ fontSize: 12, cursor: "pointer" }}
                            onClick={() => setEditing({ id: n.id, text: n.text, pinned: n.pinned })}>изменить</span>
                      <span className="dng" style={{ fontSize: 12, cursor: "pointer" }} onClick={() => remove(n)}>удалить</span>
                    </span>
                  </div>
                </>
              )}
            </div>
          ))}
        </>
      )}

      {tab === "all" && (
        <>
          <div className="sub" style={{ marginBottom: 10 }}>
            Заметки из карт пациентов. Чтобы изменить — откройте карту: там виден контекст приёма.
          </div>
          {all === null && <SkeletonList rows={4} />}
          {all !== null && all.length === 0 && (
            <Empty icon="ti-file-text" title={q ? "Ничего не найдено" : "Заметок по пациентам пока нет"} />
          )}
          {(all || []).map((n) => (
            <div key={n.id} className="row" style={{ cursor: "pointer", alignItems: "flex-start" }}
                 onClick={() => nav("/patients/" + n.patient_id)}>
              <div>
                <div style={{ fontSize: 13.5 }}>{n.text}</div>
                <div className="sub" style={{ marginTop: 2 }}>
                  {n.patient_name} · {fmtDate(n.created_at)}
                  {n.source === "voice" && <> · <i className="ti ti-microphone" style={{ fontSize: 12 }} /></>}
                </div>
              </div>
              <i className="ti ti-chevron-right muted" style={{ marginTop: 4 }} />
            </div>
          ))}
        </>
      )}
    </>
  );
}
