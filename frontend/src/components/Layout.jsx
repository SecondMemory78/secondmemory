import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import HeaderSearch from "./HeaderSearch";
import OutboxBadge from "./OutboxBadge";
import { api } from "../api";

const TABS = [
  { to: "/", end: true, icon: "ti-home", label: "Главная" },
  { to: "/calendar", icon: "ti-calendar-month", label: "Календарь" },
  { to: "/patients", icon: "ti-users", label: "Пациенты" },
  { to: "/tasks", icon: "ti-checkbox", label: "Задачи" },
  { to: "/more", icon: "ti-dots", label: "Ещё" },
];

// глобальный поиск виден на основных вкладках, кроме «Ещё»
const SEARCH_ON = ["/", "/calendar", "/patients", "/tasks"];

export default function Layout() {
  const nav = useNavigate();
  const loc = useLocation();
  const showSearch = SEARCH_ON.includes(loc.pathname);
  const [unread, setUnread] = useState(0);
  useEffect(() => { api.notifications().then((r) => setUnread(r.unread || 0)).catch(() => {}); }, [loc.pathname]);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><i className="ti ti-stethoscope" /> Вторая память</div>
        {TABS.map((t) => (
          <NavLink key={t.to} to={t.to} end={t.end}>
            <i className={"ti " + t.icon} /> {t.label}
          </NavLink>
        ))}
        <button className="btn pri block startbtn" onClick={() => nav("/start-visit")}>
          <i className="ti ti-player-play" /> Начать приём
        </button>
      </aside>

      <div className="app">
        <header className="topbar-search" style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ flex: 1 }}>{showSearch && <HeaderSearch />}</div>
          <div style={{ position: "relative", cursor: "pointer", padding: 4 }} onClick={() => nav("/notifications")} title="Уведомления">
            <i className="ti ti-bell" style={{ fontSize: 20, color: "var(--tp)" }} />
            {unread > 0 && (
              <span style={{ position: "absolute", top: -2, right: -2, minWidth: 16, height: 16, padding: "0 4px", borderRadius: 8, background: "var(--dn)", color: "#fff", fontSize: 10, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 600 }}>
                {unread > 9 ? "9+" : unread}
              </span>
            )}
          </div>
        </header>
        <div className="scroll">
          <Outlet />
        </div>
        <OutboxBadge />
        <nav className="tabbar">
          {TABS.map((t) => (
            <NavLink key={t.to} to={t.to} end={t.end}>
              <i className={"ti " + t.icon} />
              <span>{t.label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
