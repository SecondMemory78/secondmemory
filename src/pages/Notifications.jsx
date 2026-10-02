import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { fmtDate } from "../lib/dates";
import { Spinner, Empty } from "../components/Loading";

const ICON = { overdue: "ti-clock-exclamation", reminder: "ti-bell", limit: "ti-gauge", trigger: "ti-filter", ocr: "ti-file-text", billing: "ti-credit-card", security: "ti-shield-lock", support: "ti-headset", digest: "ti-sun", recap: "ti-notes", info: "ti-info-circle" };

export default function Notifications() {
  const nav = useNavigate();
  const [items, setItems] = useState(null);   // null = грузится
  const [ann, setAnn] = useState([]);         // объявления администрации
  function load() {
    api.notifications()
      .then((r) => { setItems(r.items || []); setAnn(r.announcements || []); })
      .catch(() => { setItems([]); setAnn([]); });
  }
  useEffect(() => { load(); }, []);

  async function open(n) {
    if (!n.read) await api.markNotifRead(n.id);
    if (n.patient_id) { nav(`/patients/${n.patient_id}`); return; }
    // без привязки к пациенту — ведём на профильный экран по типу уведомления
    const byKind = {
      overdue: "/tasks", reminder: "/tasks",
      limit: "/billing", billing: "/billing",
      security: "/more", support: "/support",
      ocr: "/patients",
      digest: "/digest",
      recap: "/digest",
      trigger: "/triggers",
    };
    const dest = byKind[n.kind];
    if (dest) nav(dest);
    else load();
  }
  async function readAll() { await api.readAllNotifs(); load(); }

  return (
    <>
      <div className="hd">
        {/* Экран открывается колокольчиком с любого места и вкладкой не является —
            без кнопки назад отсюда можно было выйти только через нижнее меню. */}
        <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
        <div className="ttl" style={{ flex: 1 }}>Уведомления</div>
        {(items || []).some((n) => !n.read) && <span className="acc" style={{ fontSize: 12, cursor: "pointer" }} onClick={readAll}>прочитать всё</span>}
      </div>

      {ann.length > 0 && (
        <>
          <div className="sec-label" style={{ marginTop: 0 }}>От администрации</div>
          {ann.map((a) => (
            <div key={"a" + a.id} className="card" style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 13.5, fontWeight: 500 }}>
                {a.title}<span className="sub" style={{ marginLeft: 6 }}>· {a.badge}</span>
              </div>
              {a.text && <div className="sub" style={{ marginTop: 2 }}>{a.text}</div>}
              <div className="sub" style={{ marginTop: 4, fontSize: 11 }}>{fmtDate(a.created_at)}</div>
            </div>
          ))}
          <div className="sec-label">Уведомления</div>
        </>
      )}

      {items === null && <Spinner />}
      {items !== null && items.length === 0 && (
        <Empty icon="ti-bell-off" title="Пока нет уведомлений" sub="Здесь появятся просрочки, лимиты и напоминания" />
      )}

      {(items || []).map((n) => (
        <div key={n.id} className="row" style={{ cursor: "pointer", opacity: n.read ? 0.6 : 1 }} onClick={() => open(n)}>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <i className={"ti " + (ICON[n.kind] || "ti-info-circle") + (n.level === "warn" ? " dng" : " muted")} style={{ fontSize: 18, marginTop: 1 }} />
            <div>
              <div style={{ fontSize: 13.5 }}>{n.text}</div>
              <div className="sub">{new Date(n.created_at).toLocaleString("ru-RU")}</div>
            </div>
          </div>
          {!n.read && <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--ac)" }} />}
        </div>
      ))}
    </>
  );
}
