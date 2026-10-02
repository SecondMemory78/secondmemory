import { useEffect, useState } from "react";
import { api } from "../api";
import { fmtDate } from "../lib/dates";

/**
 * Ответ из доверенных источников: только цитата и ссылка.
 * Выводов не делаем — их делает врач. Нет проверки — честно пишем об этом.
 */
export default function SourceAnswer({ question, title = "В источниках" }) {
  const [res, setRes] = useState(null);

  useEffect(() => {
    const q = (question || "").trim();
    if (q.length < 4) { setRes(null); return; }
    const t = setTimeout(() => {
      api.sourceLookup(q).then(setRes).catch(() => setRes(null));
    }, 500);
    return () => clearTimeout(t);
  }, [question]);

  if (!res || !res.query) return null;

  return (
    <div className="card" style={{ marginTop: 8, background: "var(--s1)" }}>
      <div className="sub" style={{ marginBottom: 4 }}>{title}</div>

      {res.status === "ok" ? (
        <>
          <div style={{ fontSize: 13, whiteSpace: "pre-wrap" }}>«{res.quote}»</div>
          <div className="sub" style={{ marginTop: 6 }}>
            {res.source}{res.scope_label ? ` · ${res.scope_label}` : ""}
            {res.checked_at ? ` · проверено ${fmtDate(res.checked_at)}` : ""}
          </div>
          {res.url && (
            <a className="acc" href={res.url} target="_blank" rel="noreferrer"
               style={{ fontSize: 12.5 }}>открыть документ →</a>
          )}
          {res.stale && <div className="sub wn" style={{ marginTop: 4 }}>{res.note}</div>}
          {res.scope_label && res.scope_label !== "ЕАЭС" && (
            <div className="sub" style={{ marginTop: 4 }}>
              Зарубежный источник — не российская рекомендация.
            </div>
          )}
        </>
      ) : (
        <div className="sub">
          Не проверено: в источниках пока не смотрели. Запрос «{res.query}» поставлен
          в очередь — ответ появится здесь после проверки.
        </div>
      )}
    </div>
  );
}
