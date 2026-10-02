import { useEffect, useRef, useState } from "react";
import { api } from "../api";

// Выбор пациента.
//
// Раньше здесь спрашивали фамилию текстом. Это работало, но плохо: ошибся в
// букве — «не найдено», есть однофамильцы — «уточните», и врач гадает, кого
// система имела в виду. Список с поиском показывает возраст и диагноз, то есть
// то, чем тёзки и различаются.
//
// Выбор всегда делает врач: ничего не подставляется само.

export default function PatientPicker({ title = "Выберите пациента", onPick, onClose }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState(null);
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      api.patients(q).then(setItems).catch(() => setItems([]));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div className="modal-ov" onClick={onClose}>
      <div className="modal picker" onClick={(e) => e.stopPropagation()}>
        <div className="sec-label" style={{ marginTop: 0 }}>{title}</div>

        <input ref={inputRef} className="input" placeholder="Фамилия или диагноз"
               value={q} onChange={(e) => setQ(e.target.value)} />

        <div className="picker-list">
          {items === null && <div className="sub" style={{ padding: "10px 0" }}>Загружаю…</div>}
          {items !== null && items.length === 0 && (
            <div className="sub" style={{ padding: "10px 0" }}>
              {q ? "Никто не найден" : "Пациентов пока нет"}
            </div>
          )}
          {(items || []).map((p) => (
            <div key={p.id} className="row" style={{ cursor: "pointer" }}
                 onClick={() => onPick(p)}>
              <div>
                <div style={{ fontSize: 13.5 }}>{p.short_name || p.last_name}</div>
                {/* Возраст и диагноз — то, чем однофамильцы и различаются */}
                <div className="sub">
                  {[p.age ? `${p.age} лет` : "", p.diagnosis_code || ""]
                    .filter(Boolean).join(" · ") || "без диагноза"}
                </div>
              </div>
              <i className="ti ti-chevron-right muted" />
            </div>
          ))}
        </div>

        <button className="btn block" style={{ marginTop: 10 }} onClick={onClose}>Отмена</button>
      </div>
    </div>
  );
}
