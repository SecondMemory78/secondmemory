import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

export default function HeaderSearch() {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [res, setRes] = useState([]);
  const [open, setOpen] = useState(false);
  const box = useRef(null);

  useEffect(() => {
    const t = setTimeout(() => {
      if (q.trim()) api.patients(q.trim()).then((r) => { setRes(r); setOpen(true); }).catch(() => setRes([]));
      else { setRes([]); setOpen(false); }
    }, 180);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    const onDoc = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function goPatient(id) { setOpen(false); setQ(""); nav(`/patients/${id}`); }
  function advanced() { setOpen(false); nav(`/search?q=${encodeURIComponent(q)}`); }

  return (
    <div className="gsearch-wrap" ref={box}>
      <div className="gsearch">
        <i className="ti ti-search" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => q && setOpen(true)}
          placeholder="Поиск пациентов и диагнозов…"
        />
        {q && <i className="ti ti-x" style={{ cursor: "pointer" }} onClick={() => { setQ(""); setOpen(false); }} />}
      </div>

      {open && (
        <div className="gsearch-drop">
          {res.length === 0 && <div className="gsearch-empty">Ничего не найдено</div>}
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
          <div className="gsearch-foot" onClick={advanced}>
            <i className="ti ti-adjustments-horizontal" /> Срез по картотеке и расширенный поиск
          </div>
        </div>
      )}
    </div>
  );
}
