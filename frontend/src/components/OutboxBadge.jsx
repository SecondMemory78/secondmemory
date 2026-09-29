import { useEffect, useState } from "react";
import { count, flush } from "../lib/outbox";

// Плашка «N ожидают отправки» + офлайн-статус. Появляется, только когда есть что
// показать (очередь непуста или нет сети). Тап — попытка отправить сейчас.
export default function OutboxBadge() {
  const [n, setN] = useState(0);
  const [online, setOnline] = useState(navigator.onLine);

  useEffect(() => {
    let alive = true;
    const refresh = () => count().then((c) => { if (alive) setN(c); }).catch(() => {});
    refresh();
    const onChange = () => refresh();
    const onOnline = () => { setOnline(true); refresh(); };
    const onOffline = () => { setOnline(false); refresh(); };
    window.addEventListener("sm:outbox-changed", onChange);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    const t = setInterval(refresh, 5000);   // подстраховка
    return () => {
      alive = false; clearInterval(t);
      window.removeEventListener("sm:outbox-changed", onChange);
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  if (n === 0 && online) return null;   // всё отправлено и есть сеть — ничего не показываем

  return (
    <div className="outbox-badge" onClick={() => flush()}
         title={online ? "Нажмите, чтобы отправить сейчас" : "Нет сети — отправим автоматически"}>
      <i className={"ti " + (online ? "ti-cloud-upload" : "ti-cloud-off")} />
      {n > 0
        ? <span>{online ? `Отправка… (${n})` : `Ожидают отправки: ${n}`}</span>
        : <span>Нет сети</span>}
    </div>
  );
}
