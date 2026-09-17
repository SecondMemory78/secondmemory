import { useEffect, useState } from "react";

export default function ConfirmDialog() {
  const [c, setC] = useState(null);
  useEffect(() => {
    function on(e) { setC(e.detail); }
    window.addEventListener("sm:confirm", on);
    return () => window.removeEventListener("sm:confirm", on);
  }, []);
  if (!c) return null;
  function done(v) { c.resolve(v); setC(null); }
  return (
    <div className="modal-ov" onClick={() => done(false)}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">{c.title || "Подтвердите действие"}</div>
        {c.message && <div className="modal-msg">{c.message}</div>}
        <div className="btnrow" style={{ marginTop: 16 }}>
          <button className="btn" style={{ flex: 1 }} onClick={() => done(false)}>{c.cancelText || "Отмена"}</button>
          <button className={"btn " + (c.danger ? "dng-solid" : "pri")} style={{ flex: 1 }} onClick={() => done(true)}>
            {c.confirmText || "Подтвердить"}
          </button>
        </div>
      </div>
    </div>
  );
}
