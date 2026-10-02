import { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";
import { api } from "../api";

// Движок точечных подсказок «в момент первого использования».
// Одна загрузка увиденных ключей на сессию (tips_seen), дальше — только локально.
// Экраны вызывают show(key) при первом реальном столкновении с функцией;
// dismiss(key) помечает подсказку увиденной на бэке (идемпотентно) и гасит её.

const TipsCtx = createContext(null);

export function TipsProvider({ enabled = true, children }) {
  const [seen, setSeen] = useState(null);        // null = ещё не загружено; Set<string> после
  const [queue, setQueue] = useState([]);        // очередь подсказок; показываем первую
  const requested = useRef(new Set());           // какие show() уже запрашивались в этой сессии
  const active = queue[0] || null;

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
    // Встаём в очередь, а не перебиваем открытую. Раньше вторая подсказка,
    // запрошенная при той же перерисовке, терялась навсегда — экран уже
    // отметил её как запрошенную, а показать было некому.
    setQueue((q) => (q.includes(key) ? q : [...q, key]));
  }, [enabled, seen]);

  // Погасить: пометить увиденной локально и на бэке.
  const dismiss = useCallback((key) => {
    setSeen((s) => { const n = new Set(s); n.add(key); return n; });
    setQueue((q) => q.filter((k) => k !== key));   // следующая из очереди покажется сама
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
