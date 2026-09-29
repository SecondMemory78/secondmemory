import { useEffect, useState } from "react";

export default function Toast() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    function on(e) {
      const t = e.detail;
      setItems((x) => [...x.slice(-2), t]);   // не больше 3 одновременно
      setTimeout(() => setItems((x) => x.filter((i) => i.id !== t.id)), 3500);
    }
    window.addEventListener("sm:toast", on);
    return () => window.removeEventListener("sm:toast", on);
  }, []);

  const icon = (t) => t === "error" ? "ti-wifi-off" : t === "success" ? "ti-circle-check" : "ti-info-circle";
  function act(t) {
    try { t.onAction && t.onAction(); } catch (e) { /* тихо */ }
    setItems((x) => x.filter((i) => i.id !== t.id));
  }

  return (
    <div className="toast-host">
      {items.map((t) => (
        <div key={t.id} className={"toast " + (t.type || "info")}>
          <i className={"ti " + icon(t.type)} /> <span style={{ flex: 1 }}>{t.msg}</span>
          {t.label && t.onAction && (
            <span onClick={() => act(t)} style={{ fontWeight: 600, cursor: "pointer", marginLeft: 10, textDecoration: "underline" }}>{t.label}</span>
          )}
        </div>
      ))}
    </div>
  );
}
