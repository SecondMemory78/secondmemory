import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Spinner, Empty } from "../components/Loading";

const ICON = { overdue: "ti-clock-exclamation", limit: "ti-gauge", trigger: "ti-filter", ocr: "ti-file-text", billing: "ti-credit-card", security: "ti-shield-lock", info: "ti-info-circle" };

export default function Notifications() {
  const nav = useNavigate();
  const [items, setItems] = useState(null);   // null = грузится
  function load() { api.notifications().then((r) => setItems(r.items || [])).catch(() => setItems([])); }
  useEffect(() => { load(); }, []);

  async function open(n) {
    if (!n.read) await api.markNotifRead(n.id);
    if (n.patient_id) nav(`/patients/${n.patient_id}`);
    else load();
  }
  async function readAll() { await api.readAllNotifs(); load(); }

  return (
    <>
      <div className="hd">
        <div className="ttl">Уведомления</div>
        {(items || []).some((n) => !n.read) && <span className="acc" style={{ fontSize: 12, cursor: "pointer" }} onClick={readAll}>прочитать всё</span>}
      </div>

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
