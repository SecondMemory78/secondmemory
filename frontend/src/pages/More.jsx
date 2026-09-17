import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import Toggle from "../components/Toggle";
import { confirmAction } from "../lib/confirm";
import { getDoctor, hasPin, setPin, clearPin, hasBiometric, biometricSupported, registerBiometric } from "../lib/auth";

function setTheme(dark) {
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch (e) {}
}

export default function More({ onLogout }) {
  const nav = useNavigate();
  const [unread, setUnread] = useState(0);
  useEffect(() => { api.supportThread().then((r) => setUnread(r.unread || 0)).catch(() => {}); }, []);
  const [dark, setDark] = useState(
    (typeof localStorage !== "undefined" && localStorage.getItem("theme") === "dark") || false
  );
  const [pinSet, setPinSet] = useState(hasPin());
  const [autolock, setAutolock] = useState(localStorage.getItem("sm_autolock_min") || "5");
  const [bioSet, setBioSet] = useState(hasBiometric());
  const [pinForm, setPinForm] = useState(false);
  const [pin1, setPin1] = useState("");
  const [pin2, setPin2] = useState("");
  const [pinErr, setPinErr] = useState("");
  const [push, setPush] = useState(true);
  const [track, setTrack] = useState(true);
  const [prof, setProf] = useState(null);
  const [usage, setUsage] = useState(null);
  const [sub, setSub] = useState(null);
  const [sessions, setSessions] = useState(null);
  useEffect(() => { api.sessions().then(setSessions).catch(() => setSessions([])); }, []);
  async function revokeDevice(id) {
    if (!(await confirmAction({ title: "Выйти с этого устройства?", danger: true, confirmText: "Выйти" }))) return;
    await api.revokeSession(id);
    setSessions(await api.sessions().catch(() => []));
  }
  useEffect(() => { api.usageToday().then(setUsage).catch(() => {}); }, []);
  useEffect(() => { api.billingStatus().then(setSub).catch(() => {}); }, []);
  const [doctor, setDoctorState] = useState(getDoctor());
  async function saveProfile() {
    await api.saveSettings({ full_name: prof.full_name, specialty: prof.specialty });
    const st = await api.settings();
    const upd = { ...getDoctor(), full_name: st.full_name, specialty: st.specialty };
    try { localStorage.setItem("sm_doctor", JSON.stringify(upd)); } catch (e) {}
    setDoctorState(upd); setProf(null);
  }
  useEffect(() => {
    api.settings().then((st) => { setPush(st.notify_push !== false); setTrack(st.notify_tracking !== false); }).catch(() => {});
  }, []);
  function togglePush() { const v = !push; setPush(v); api.saveSettings({ notify_push: v }).catch(() => {}); }
  function toggleTrack() { const v = !track; setTrack(v); api.saveSettings({ notify_tracking: v }).catch(() => {}); }

  function toggleTheme() { const v = !dark; setDark(v); setTheme(v); }
  async function exportIcs() {
    try {
      const r = await fetch("/api/calendar/export.ics", { headers: { Authorization: `Bearer ${localStorage.getItem("sm_token") || ""}` } });
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = "second-memory.ics"; a.click();
      URL.revokeObjectURL(url);
    } catch { alert("Не удалось выгрузить календарь."); }
  }
  function savePin() {
    if (!/^\d{4}$/.test(pin1)) { setPinErr("PIN — 4 цифры"); return; }
    if (pin1 !== pin2) { setPinErr("PIN не совпадает"); return; }
    setPin(pin1); setPinSet(true); setPinForm(false); setPin1(""); setPin2(""); setPinErr("");
  }
  async function enableBio() {
    const ok = await registerBiometric();
    setBioSet(ok);
    if (!ok) alert("Биометрия недоступна на этом устройстве (нужен https или встроенный сканер). Останется вход по PIN.");
  }

  const initials = (doctor.full_name || "Врач").split(" ").map((w) => w[0]).slice(0, 2).join("");

  return (
    <>
      <div className="hd"><div className="ttl">Ещё</div></div>

      <div className="card" style={{ marginBottom: 8 }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <div className="avatar" style={{ width: 44, height: 44 }}>{initials}</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 500 }}>{doctor.full_name || "Врач"}</div>
            <div className="sub">{[doctor.specialty, doctor.email].filter(Boolean).join(" · ")}</div>
          </div>
          <i className="ti ti-pencil muted" style={{ cursor: "pointer" }} title="Изменить профиль"
            onClick={() => setProf(prof ? null : { full_name: doctor.full_name || "", specialty: doctor.specialty || "" })} />
        </div>
        {prof && (
          <div style={{ marginTop: 10 }}>
            <input className="input" placeholder="ФИО" value={prof.full_name} onChange={(e) => setProf({ ...prof, full_name: e.target.value })} style={{ marginBottom: 8 }} />
            <input className="input" placeholder="Специальность" value={prof.specialty} onChange={(e) => setProf({ ...prof, specialty: e.target.value })} style={{ marginBottom: 8 }} />
            <div className="btnrow">
              <button className="btn sm" style={{ flex: 1 }} onClick={() => setProf(null)}>Отмена</button>
              <button className="btn pri sm" style={{ flex: 1 }} onClick={saveProfile}>Сохранить</button>
            </div>
          </div>
        )}
      </div>

      {usage && (
        <>
          <div className="sec-label">Расход сегодня</div>
          <div className="card">
            {["ocr", "stt", "llm"].map((k) => {
              const u = usage[k]; if (!u) return null;
              const pct = Math.min(100, Math.round((u.used / u.limit) * 100));
              const col = pct >= 100 ? "var(--dn)" : pct >= 80 ? "var(--wn)" : "var(--ac)";
              return (
                <div key={k} style={{ marginBottom: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 4 }}>
                    <span>{u.label}</span>
                    <span className="mono" style={{ color: col }}>{u.used} / {u.limit}</span>
                  </div>
                  <div style={{ height: 6, borderRadius: 4, background: "var(--s1)", overflow: "hidden" }}>
                    <div style={{ width: pct + "%", height: "100%", background: col, borderRadius: 4 }} />
                  </div>
                </div>
              );
            })}
            <div className="sub" style={{ marginTop: 2 }}>Суточные лимиты защищают от перерасхода на распознавании. Обнуляются в полночь (МСК).</div>
          </div>
        </>
      )}

      <div className="sec-label">Подписка</div>
      <div className="row" onClick={() => nav("/billing")} style={{ cursor: "pointer" }}>
        <div>
          <div style={{ fontSize: 13 }}>Тариф и оплата</div>
          <div className="sub" style={{ marginTop: 2 }}>
            {sub == null ? "…" : sub.is_demo ? "демо-доступ" : sub.active
              ? `активна · осталось ${sub.days_left} дн.` : "не активна — оформить"}
          </div>
        </div>
        <i className="ti ti-chevron-right muted" />
      </div>

      <div className="sec-label">Устройства</div>
      <div className="card">
        {sessions === null && <div className="sub">Загрузка…</div>}
        {sessions !== null && sessions.length === 0 && <div className="sub">Нет активных сессий.</div>}
        {(sessions || []).map((d) => (
          <div key={d.id} className="row">
            <div>
              <div style={{ fontSize: 13 }}>
                {d.current ? "Это устройство" : (d.device_id || "Устройство")}
                {d.current && <span className="acc" style={{ fontSize: 11, marginLeft: 6 }}>● активно</span>}
              </div>
              <div className="sub">{(d.user_agent || "").slice(0, 40) || "вход " + d.created_at.slice(0, 10)}</div>
            </div>
            {!d.current && (
              <button className="btn sm dng-solid" onClick={() => revokeDevice(d.id)}>Выйти</button>
            )}
          </div>
        ))}
      </div>

      <div className="sec-label">Безопасность входа</div>
      <div className="row">
        <div>
          <div style={{ fontSize: 13 }}>Авто-блокировка</div>
          <div className="sub" style={{ marginTop: 2 }}>вернуться к PIN/биометрии после простоя</div>
        </div>
        <select className="input" style={{ width: 130 }} value={autolock}
          onChange={(e) => { setAutolock(e.target.value); localStorage.setItem("sm_autolock_min", e.target.value); }}>
          <option value="0">Выключено</option>
          <option value="1">1 минута</option>
          <option value="5">5 минут</option>
          <option value="15">15 минут</option>
          <option value="30">30 минут</option>
        </select>
      </div>
      <div className="row" onClick={() => setPinForm(!pinForm)} style={{ cursor: "pointer" }}>
        <div>
          <div style={{ fontSize: 13 }}>Быстрый вход по PIN</div>
          <div className="sub" style={{ marginTop: 2 }}>{pinSet ? "PIN установлен" : "не задан"}</div>
        </div>
        <i className={"ti " + (pinSet ? "ti-check acc" : "ti-chevron-right muted")} />
      </div>
      {pinForm && (
        <div className="card" style={{ marginBottom: 8 }}>
          <input className="input" inputMode="numeric" maxLength={4} placeholder="Новый PIN (4 цифры)"
            value={pin1} onChange={(e) => { setPin1(e.target.value.replace(/\D/g, "")); setPinErr(""); }}
            style={{ marginBottom: 8, letterSpacing: 6, textAlign: "center" }} />
          <input className="input" inputMode="numeric" maxLength={4} placeholder="Повторите PIN"
            value={pin2} onChange={(e) => { setPin2(e.target.value.replace(/\D/g, "")); setPinErr(""); }}
            onKeyDown={(e) => e.key === "Enter" && savePin()}
            style={{ marginBottom: 8, letterSpacing: 6, textAlign: "center" }} />
          {pinErr && <div className="sub dng" style={{ marginBottom: 8 }}>{pinErr}</div>}
          <button className="btn pri block" onClick={savePin}>Сохранить PIN</button>
          {pinSet && <button className="btn block" style={{ marginTop: 6 }} onClick={() => { clearPin(); setPinSet(false); setPinForm(false); }}>Убрать PIN</button>}
        </div>
      )}
      {biometricSupported() && (
        <div className="row" onClick={enableBio} style={{ cursor: "pointer" }}>
          <div>
            <div style={{ fontSize: 13 }}>Вход по биометрии</div>
            <div className="sub" style={{ marginTop: 2 }}>{bioSet ? "включена" : "Face ID / отпечаток"}</div>
          </div>
          <i className={"ti " + (bioSet ? "ti-check acc" : "ti-fingerprint muted")} />
        </div>
      )}

      <div className="sec-label">Вид</div>
      <Toggle label="Тёмная тема" on={dark} onClick={toggleTheme} />

      <div className="sec-label">Календарь</div>
      <div className="row">
        <div>
          <div style={{ fontSize: 13 }}>Экспорт приёмов (.ics)</div>
          <div className="sub" style={{ marginTop: 2 }}>добавить в любой календарь на устройстве</div>
        </div>
        <button className="btn sm" onClick={exportIcs}>Скачать</button>
      </div>
      <div className="sub" style={{ marginTop: 4, marginBottom: 8 }}>
        Прямую синхронизацию с Google не делаем: данные пациентов нельзя выгружать во внешнее облако (152-ФЗ). Файл .ics вы добавляете в свой календарь сами.
      </div>

      <div className="sec-label">Уведомления</div>
      <div className="row" onClick={() => nav("/notify-settings")} style={{ cursor: "pointer" }}>
        <div>
          <div style={{ fontSize: 13 }}>Напоминания и тихие часы</div>
          <div className="sub" style={{ marginTop: 2 }}>когда напоминать, утренняя сводка, повтор</div>
        </div>
        <i className="ti ti-chevron-right muted" />
      </div>
      <div className="row" onClick={() => nav("/triggers")} style={{ cursor: "pointer" }}>
        <div>
          <div style={{ fontSize: 13 }}>Автослежение (триггеры)</div>
          <div className="sub" style={{ marginTop: 2 }}>следить за порогами и заводить контроли</div>
        </div>
        <i className="ti ti-chevron-right muted" />
      </div>
      <Toggle label="Push при распознавании" sub="документ готов или требует пересъёмки" on={push} onClick={togglePush} />
      <Toggle label="Автослежение по фильтрам" sub="уведомлять о новых совпадениях" on={track} onClick={toggleTrack} />

      <div className="sec-label">Данные</div>
      <label className="row" style={{ cursor: "pointer" }}>
        <div>
          <div style={{ fontSize: 13 }}>Импорт календаря из CSV</div>
          <div className="sub" style={{ marginTop: 2 }}>колонки: date, time, patient, reason, kind</div>
        </div>
        <i className="ti ti-file-upload muted" />
        <input type="file" accept=".csv,text/csv" style={{ display: "none" }} onChange={async (e) => {
          const f = e.target.files?.[0]; if (!f) return;
          const r = await api.importCalendarCsv(f);
          alert(`Импорт завершён: создано ${r.created}, пропущено ${r.skipped}` + (r.errors?.length ? "\nОшибки:\n" + r.errors.join("\n") : ""));
        }} />
      </label>
      <Nav label="Версия клинических рекомендаций" sub="обновлено 03.2026" />

      <div className="sec-label">Поддержка</div>
      <div className="row" onClick={() => nav("/support")} style={{ cursor: "pointer" }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <i className="ti ti-lifebuoy acc" style={{ fontSize: 18 }} />
          <div style={{ fontSize: 13 }}>Написать в поддержку</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {unread > 0 && <span style={{ background: "var(--dn)", color: "#fff", borderRadius: 999, fontSize: 10, padding: "1px 7px" }}>{unread}</span>}
          <i className="ti ti-chevron-right muted" />
        </div>
      </div>
      <div className="row" style={{ cursor: "pointer" }} onClick={() => nav("/help")}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <i className="ti ti-help-circle acc" style={{ fontSize: 18 }} />
          <div style={{ fontSize: 13 }}>Справка и частые вопросы</div>
        </div>
        <i className="ti ti-chevron-right muted" />
      </div>

      <button className="btn block dng" style={{ marginTop: 18 }} onClick={onLogout}>Выйти</button>
    </>
  );
}

function Nav({ label, sub }) {
  return (
    <div className="row">
      <div>
        <div style={{ fontSize: 13 }}>{label}</div>
        {sub && <div className="sub" style={{ marginTop: 2 }}>{sub}</div>}
      </div>
      <i className="ti ti-chevron-right muted" />
    </div>
  );
}
