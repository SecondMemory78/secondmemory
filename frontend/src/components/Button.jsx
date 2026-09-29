import { useState } from "react";

// Кнопка, которая сама показывает спиннер и блокируется, пока выполняется async onClick.
// Достаточно передать async-обработчик — состояние «в процессе» отслеживается автоматически.
export default function Button({ children, onClick, busy: busyProp, className = "btn", disabled, ...rest }) {
  const [busy, setBusy] = useState(false);
  async function handle(e) {
    if (busy || disabled) return;
    const r = onClick?.(e);
    if (r && typeof r.then === "function") {
      setBusy(true);
      try { await r; } finally { setBusy(false); }
    }
  }
  const isBusy = busyProp ?? busy;
  return (
    <button className={className} disabled={isBusy || disabled} onClick={handle} {...rest}>
      {isBusy ? <span className="spinner sm" style={{ display: "inline-block", verticalAlign: "middle" }} /> : children}
    </button>
  );
}
