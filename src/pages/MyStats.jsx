import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Spinner } from "../components/Loading";

const PERIODS = [
  { days: 30, label: "30 дней" },
  { days: 90, label: "3 месяца" },
  { days: 365, label: "год" },
];

export default function MyStats() {
  const nav = useNavigate();
  const [days, setDays] = useState(90);
  const [st, setSt] = useState(null);

  useEffect(() => {
    setSt(null);
    api.myStats(days).then(setSt).catch(() => setSt(false));
  }, [days]);

  const maxWd = st ? Math.max(1, ...st.by_weekday.map((w) => w.total)) : 1;

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav("/more")} />
        <div className="ttl">Моя статистика</div>
      </div>
      <div className="sub" style={{ marginBottom: 10 }}>
        Только ваш приём — эти данные никуда не передаются.
      </div>

      <div className="tabs">
        {PERIODS.map((p) => (
          <div key={p.days} className={"t" + (days === p.days ? " on" : "")}
               onClick={() => setDays(p.days)}>{p.label}</div>
        ))}
      </div>

      {st === null && <Spinner />}
      {st === false && <div className="sub dng">Не удалось загрузить статистику.</div>}

      {st && (
        <>
          <div className="sec-label">Приёмы за период</div>
          <div className="card">
            <div className="row" style={{ borderTop: 0 }}>
              <span className="sub">Проведено</span>
              <span style={{ fontSize: 15, fontWeight: 600 }}>{st.appointments.done}</span>
            </div>
            <div className="row">
              <span className="sub">Не пришли</span>
              <span style={{ fontSize: 15, fontWeight: 600, color: st.appointments.no_show ? "var(--dn)" : "var(--tp)" }}>
                {st.appointments.no_show}
                {st.appointments.no_show_rate > 0 && (
                  <span className="sub" style={{ marginLeft: 6 }}>({st.appointments.no_show_rate}%)</span>
                )}
              </span>
            </div>
            <div className="row"><span className="sub">Отменено</span><span>{st.appointments.cancelled}</span></div>
            <div className="row"><span className="sub">Запланировано впереди</span><span>{st.appointments.upcoming}</span></div>
            {st.appointments.total === 0 && (
              <div className="sub" style={{ marginTop: 6 }}>За период завершённых приёмов не было.</div>
            )}
          </div>

          <div className="sec-label">По дням недели</div>
          <div className="card">
            <div className="sub" style={{ marginBottom: 8 }}>
              Серым — всего приёмов, красным — сколько из них не пришли.
            </div>
            {st.by_weekday.map((w) => (
              <div key={w.day} style={{ marginBottom: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 3 }}>
                  <span>{w.day}</span>
                  <span className="sub">{w.total}{w.no_show ? ` · не пришли ${w.no_show}` : ""}</span>
                </div>
                <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", background: "var(--s1)" }}>
                  <div style={{ width: `${(w.total - w.no_show) / maxWd * 100}%`, background: "var(--bds)" }} />
                  <div style={{ width: `${w.no_show / maxWd * 100}%`, background: "var(--dn)" }} />
                </div>
              </div>
            ))}
          </div>

          <div className="sec-label">Картотека</div>
          <div className="card">
            <div className="row" style={{ borderTop: 0 }}><span className="sub">Всего пациентов</span><span>{st.patients.total}</span></div>
            <div className="row"><span className="sub">Новых за период</span><span>{st.patients.new}</span></div>
            <div className="row"><span className="sub">Заметок в картах</span><span>{st.patients.notes}</span></div>
          </div>

          <div className="sec-label">Задачи</div>
          <div className="card">
            <div className="row" style={{ borderTop: 0 }}><span className="sub">Открытых</span><span>{st.tasks.open}</span></div>
            <div className="row">
              <span className="sub">Просрочено</span>
              <span style={{ color: st.tasks.overdue ? "var(--dn)" : "var(--tp)" }}>{st.tasks.overdue}</span>
            </div>
            <div className="row"><span className="sub">Закрыто за период</span><span>{st.tasks.done}</span></div>
          </div>
        </>
      )}
    </>
  );
}
