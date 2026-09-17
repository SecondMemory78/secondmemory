import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { WD, monthMatrix, monthRange, monthLabel, todayISO, weekOffsetOfISO, fmtDay, iso as isoOf } from "../lib/dates";

export default function Home() {
  const nav = useNavigate();
  const now = new Date();
  const Y = now.getFullYear(), M = now.getMonth() + 1;
  const [dash, setDash] = useState(null);
  const [appts, setAppts] = useState([]);
  const [rems, setRems] = useState([]);
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [sub, setSub] = useState(null);
  const [attn, setAttn] = useState(null);

  function load() {
    api.dashboard().then(setDash).catch(() => {});
    api.attention().then(setAttn).catch(() => {});
    api.billingStatus().then(setSub).catch(() => {});
    const [from, to] = monthRange(Y, M);
    api.appointments(from, to).then(setAppts).catch(() => {});
    api.reminders("open").then(setRems).catch(() => {});
  }
  useEffect(() => { load(); }, []);

  const TODAY = todayISO();
  const dotDays = new Set(appts.map((a) => a.day));
  const remDays = new Set(rems.filter((r) => r.due_at).map((r) => {
    const d = new Date(r.due_at); return isoOf(d.getFullYear(), d.getMonth() + 1, d.getDate());
  }));
  const weeks = monthMatrix(Y, M);
  const todayAppts = appts.filter((a) => a.day === TODAY);
  const todayRems = rems.filter((r) => r.due_at && new Date(r.due_at) <= new Date());

  async function voiceCapture(blob) {
    setNote("Распознаю и разбираю…");
    const res = await api.assistantVoice(blob);
    setNote(res.message || "Готово");
    load();
  }
  async function quickAdd() {
    if (!text.trim()) return;
    const res = await api.assistantCommand(text.trim());
    setText(""); setNote(res.message || "Готово"); load();
  }

  return (
    <>
      <div className="hd"><div className="ttl">Главная</div></div>

      {sub && sub.active && !sub.is_demo && sub.days_left <= 5 && (
        <div className="banner b-dn" style={{ marginBottom: 12 }} onClick={() => nav("/billing")}>
          <i className="ti ti-credit-card" /> Подписка заканчивается через {sub.days_left} дн. — продлить
        </div>
      )}

      {/* умный диктофон — центральный захват */}
      <div className="hero">
        <VoiceButtonHero onResult={voiceCapture} />
        <div style={{ fontSize: 13.5, fontWeight: 500 }}>Записать голосом</div>
        <div className="acc" style={{ fontSize: 12, marginTop: 6, cursor: "pointer" }} onClick={() => nav("/dictation")}>Несколько дел разом →</div>
        <div className="sub" style={{ marginTop: 2 }}>приём, задача, заметка или запись в карту — разберём сами</div>
        {note && <div className="sub acc" style={{ marginTop: 8 }}>{note}</div>}
      </div>

      <div className="input" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <i className="ti ti-sparkles muted" />
        <input value={text} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && quickAdd()}
          placeholder="«запиши Иванова на среду 15:00» / «заехать в магазин вечером»"
          style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)" }} />
      </div>

      {/* сводка дня */}
      {dash && (
        <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
          <Stat n={dash.today_appointments} label="приёма" color="var(--ac)" />
          <Stat n={dash.overdue_reminders} label="просрочено" color="var(--rm)" />
          <Stat n={dash.pending_observations} label="на проверке" color="var(--wn)" />
        </div>
      )}

      {/* требуют внимания — проактивная лента по всем пациентам */}
      {attn && attn.count > 0 && (
        <div style={{ marginTop: 6 }}>
          <div className="sec-label"><i className="ti ti-alert-triangle dng" /> Требуют внимания · {attn.count}</div>
          {attn.items.slice(0, 8).map((it) => (
            <div key={it.patient_id} className="row" style={{ cursor: "pointer" }} onClick={() => nav(`/patients/${it.patient_id}`)}>
              <div>
                <div style={{ fontSize: 13.5, fontWeight: 500 }}>{it.name}</div>
                <div className="sub">{it.reasons.map((r) => r.text).join(" · ")}</div>
              </div>
              <i className="ti ti-chevron-right muted" />
            </div>
          ))}
          {attn.count > 8 && <div className="sub" style={{ marginTop: 4 }}>…и ещё {attn.count - 8}</div>}
        </div>
      )}

      {/* подсказки (в духе Toki) */}
      {dash?.suggestions?.map((s, i) => (
        <div key={i} className={"banner " + (s.level === "high" ? "b-dn" : "b-ac")} onClick={() => nav(s.action === "cohort" ? "/search" : "/tasks")}>
          <i className={"ti " + s.icon} /> {s.text}
        </div>
      ))}

      {/* недельная сводка */}
      {dash?.weekly && (
        <div className="card" style={{ marginTop: 6 }}>
          <div className="sub" style={{ fontWeight: 500, marginBottom: 8 }}>На этой неделе</div>
          <div style={{ display: "flex", gap: 8 }}>
            <WeekStat n={dash.weekly.appointments} label="приёмов" />
            <WeekStat n={dash.weekly.controls} label="контролей" />
            <WeekStat n={dash.weekly.overdue} label="просрочено" danger={dash.weekly.overdue > 0} />
          </div>
        </div>
      )}

      {/* календарь на главной */}
      <div className="sec-label">{monthLabel(Y, M)}</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", marginBottom: 6 }}>
        {WD.map((d) => (
          <div key={d} style={{ textAlign: "center", fontSize: 11, color: "var(--tm)" }}>{d}</div>
        ))}
      </div>
      {weeks.map((row, wi) => (
        <div key={wi} onClick={() => nav(`/week/${weekOffsetOfISO(row.find((c) => c.cur).iso)}`)}
          style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", borderRadius: 12, cursor: "pointer" }}>
          {row.map((c, i) => {
            const isToday = c.iso === TODAY;
            const hasA = c.cur && dotDays.has(c.iso);
            const hasR = c.cur && remDays.has(c.iso);
            return (
              <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3, padding: "8px 0" }}>
                {isToday ? (
                  <div style={{ width: 27, height: 27, borderRadius: "50%", background: "var(--ac)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13 }}>{c.day}</div>
                ) : (
                  <div style={{ fontSize: 13, color: c.cur ? "var(--tp)" : "var(--tm)", opacity: c.cur ? 1 : 0.5 }}>{c.day}</div>
                )}
                <div style={{ display: "flex", gap: 2, height: 5 }}>
                  {hasA && <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--ac)" }} />}
                  {hasR && <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--rm)" }} />}
                </div>
              </div>
            );
          })}
        </div>
      ))}
      <div style={{ marginTop: 8 }}>
        <span className="legdot"><span style={{ background: "var(--ac)" }} /> приём</span>
        <span className="legdot"><span style={{ background: "var(--rm)" }} /> напоминание</span>
      </div>

      {/* сегодня */}
      <div className="sec-label">Сегодня, {fmtDay(TODAY)}</div>
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

      <button className="btn pri block" style={{ marginTop: 18, padding: 14 }} onClick={() => nav("/start-visit")}>
        <i className="ti ti-player-play" /> Начать приём
      </button>
    </>
  );
}

