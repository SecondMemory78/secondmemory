import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Lock from "./pages/Lock";
import Home from "./pages/Home";
import Calendar from "./pages/Calendar";
import Week from "./pages/Week";
import NewEntry from "./pages/NewEntry";
import Search from "./pages/Search";
import SupportChat from "./pages/SupportChat";
import Triggers from "./pages/Triggers";
import Help from "./pages/Help";
import Notifications from "./pages/Notifications";
import Patients from "./pages/Patients";
import PatientDetail from "./pages/PatientDetail";
import Reminders from "./pages/Reminders";
import More from "./pages/More";
import StartVisit from "./pages/StartVisit";
import Billing from "./pages/Billing";
import PhotoBatch from "./pages/PhotoBatch";
import Dictation from "./pages/Dictation";
import NotifySettings from "./pages/NotifySettings";
import Toast from "./components/Toast";
import ConfirmDialog from "./components/ConfirmDialog";
import { api } from "./api";
import { auth as authApi } from "./api";
import { getToken, clearSession, quickUnlockEnabled } from "./lib/auth";

if (typeof localStorage !== "undefined" && localStorage.getItem("theme") === "dark") {
  document.documentElement.setAttribute("data-theme", "dark");
}

export default function App() {
  const [token, setToken] = useState(getToken());
  const [unlocked, setUnlocked] = useState(!quickUnlockEnabled());
  const [sub, setSub] = useState(null);

  useEffect(() => {
    if (token && unlocked) api.billingStatus().then(setSub).catch(() => setSub(null));
  }, [token, unlocked]);

  // авто-блокировка по бездействию: если задан PIN/биометрия — через N минут без
  // действий возвращаем на экран разблокировки (защита оставленного устройства)
  useEffect(() => {
    if (!token || !unlocked || !quickUnlockEnabled()) return;
    const mins = Number(localStorage.getItem("sm_autolock_min") || "5");
    if (!mins) return;
    let timer;
    const reset = () => { clearTimeout(timer); timer = setTimeout(() => setUnlocked(false), mins * 60000); };
    const evs = ["mousedown", "keydown", "touchstart", "scroll", "visibilitychange"];
    evs.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    reset();
    return () => { clearTimeout(timer); evs.forEach((e) => window.removeEventListener(e, reset)); };
  }, [token, unlocked]);

  async function logout() {
    await authApi.logout();
    clearSession();
    setToken(""); setUnlocked(true); setSub(null);
  }

  if (!token) {
    return <Login onAuthed={() => { setToken(getToken()); setUnlocked(!quickUnlockEnabled()); }} />;
  }
  if (!unlocked) {
    return <Lock onUnlock={() => setUnlocked(true)} onLogout={logout} />;
  }

  const needsBilling = sub && !sub.active && !sub.is_demo;

  return (
    <>
    <Toast />
    <ConfirmDialog />
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={needsBilling ? <Navigate to="/billing" replace /> : <Home />} />
          <Route path="/calendar" element={<Calendar />} />
          <Route path="/week/:offset" element={<Week />} />
          <Route path="/new-entry/:date" element={<NewEntry />} />
          <Route path="/search" element={<Search />} />
          <Route path="/support" element={<SupportChat />} />
          <Route path="/triggers" element={<Triggers />} />
          <Route path="/help" element={<Help />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/billing" element={<Billing />} />
          <Route path="/photo-batch" element={<PhotoBatch />} />
          <Route path="/dictation" element={<Dictation />} />
          <Route path="/notify-settings" element={<NotifySettings />} />
          <Route path="/patients" element={<Patients />} />
          <Route path="/patients/:id" element={<PatientDetail />} />
          <Route path="/tasks" element={<Reminders />} />
          <Route path="/more" element={<More onLogout={logout} />} />
          <Route path="/start-visit" element={<StartVisit />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
    </>
  );
}
