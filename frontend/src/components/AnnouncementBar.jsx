import { useEffect, useState } from "react";
import { api } from "../api";

// Объявления из админки: техработы, важное, новости.
// Полоса вверху на всех экранах; закрыть можно, если тип это разрешает.
const STYLE = {
  maintenance: { bg: "var(--wnbg)", fg: "var(--wn)", icon: "ti-tool" },
  important:   { bg: "var(--dnbg)", fg: "var(--dn)", icon: "ti-alert-triangle" },
  news:        { bg: "var(--acbg)", fg: "var(--ac)", icon: "ti-speakerphone" },
};

export default function AnnouncementBar() {
  const [items, setItems] = useState([]);

  function load() {
    api.announcements().then((r) => setItems(r.items || [])).catch(() => setItems([]));
  }
  useEffect(() => {
    load();
    const t = setInterval(load, 5 * 60 * 1000);   // раз в 5 минут — вдруг объявили новое
    return () => clearInterval(t);
  }, []);

  async function close(a) {
    setItems((prev) => prev.filter((x) => x.id !== a.id));   // сразу, без ожидания
    await api.dismissAnnouncement(a.id).catch(() => load());
  }

  if (!items.length) return null;

  return (
    <>
      {items.map((a) => {
        const st = STYLE[a.kind] || STYLE.news;
        return (
          <div key={a.id} className="ann-bar" style={{ background: st.bg }}>
            <i className={"ti " + st.icon} style={{ color: st.fg, marginTop: 1 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 500 }}>{a.title}</div>
              {a.text && <div className="sub" style={{ marginTop: 2 }}>{a.text}</div>}
            </div>
            {a.dismissible ? (
              <i className="ti ti-x muted" style={{ cursor: "pointer" }}
                 title="Скрыть" onClick={() => close(a)} />
            ) : (
              <span className="sub" style={{ fontSize: 11 }}>{a.kind_label}</span>
            )}
          </div>
        );
      })}
    </>
  );
}
