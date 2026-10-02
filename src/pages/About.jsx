import { useNavigate } from "react-router-dom";
import { CHANGELOG, VERSION } from "../lib/version";
import { fmtDate } from "../lib/dates";

// О приложении: версия и что менялось.
//
// Список изменений написан на языке врача, а не разработчика: он отвечает на
// вопрос «почему теперь иначе», а не перечисляет правки.

export default function About() {
  const nav = useNavigate();

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
        <div className="ttl" style={{ flex: 1 }}>О приложении</div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 15, fontWeight: 500 }}>Вторая память врача</div>
        <div className="sub" style={{ marginTop: 4 }}>
          Версия {VERSION}
        </div>
        <div className="sub" style={{ marginTop: 8, lineHeight: 1.5 }}>
          Приложение помогает вести наблюдение и не терять сроки. Оно не ставит
          диагнозов, не назначает лечение и не заменяет ваше решение.
        </div>
      </div>

      <div className="sec-label">Что менялось</div>
      {CHANGELOG.map((rel) => (
        <div key={rel.version} className="card" style={{ marginBottom: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <b style={{ fontSize: 13.5 }}>{rel.title}</b>
            <span className="sub">{rel.version}</span>
          </div>
          <div className="sub" style={{ marginBottom: 6 }}>{fmtDate(rel.date)}</div>
          {rel.items.map((x, i) => (
            <div key={i} className="sub" style={{ lineHeight: 1.6 }}>· {x}</div>
          ))}
        </div>
      ))}
    </>
  );
}
