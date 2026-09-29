import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

export default function HeaderSearch() {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [res, setRes] = useState([]);
  const [notes, setNotes] = useState([]);      // заметки по пациентам
  const [myNotes, setMyNotes] = useState([]);  // мои личные заметки
  const [open, setOpen] = useState(false);
  const box = useRef(null);

  useEffect(() => {
    const t = setTimeout(() => {
      const term = q.trim();
      if (term) {
        api.patients(term).then((r) => { setRes(r); setOpen(true); }).catch(() => setRes([]));
        api.allPatientNotes(term).then((r) => setNotes(r.items || [])).catch(() => setNotes([]));
        api.myNotes(term).then((r) => setMyNotes(r.items || [])).catch(() => setMyNotes([]));
      } else { setRes([]); setNotes([]); setMyNotes([]); setOpen(false); }
    }, 180);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    const onDoc = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function goPatient(id) { setOpen(false); setQ(""); nav(`/patients/${id}`); }
  function goNotes() { setOpen(false); setQ(""); nav("/notes"); }
  function advanced() { setOpen(false); nav(`/search?q=${encodeURIComponent(q)}`); }

  return (
    <div className="gsearch-wrap" ref={box}>
      <div className="gsearch">
        <i className="ti ti-search" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => q && setOpen(true)}
          placeholder="Поиск: пациенты, диагнозы, заметки…"
        />
        {q && <i className="ti ti-x" style={{ cursor: "pointer" }} onClick={() => { setQ(""); setOpen(false); }} />}
      </div>

      {open && (
        <div className="gsearch-drop">
          {res.length === 0 && notes.length === 0 && myNotes.length === 0 &&
            <div className="gsearch-empty">Ничего не найдено</div>}
          {res.slice(0, 8).map((p) => (
            <div key={p.id} className="gsearch-item" onClick={() => goPatient(p.id)}>
              <div className="avatar" style={{ width: 30, height: 30, fontSize: 12 }}>
                {(p.last_name[0] || "") + (p.first_name[0] || "")}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {p.last_name} {p.first_name} {p.middle_name}
                </div>
                <div className="sub">{[p.age && p.age + " лет", p.diagnosis_code].filter(Boolean).join(" · ")}</div>
              </div>
            </div>
          ))}
          {notes.length > 0 && (
            <>
              <div className="gsearch-sec">Заметки по пациентам</div>
              {notes.slice(0, 4).map((n) => (
                <div key={"n" + n.id} className="gsearch-item" onClick={() => goPatient(n.patient_id)}>
                  <i className="ti ti-file-text muted" style={{ width: 30, textAlign: "center" }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{n.text}</div>
                    <div className="sub">{n.patient_name}</div>
                  </div>
                </div>
              ))}
            </>
          )}

          {myNotes.length > 0 && (
            <>
              <div className="gsearch-sec">Мои заметки</div>
              {myNotes.slice(0, 4).map((n) => (
                <div key={"m" + n.id} className="gsearch-item" onClick={goNotes}>
                  <i className="ti ti-notes muted" style={{ width: 30, textAlign: "center" }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{n.text}</div>
                    <div className="sub">личная заметка</div>
                  </div>
                </div>
              ))}
            </>
          )}

          <div className="gsearch-foot" onClick={advanced}>
            <i className="ti ti-adjustments-horizontal" /> Срез по картотеке и расширенный поиск
          </div>
        </div>
      )}
    </div>
  );
}
