import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { SkeletonList } from "../components/Loading";
import { fmtDay } from "../lib/dates";
import { plural } from "../lib/plural";

// Экран сводки на сегодня.
//
// Раньше утреннее уведомление было одной строкой со счётчиком, и нажатие вело
// в общий список уведомлений — врач всё равно шёл разбираться сам. Здесь то
// же самое, но по существу: расписание, просроченное и кто требует внимания,
// с переходами прямо в карты.

export default function Digest() {
  const nav = useNavigate();
  const [d, setD] = useState(null);

  useEffect(() => { api.digest().then(setD).catch(() => setD({ error: true })); }, []);

  if (!d) return <><div className="hd"><div className="ttl">Сводка</div></div><SkeletonList /></>;

  if (d.error) {
    return (
      <>
        <div className="hd">
          <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
          <div className="ttl">Сводка</div>
        </div>
        <div className="sub">Не удалось загрузить сводку.</div>
      </>
    );
  }

  const next = (d.schedule || []).filter((a) => !a.past);

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
        <div className="ttl" style={{ flex: 1 }}>Сводка на {fmtDay(d.date)}</div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 14, lineHeight: 1.5 }}>{d.text}</div>
      </div>

      {/* Приёмы. Прошедшие приглушены: взгляд должен цепляться за то, что впереди. */}
      <div className="sec-label">
        Приёмы{d.schedule?.length ? ` · ${d.schedule.length}` : ""}
      </div>
      {d.schedule?.length === 0 && <div className="sub">На сегодня приёмов нет.</div>}
      {d.schedule?.map((a) => (
        <div key={a.appointment_id} className="row" style={{ cursor: "pointer", opacity: a.past ? 0.55 : 1 }}
             onClick={() => nav(`/patients/${a.patient_id}`)}>
          <div style={{ display: "flex", gap: 12 }}>
            <span className="mono acc" style={{ minWidth: 42 }}>{a.time}</span>
            <div>
              <div style={{ fontSize: 13.5 }}>{a.name}</div>
              <div className="sub">{a.kind}{a.reason ? ` · ${a.reason}` : ""}</div>
            </div>
          </div>
          <i className="ti ti-chevron-right muted" />
        </div>
      ))}

      {d.overdue?.length > 0 && (
        <>
          <div className="sec-label">Просрочено · {d.overdue.length}</div>
          {d.overdue.map((r) => (
            <div key={r.reminder_id} className="row"
                 style={{ cursor: r.patient_id ? "pointer" : "default" }}
                 onClick={() => r.patient_id && nav(`/patients/${r.patient_id}`)}>
              <div>
                <div style={{ fontSize: 13.5 }}>{r.title}</div>
                <div className="sub dng">
                  {r.days > 0
                    ? `${r.days} ${plural(r.days, "день", "дня", "дней")} назад`
                    : "сегодня"}
                  {/* имя не повторяем, если оно уже есть в самой задаче:
                      «Контроль PSA — Кузнецов А. И. · Кузнецов А. И.» */}
                  {r.name && !r.title.includes(r.name.split(" ")[0]) ? ` · ${r.name}` : ""}
                </div>
              </div>
              {r.patient_id ? <i className="ti ti-chevron-right muted" /> : null}
            </div>
          ))}
        </>
      )}

      {d.needs_attention?.length > 0 && (
        <>
          <div className="sec-label">
            Требуют внимания{d.attention_total > d.needs_attention.length
              ? ` · показаны ${d.needs_attention.length} из ${d.attention_total}` : ""}
          </div>
          {d.needs_attention.map((p) => (
            <div key={p.patient_id} className="row" style={{ cursor: "pointer" }}
                 onClick={() => nav(`/patients/${p.patient_id}`)}>
              <div>
                <div style={{ fontSize: 13.5 }}>{p.name}</div>
                {/* Причина, а не число: иначе врач всё равно идёт разбираться сам */}
                <div className="sub">{p.why}</div>
              </div>
              <i className="ti ti-chevron-right muted" />
            </div>
          ))}
        </>
      )}

      {next.length === 0 && !d.overdue?.length && !d.needs_attention?.length && (
        <div className="sub" style={{ marginTop: 14 }}>
          Впереди ничего срочного.
        </div>
      )}
    </>
  );
}