function Stat({ n, label, color }) {
  return (
    <div className="card" style={{ flex: 1, textAlign: "center", padding: "12px 6px" }}>
      <div style={{ fontSize: 22, fontWeight: 600, color }}>{n}</div>
      <div className="sub" style={{ marginTop: 2 }}>{label}</div>
    </div>
  );
}

function WeekStat({ n, label, danger }) {
  return (
    <div style={{ flex: 1, textAlign: "center" }}>
      <div style={{ fontSize: 20, fontWeight: 600, color: danger ? "var(--dn)" : "var(--tp)" }}>{n}</div>
      <div className="sub" style={{ marginTop: 2 }}>{label}</div>
    </div>
  );
}

// большой круг микрофона для главной
function VoiceButtonHero({ onResult }) {
  const [rec, setRec] = useState(false);
  let mr = null;
  const chunks = [];
  async function toggle() {
    if (rec && window.__mr) { window.__mr.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mr = new MediaRecorder(stream);
      window.__mr = mr;
      mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        setRec(false);
        onResult(new Blob(chunks, { type: "audio/webm" }));
      };
      mr.start(); setRec(true);
    } catch (e) { onResult(null); }
  }
  return (
    <button className={"mic" + (rec ? " rec" : "")} onClick={toggle}>
      <i className={"ti " + (rec ? "ti-player-stop rec" : "ti-microphone")} />
    </button>
  );
}
