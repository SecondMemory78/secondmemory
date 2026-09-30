import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { notifyAssistantResult } from "../lib/bus";
import { WD, monthMatrix, monthRange, todayISO, weekOffsetOfISO, fmtDay, iso as isoOf } from "../lib/dates";
import { plural } from "../lib/plural";
import Tip from "../components/Tip";
import { useTips } from "../lib/tips";

export default function Home() {
  const nav = useNavigate();
  const { show } = useTips();
  const now = new Date();
  const Y = now.getFullYear(), M = now.getMonth() + 1;
  const [dash, setDash] = useState(null);
  const [appts, setAppts] = useState([]);
  const [rems, setRems] = useState([]);
  const [sub, setSub] = useState(null);
  const [attn, setAttn] = useState(null);
  const [attnOpen, setAttnOpen] = useState(false);

  function load() {
    api.dashboard().then(setDash).catch(() => {});
    api.attention().then(setAttn).catch(() => {});
    api.billingStatus().then(setSub).catch(() => {});
    // Берём месяц плюс полтора месяца вперёд: точки на неделе рисуются из
    // текущего месяца, а «ближайший приём» иначе не видел записи, попавшие
    // в следующий месяц — а это самый обычный случай в конце месяца.
    const [from] = monthRange(Y, M);
    const ahead = new Date(); ahead.setDate(ahead.getDate() + 45);
    const to = isoOf(ahead.getFullYear(), ahead.getMonth() + 1, ahead.getDate());
    api.appointments(from, to).then(setAppts).catch(() => {});
    api.reminders("open").then(setRems).catch(() => {});
  }
  useEffect(() => { load(); }, []);
  useEffect(() => { if (attn && attn.count > 0) show("tip:attention"); }, [attn, show]);
  // Новая раскладка: объясняем главную кнопку и вход в ассистента.
  // Показываются по очереди, одна за другой, и только при первом заходе.
  useEffect(() => { show("tip:start-visit"); show("tip:assistant"); }, [show]);

  const TODAY = todayISO();
  const dotDays = new Set(appts.map((a) => a.day));
  const remDays = new Set(rems.filter((r) => r.due_at).map((r) => {
    const d = new Date(r.due_at); return isoOf(d.getFullYear(), d.getMonth() + 1, d.getDate());
  }));
  // Ближайший приём — то, что нужно знать, когда сегодня никого: свободен ли
  // врач до вторника или на завтра уже кто-то записан. Данные уже загружены,
  // новых запросов к серверу не нужно.
  const nextAppt = appts
    .filter((a) => a.day > TODAY || (a.day === TODAY && a.time >= new Date().toTimeString().slice(0, 5)))
    .sort((x, y) => (x.day + x.time).localeCompare(y.day + y.time))[0];

  const weeks = monthMatrix(Y, M);
  // На Главной показываем НЕДЕЛЮ, а не месяц: месячная сетка занимала полэкрана
  // и утапливала вниз то, ради чего врач открыл приложение. Месяц остался
  // отдельной страницей «Календарь».
  const week = weeks.find((row) => row.some((c) => c.iso === TODAY)) || weeks[0];
  const todayAppts = appts.filter((a) => a.day === TODAY);
  const todayRems = rems.filter((r) => r.due_at && new Date(r.due_at) <= new Date());


  return (
    <>
      <div className="hd"><div className="ttl">Сегодня</div></div>

      {sub && sub.active && !sub.is_demo && sub.days_left <= 5 && (
        <div className="banner b-dn" style={{ marginBottom: 12 }} onClick={() => nav("/billing")}>
          <i className="ti ti-credit-card" /> Подписка заканчивается через {sub.days_left} дн. — продлить
        </div>
      )}

      {/* Неделя. Месяц — на отдельной странице «Календарь»: месячная сетка
          занимала полэкрана и утапливала вниз главное. */}
      <div className="weekstrip">
        {week.map((c) => {
          const isToday = c.iso === TODAY;
          return (
            <button key={c.iso} className={"wday" + (isToday ? " today" : "")}
                    onClick={() => nav(`/week/${weekOffsetOfISO(c.iso)}`)}>
              <span className="wd-name">{WD[(new Date(c.iso).getDay() + 6) % 7]}</span>
              <span className="wd-num">{c.day}</span>
              <span className="wd-dots">
                {dotDays.has(c.iso) && <i style={{ background: "var(--ac)" }} />}
                {remDays.has(c.iso) && <i style={{ background: "var(--rm)" }} />}
              </span>
            </button>
          );
        })}
      </div>

      {/* Главное действие — сразу, без прокрутки. Врач жаловался, что кнопку
          приёма приходилось искать в самом низу. */}
      <Tip tipKey="tip:start-visit" place="bottom" title="Отсюда начинается приём"
           text="Открывает карту пациента и заводит визит. Всё, что внесёте при открытом визите — заметки, показатели, назначения, документы, — привяжется именно к нему.">
        <button className="btn pri block start-visit" onClick={() => nav("/start-visit")}>
          <i className="ti ti-player-play" /> Начать приём
        </button>
      </Tip>

      {/* требуют внимания — компактная плитка, подробности в окне (чтобы не захламлять) */}
      {attn && attn.count > 0 && (
        <Tip tipKey="tip:attention" place="bottom" title="Это автоматический список"
             text="«Требуют внимания» собирается по правилам (согласие, контроль ПСА, дренажи, значения на подтверждении) — это подсказка системы, а не диагноз. Откройте, чтобы разобраться.">
          <div className="row" style={{ cursor: "pointer", marginTop: 6 }} onClick={() => setAttnOpen(true)}>
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <i className="ti ti-alert-triangle dng" style={{ fontSize: 19 }} />
              <div>
                <div style={{ fontSize: 13.5, fontWeight: 500 }}>Требуют внимания · {attn.count}</div>
                <div className="sub">{attnSummary(attn.items)}</div>
              </div>
            </div>
            <i className="ti ti-chevron-right muted" />
          </div>
        </Tip>
      )}

      {attnOpen && (
        <div className="modal-ov" onClick={() => setAttnOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxHeight: "78vh", overflowY: "auto" }}>
            <div className="sec-label" style={{ marginTop: 0, display: "flex", justifyContent: "space-between" }}>
              <span>Требуют внимания · {attn.count}</span>
              <i className="ti ti-x muted" style={{ cursor: "pointer" }} onClick={() => setAttnOpen(false)} />
            </div>
            {attn.items.map((it) => (
              <div key={it.patient_id} className="row" style={{ cursor: "pointer", alignItems: "flex-start" }}
                   onClick={() => { setAttnOpen(false); nav(`/patients/${it.patient_id}`); }}>
                <div>
                  <div style={{ fontSize: 13.5, fontWeight: 500 }}>{it.name}</div>
                  {it.reasons.map((r, i) => (
                    <div key={i} className={"sub" + (r.type === "no_consent" || r.type === "overdue" ? " dng" : "")}>
                      {r.text}
                    </div>
                  ))}
                </div>
                <i className="ti ti-chevron-right muted" style={{ marginTop: 4 }} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* подсказки (в духе Toki) */}
      {dash?.suggestions?.map((s, i) => (
        <div key={i} className={"banner " + (s.level === "high" ? "b-dn" : "b-ac")} onClick={() => nav(s.action === "cohort" ? "/search" : "/tasks")}>
          <i className={"ti " + s.icon} /> {s.text}
        </div>
      ))}

      {/* Список дня: приёмы и дела вместе, по времени. Это и есть ответ на
          вопрос «что у меня сегодня» — вместо шести счётчиков с нулями. */}
      <div className="sec-label">{fmtDay(TODAY)}</div>
      {todayAppts.map((a) => (
        <div key={"a" + a.id} className="row" style={{ cursor: "pointer" }} onClick={() => nav(`/patients/${a.patient_id}`)}>
          <div style={{ display: "flex", gap: 12 }}>
            <span className="mono acc" style={{ minWidth: 42 }}>{a.time}</span>
            <div>
              <div style={{ fontSize: 13.5 }}>{a.patient_name}</div>
              <div className="sub">{a.kind === "primary" ? "первичный" : "повторный"} · {a.reason}</div>
            </div>
          </div>
          <i className="ti ti-chevron-right muted" />
        </div>
      ))}
      {todayRems.map((r) => (
        <div key={"r" + r.id} className="row">
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <i className="ti ti-bell rmc" style={{ minWidth: 42, textAlign: "center" }} />
            <div>
              <div style={{ fontSize: 13.5 }}>{r.title}</div>
              <div className="sub rmc">напоминание{r.project ? " · " + r.project : ""}</div>
            </div>
          </div>
        </div>
      ))}
      {todayAppts.length === 0 && todayRems.length === 0 && (
        /* Пустой день должен отвечать на вопрос «раз сегодня никого — что дальше?»,
           а не просто сообщать, что пусто. */
        <div className="emptyday">
          <div className="sub">На сегодня ничего не запланировано.</div>

          {nextAppt && (
            <div className="row" style={{ cursor: "pointer", marginTop: 8 }}
                 onClick={() => nav(`/patients/${nextAppt.patient_id}`)}>
              <div style={{ display: "flex", gap: 12, alignItems: "baseline", minWidth: 0 }}>
                <i className="ti ti-calendar-event acc" />
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13.5 }}>Ближайший приём — {fmtDay(nextAppt.day)}, {nextAppt.time}</div>
                  <div className="sub">{nextAppt.patient_name}</div>
                </div>
              </div>
              <i className="ti ti-chevron-right muted" />
            </div>
          )}

          {dash?.weekly && (dash.weekly.appointments > 0 || dash.weekly.controls > 0) && (
            <div className="sub" style={{ marginTop: 10 }}>
              На этой неделе: {dash.weekly.appointments} {plural(dash.weekly.appointments, "приём", "приёма", "приёмов")}
              {dash.weekly.controls > 0 && `, ${dash.weekly.controls} ${plural(dash.weekly.controls, "контроль", "контроля", "контролей")}`}.
            </div>
          )}

          {!nextAppt && (
            <div className="btnrow" style={{ marginTop: 14 }}>
              <button className="btn sm" style={{ flex: 1 }} onClick={() => nav("/calendar")}>
                <i className="ti ti-calendar-plus" /> Запланировать
              </button>
              <button className="btn sm" style={{ flex: 1 }} onClick={() => nav("/patients")}>
                <i className="ti ti-user-plus" /> Добавить пациента
              </button>
            </div>
          )}
          <div className="gridfill" aria-hidden="true" />
        </div>
      )}

    </>
  );
}




// Короткая сводка для плитки: что именно требует внимания, без списка пациентов
function attnSummary(items) {
  const n = { no_consent: 0, overdue: 0, above: 0, pending: 0 };
  for (const it of items) for (const r of it.reasons) if (n[r.type] !== undefined) n[r.type]++;
  const parts = [];
  if (n.no_consent) parts.push(`без согласия: ${n.no_consent}`);
  if (n.overdue) parts.push(`просрочен контроль: ${n.overdue}`);
  if (n.above) parts.push(`выше порога: ${n.above}`);
  if (n.pending) parts.push(`на подтверждении: ${n.pending}`);
  return parts.join(" · ") || "нажмите, чтобы посмотреть";
}
