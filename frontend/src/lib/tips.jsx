import { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { api } from "../api";

// Движок точечных подсказок «в момент первого использования».
// Одна загрузка увиденных ключей на сессию (tips_seen), дальше — только локально.
// Экраны вызывают show(key) при первом реальном столкновении с функцией;
// dismiss(key) помечает подсказку увиденной на бэке (идемпотентно) и гасит её.

const TipsCtx = createContext(null);

export function TipsProvider({ enabled = true, children }) {
  const [seen, setSeen] = useState(null);        // null = ещё не загружено; Set<string> после
  const [active, setActive] = useState(null);    // ключ показываемой сейчас подсказки (одна за раз)
  const requested = useRef(new Set());           // какие show() уже запрашивались в этой сессии

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    api.onboardingProgress()
      .then((p) => { if (alive) setSeen(new Set(p.tips_seen || [])); })
      .catch(() => { if (alive) setSeen(new Set()); });   // при ошибке не мешаем работе
    return () => { alive = false; };
  }, [enabled]);

  // Показать подсказку, если она ещё не видена и сейчас ничего не показывается.
  const show = useCallback((key) => {
    if (!enabled || !seen) return;               // ещё не загрузились — попробуют снова при перерисовке
    if (seen.has(key) || requested.current.has(key)) return;
    requested.current.add(key);
    setActive((cur) => cur || key);              // не перебиваем уже открытую подсказку
  }, [enabled, seen]);

  // Погасить: пометить увиденной локально и на бэке.
  const dismiss = useCallback((key) => {
    setSeen((s) => { const n = new Set(s); n.add(key); return n; });
    setActive((cur) => (cur === key ? null : cur));
    api.tipSeen(key);                            // .catch внутри api — не роняет UI
  }, []);

  return (
    <TipsCtx.Provider value={{ show, dismiss, active, ready: seen != null }}>
      {children}
    </TipsCtx.Provider>
  );
}

export function useTips() {
  const ctx = useContext(TipsCtx);
  // Безопасный no-op вне провайдера (например, на экране логина) — чтобы вызовы show() не падали.
  return ctx || { show: () => {}, dismiss: () => {}, active: null, ready: false };
}
