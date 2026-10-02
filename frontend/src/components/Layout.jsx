import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import HeaderSearch from "./HeaderSearch";
import OutboxBadge from "./OutboxBadge";
import AnnouncementBar from "./AnnouncementBar";
import AssistantFab from "./AssistantFab";
import { api } from "../api";
import { getDoctor } from "../lib/auth";

const TABS = [
  { to: "/", end: true, icon: "ti-home", label: "Главная" },
  // Календарь убран из вкладок: он открывается с Главной полоской недели в
  // одно касание, а блокнот врач открывает чаще. Решено 01.10.2026.
  { to: "/blocknote", icon: "ti-notebook", label: "Блокнот" },
  { to: "/patients", icon: "ti-users", label: "Пациенты" },
  // Задачи остаются отдельной вкладкой: они срочные, и прятать их на касание
  // глубже нельзя. Внутри «Блокнота» они тоже есть — это один и тот же список,
  // просто рядом с заметками, из которых задачи и рождаются.
  { to: "/tasks", icon: "ti-checkbox", label: "Задачи" },
  { to: "/more", icon: "ti-dots", label: "Ещё" },
];

// Раздел «Работа». На телефоне он живёт в «Ещё» — там нет места для восьми
// пунктов внизу. На компьютере места полно, и прятать рабочие разделы в
// «Ещё» незачем: врач за столом открывает заметки и списки постоянно.
const WORK = [
  { to: "/calendar", icon: "ti-calendar-month", label: "Календарь" },
  { to: "/lists", icon: "ti-list-check", label: "Списки пациентов" },
  { to: "/triggers", icon: "ti-filter", label: "Автослежение" },
  { to: "/assistant-log", icon: "ti-history", label: "Что сделал ассистент" },
];

// глобальный поиск виден на основных вкладках, кроме «Ещё»
const SEARCH_ON = ["/", "/calendar", "/patients", "/tasks", "/blocknote"];

export default function Layout() {
  const nav = useNavigate();
  const loc = useLocation();
  const showSearch = SEARCH_ON.includes(loc.pathname);
  const [unread, setUnread] = useState(0);
  // Просроченное на вкладке «Задачи»: видно, не заходя внутрь.
  const [overdue, setOverdue] = useState(0);
  useEffect(() => { api.dashboard().then((d) => setOverdue(d.overdue_reminders || 0)).catch(() => {}); }, [loc.pathname]);
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

        <div className="side-sec">Работа</div>
        {WORK.map((t) => (
          <NavLink key={t.to} to={t.to}>
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
          <div className="hd-bell" onClick={() => nav("/notifications")} title="Уведомления">
            {/* Счётчик крепится к самому значку, а не к зоне нажатия: зона
                40×40, значок 20×20, и привязка к её углу отрывала кружок от
                колокольчика. */}
            <span className="bell-ico">
              <i className="ti ti-bell" style={{ fontSize: 20, color: "var(--tp)" }} />
              {unread > 0 && (
                <span className="bell-badge">{unread > 9 ? "9+" : unread}</span>
              )}
            </span>
          </div>
        </header>
        <div className="scroll">
          <AnnouncementBar />
          {getDoctor()?.is_demo && (
            <div className="banner" style={{ background: "var(--wnbg)", color: "var(--tp)", marginBottom: 10 }}>
              <i className="ti ti-eye wn" /> Демо-режим: это ваша личная копия для просмотра.
              Через час она удалится, ассистент отключён.
            </div>
          )}
          <Outlet />
        </div>
        {/* Ассистент есть и на Главной: раньше там был отдельный большой микрофон,
            теперь вход в ассистента один и в одном месте на всех экранах. */}
        {loc.pathname !== "/more" && <AssistantFab />}
        <OutboxBadge />
        <nav className="tabbar">
          {TABS.map((t) => (
            <NavLink key={t.to} to={t.to} end={t.end}>
              <span className="tab-ico">
                <i className={"ti " + t.icon} />
                {t.to === "/tasks" && overdue > 0 && (
                  <span className="tab-dot">{overdue > 9 ? "9+" : overdue}</span>
                )}
              </span>
              <span>{t.label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
