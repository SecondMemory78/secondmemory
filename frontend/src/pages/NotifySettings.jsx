import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import Toggle from "../components/Toggle";
import Button from "../components/Button";
import { Spinner } from "../components/Loading";
import { pushSupported, isStandalone, detectPlatform, rememberPlatform,
         permissionStatus, subscribePush, unsubscribePush } from "../lib/push";

const KINDS = [
  ["appointment", "Приёмы"],
  ["control", "Контроли"],
  ["task", "Задачи"],
  ["call", "Звонки"],
];
const OFFSET_PRESETS = [5, 15, 30, 60, 1440];
const OFFSET_LABEL = { 5: "5 мин", 15: "15 мин", 30: "30 мин", 60: "1 час", 1440: "1 день" };

export default function NotifySettings() {
  const nav = useNavigate();
  const [p, setP] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  function load() { api.notifyPrefs().then(setP).catch(() => {}); }
  useEffect(() => { load(); }, []);

  // ── Push-подписка ──
  const [perm, setPerm] = useState(permissionStatus());
  const [platform, setPlatform] = useState(detectPlatform());
  const [askPlatform, setAskPlatform] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [pushMsg, setPushMsg] = useState("");
  const [testedDone, setTestedDone] = useState(localStorage.getItem("sm_push_tested") === "1");

  async function enablePush() {
    // если платформу не определили — сперва спросим один раз
    if (platform === "unknown" && !askPlatform) { setAskPlatform(true); return; }
    // iPhone и приложение НЕ добавлено на экран → показать инструкцию, не дёргать запрос
    if (platform === "ios" && !isStandalone()) { setPushMsg("ios-instruction"); return; }
    setPushBusy(true); setPushMsg("");
    try {
      await subscribePush();
      setPerm("granted"); setPushMsg("Уведомления включены.");
    } catch (e) {
      setPushMsg(e.message || "Не удалось включить уведомления.");
    } finally { setPushBusy(false); }
  }
  async function disablePush() {
    await unsubscribePush(); setPerm(permissionStatus()); setPushMsg("Уведомления отключены на этом устройстве.");
  }
  async function sendTest() {
    setPushBusy(true);
    try { await api.pushTest(); localStorage.setItem("sm_push_tested", "1"); setTestedDone(true); setPushMsg("Тест отправлен — проверьте телефон."); }
    catch (e) { setPushMsg("Не удалось отправить тест."); }
    finally { setPushBusy(false); }
  }
  function choosePlatform(p) { rememberPlatform(p); setPlatform(p); setAskPlatform(false); setTimeout(enablePush, 0); }

  async function save(patch) {
    setBusy(true); setMsg("");
    try {
      const r = await api.updateNotifyPrefs({ expected_version: p.version, ...patch });
      setP(r); setMsg("Сохранено");
      setTimeout(() => setMsg(""), 1500);
    } catch (e) {
      if (e.status === 409) { setMsg("Изменено на другом устройстве — обновляю…"); load(); }
      else setMsg(e.detail || "Не удалось сохранить");
    } finally { setBusy(false); }
  }

  function toggleOffset(kind, minutes) {
    const cur = p.default_offsets[kind] || [];
    const next = cur.includes(minutes) ? cur.filter((x) => x !== minutes) : [...cur, minutes].sort((a, b) => a - b);
    save({ default_offsets: { ...p.default_offsets, [kind]: next } });
  }

  if (!p) return <Spinner label="Загружаю настройки…" />;

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
        <div className="ttl">Уведомления</div>
      </div>
      {msg && <div className="sub acc" style={{ marginBottom: 10 }}>{msg}</div>}

      <div className="sec-label" style={{ marginTop: 0 }}>Пуш-уведомления на телефон</div>
      <div className="card" style={{ marginBottom: 12 }}>
        {!pushSupported() && (
          <div className="sub">Этот браузер не поддерживает пуш-уведомления. На iPhone добавьте приложение на экран «Домой» и откройте оттуда.</div>
        )}
        {pushSupported() && (
          <>
            {perm === "granted" ? (
              <>
                <div style={{ fontSize: 13, marginBottom: 8 }}><i className="ti ti-bell-check acc" /> Уведомления включены на этом устройстве</div>
                {!testedDone && (
                  <button className="btn sm" style={{ marginRight: 8 }} disabled={pushBusy} onClick={sendTest}>Отправить тестовое</button>
                )}
                <button className="btn sm" onClick={disablePush}>Отключить здесь</button>
              </>
            ) : (
              <>
                <div className="sub" style={{ marginBottom: 8 }}>
                  Получайте напоминания о приёмах и контролях, даже когда приложение закрыто.
                </div>
                {askPlatform ? (
                  <>
                    <div style={{ fontSize: 13, marginBottom: 6 }}>Какое у вас устройство?</div>
                    <div className="btnrow">
                      <button className="btn sm" style={{ flex: 1 }} onClick={() => choosePlatform("ios")}>iPhone</button>
                      <button className="btn sm" style={{ flex: 1 }} onClick={() => choosePlatform("android")}>Android / другое</button>
                    </div>
                  </>
                ) : (
                  <button className="btn pri" disabled={pushBusy} onClick={enablePush}>
                    {pushBusy ? "…" : "Разрешить уведомления"}
                  </button>
                )}
              </>
            )}
            {pushMsg === "ios-instruction" && (
              <div className="banner b-ac" style={{ cursor: "default", marginTop: 10, display: "block" }}>
                <b>На iPhone нужно добавить приложение на экран «Домой»:</b>
                <div style={{ fontSize: 12.5, marginTop: 6, lineHeight: 1.6 }}>
                  1. Нажмите кнопку «Поделиться» внизу Safari (квадрат со стрелкой вверх).<br />
                  2. Выберите «На экран „Домой“».<br />
                  3. Откройте приложение с иконки на экране и снова нажмите «Разрешить уведомления».
                </div>
              </div>
            )}
            {pushMsg && pushMsg !== "ios-instruction" && <div className="sub" style={{ marginTop: 8 }}>{pushMsg}</div>}
          </>
        )}
      </div>

      <div className="sec-label">Когда напоминать по умолчанию</div>
      <div className="sub" style={{ marginBottom: 10 }}>
        За сколько до срока присылать напоминание — можно выбрать несколько для каждого типа. Новые события подхватят это автоматически.
      </div>
      {KINDS.map(([kind, label]) => (
        <div key={kind} className="card" style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>{label}</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {OFFSET_PRESETS.map((m) => {
              const on = (p.default_offsets[kind] || []).includes(m);
              return (
                <span key={m} onClick={() => toggleOffset(kind, m)} style={{
                  padding: "6px 12px", borderRadius: 8, fontSize: 12.5, cursor: "pointer",
                  background: on ? "var(--acbg)" : "var(--s1)",
                  border: ".5px solid " + (on ? "var(--ac)" : "var(--bd)"),
                  color: on ? "var(--ac)" : "var(--tp)" }}>
                  {on ? "✓ " : ""}{OFFSET_LABEL[m]}
                </span>
              );
            })}
          </div>
        </div>
      ))}

      <div className="sec-label">Утренняя сводка</div>
      <div className="card" style={{ marginBottom: 10 }}>
        <Toggle label="Присылать утром" sub="короткая сводка: сколько пациентов требуют внимания сегодня"
          on={p.digest_enabled} onClick={() => save({ digest_enabled: !p.digest_enabled })} />
        {p.digest_enabled && (
          <div className="row">
            <span style={{ fontSize: 13 }}>Время</span>
            <select className="input" style={{ width: 100 }} value={p.digest_hour}
              onChange={(e) => save({ digest_hour: Number(e.target.value) })}>
              {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
            </select>
          </div>
        )}
      </div>

      <div className="sec-label">Сводка по выполненному</div>
      <div className="card" style={{ marginBottom: 10 }}>
        <div className="sub" style={{ marginBottom: 8 }}>Итог, сколько задач вы закрыли — как отчёт самому себе.</div>
        <div className="row" style={{ borderTop: 0 }}>
          <span style={{ fontSize: 13 }}>Присылать</span>
          <select className="input" style={{ width: 150 }} value={p.recap_mode || "off"}
            onChange={(e) => save({ recap_mode: e.target.value })}>
            <option value="off">Не присылать</option>
            <option value="daily">Каждый вечер</option>
            <option value="weekly">Раз в неделю</option>
          </select>
        </div>
        {p.recap_mode && p.recap_mode !== "off" && (
          <div className="row">
            <span style={{ fontSize: 13 }}>Время</span>
            <div style={{ display: "flex", gap: 8 }}>
              {p.recap_mode === "weekly" && (
                <select className="input" value={p.recap_weekday} onChange={(e) => save({ recap_weekday: Number(e.target.value) })}>
                  {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((d, i) => <option key={i} value={i}>{d}</option>)}
                </select>
              )}
              <select className="input" style={{ width: 100 }} value={p.recap_hour}
                onChange={(e) => save({ recap_hour: Number(e.target.value) })}>
                {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
              </select>
            </div>
          </div>
        )}
      </div>

      <div className="sec-label">Тихие часы</div>
      <div className="card" style={{ marginBottom: 10 }}>
        <div className="sub" style={{ marginBottom: 8 }}>В это время напоминания не беспокоят — придут, как тихие часы закончатся.</div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select className="input" value={p.quiet_hours_start} onChange={(e) => save({ quiet_hours_start: Number(e.target.value) })}>
            {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
          </select>
          <span className="sub">—</span>
          <select className="input" value={p.quiet_hours_end} onChange={(e) => save({ quiet_hours_end: Number(e.target.value) })}>
            {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
          </select>
        </div>
      </div>

      <div className="sec-label">Повтор напоминания</div>
      <div className="card" style={{ marginBottom: 10 }}>
        <Toggle label="Напомнить ещё раз, если не открыл" sub="один повтор, чтобы не пропустить важное"
          on={p.escalation_enabled} onClick={() => save({ escalation_enabled: !p.escalation_enabled })} />
        {p.escalation_enabled && (
          <div className="row">
            <span style={{ fontSize: 13 }}>Через</span>
            <select className="input" style={{ width: 110 }} value={p.escalation_minutes}
              onChange={(e) => save({ escalation_minutes: Number(e.target.value) })}>
              {[5, 10, 15, 30, 60].map((m) => <option key={m} value={m}>{m} мин</option>)}
            </select>
          </div>
        )}
      </div>

      <div className="sec-label">Что присылать пушем (когда включите уведомления)</div>
      <div className="card">
        <Toggle label="Приёмы" on={p.push.appointment} onClick={() => save({ push: { ...p.push, appointment: !p.push.appointment } })} />
        <Toggle label="Просроченные контроли" on={p.push.control} onClick={() => save({ push: { ...p.push, control: !p.push.control } })} />
        <Toggle label="Задачи" on={p.push.task} onClick={() => save({ push: { ...p.push, task: !p.push.task } })} />
        <Toggle label="Звонки" on={p.push.call} onClick={() => save({ push: { ...p.push, call: !p.push.call } })} />
        <Toggle label="Подписка/оплата" on={p.push.billing} onClick={() => save({ push: { ...p.push, billing: !p.push.billing } })} />
      </div>
      <div className="sub" style={{ marginTop: 8 }}>
        Пуш-уведомления (на телефон, даже когда приложение закрыто) — появятся отдельным шагом. Здесь сохраняются ваши предпочтения заранее.
      </div>
    </>
  );
}
