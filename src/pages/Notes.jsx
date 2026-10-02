import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { SkeletonList, Empty } from "../components/Loading";
import { fmtDateTime, fmtDate } from "../lib/dates";
import { confirmAction } from "../lib/confirm";
import { toast } from "../lib/toast";

export default function Notes({ embedded = false }) {
  const nav = useNavigate();
  const [tab, setTab] = useState("my");        // my | all
  const [q, setQ] = useState("");
  const [mine, setMine] = useState(null);
  const [all, setAll] = useState(null);
  const [draft, setDraft] = useState("");
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
      {!embedded && (
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav("/more")} />
        <div className="ttl">Заметки</div>
      </div>
      )}

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
            <div className="btnrow">
              <button className="btn pri" style={{ flex: 1 }} disabled={!draft.trim() || busy} onClick={add}>
                <i className="ti ti-plus" /> Быстро добавить
              </button>
              {/* Полный вид — с названием, списком и папкой */}
              <button className="btn" style={{ flex: 1 }} onClick={() => nav("/notes/new")}>
                <i className="ti ti-edit" /> Развёрнуто
              </button>
            </div>
          </div>

          {mine === null && <SkeletonList rows={4} />}
          {mine !== null && mine.length === 0 && (
            <Empty icon="ti-notes" title={q ? "Ничего не найдено" : "Заметок пока нет"}
                   sub={q ? "Измените запрос" : "Здесь только ваши личные заметки — пациенты их не касаются"} />
          )}

          {(mine || []).map((n) => (
            <div key={n.id} className="card note-card" style={{ marginBottom: 8 }}>
              <>
                  <div className="note-acts">
                    <i className={"ti " + (n.pinned ? "ti-pin-filled acc" : "ti-pin muted")}
                       title={n.pinned ? "Открепить" : "Закрепить"}
                       onClick={(e) => { e.stopPropagation(); togglePin(n); }} />
                    <i className="ti ti-trash muted" title="Удалить"
                       onClick={(e) => { e.stopPropagation(); remove(n); }} />
                  </div>
                  <div onClick={() => nav(`/notes/${n.id}`)} style={{ cursor: "pointer" }}>
                    <div style={{ fontSize: 14, fontWeight: 500 }}>
                      {n.pinned && <i className="ti ti-pin acc" style={{ marginRight: 5 }} />}
                      {n.title}
                    </div>
                    {/* Текст показываем в две строки: список должен листаться,
                        а не превращаться в простыню. */}
                    {n.text && (
                      <div className="sub note-preview" style={{ marginTop: 3 }}>{n.text}</div>
                    )}
                    <div style={{ display: "flex", gap: 10, marginTop: 6, flexWrap: "wrap" }}>
                      {n.folder && <span className="chip-sm">{n.folder}</span>}
                      {n.checklist_total > 0 && (
                        <span className="chip-sm">
                          <i className="ti ti-checkbox" /> {n.checklist_done} из {n.checklist_total}
                        </span>
                      )}
                    </div>
                  </div>
                  {/* «Изменить» отсюда убрано: та правка на месте не знала ни
                      про заголовок, ни про список, и заметка после неё
                      становилась «Без названия». Правка теперь одна — на своём
                      экране, по нажатию на карточку. */}
                  <div className="sub" style={{ marginTop: 8 }}>{fmtDateTime(n.updated_at)}</div>
              </>
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
