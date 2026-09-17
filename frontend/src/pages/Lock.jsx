import { useState } from "react";
import { checkPin, hasBiometric, unlockBiometric, getDoctor } from "../lib/auth";

export default function Lock({ onUnlock, onLogout }) {
  const [pin, setPin] = useState("");
  const [err, setErr] = useState("");
  const doctor = getDoctor();

  async function push(d) {
    const v = (pin + d).slice(0, 4);
    setPin(v); setErr("");
    if (v.length === 4) {
      if (await checkPin(v)) onUnlock();
      else { setErr("Неверный PIN"); setTimeout(() => setPin(""), 250); }
    }
  }
  async function bio() {
    if (await unlockBiometric()) onUnlock();
    else setErr("Биометрия недоступна — введите PIN");
  }

  return (
    <div className="app">
      <div className="scroll" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ width: 56, height: 56, borderRadius: 16, background: "var(--acbg)", color: "var(--act)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 26, marginBottom: 14 }}>
          <i className="ti ti-lock" />
        </div>
        <h1 style={{ fontSize: 18 }}>{doctor.full_name || "Вход"}</h1>
        <div className="muted" style={{ fontSize: 12, margin: "6px 0 22px" }}>{err || "Введите PIN для входа"}</div>

        <div style={{ display: "flex", gap: 10, marginBottom: 24 }}>
          {[0, 1, 2, 3].map((i) => (
            <div key={i} style={{ width: 13, height: 13, borderRadius: "50%", border: "1.5px solid var(--bds)", background: i < pin.length ? "var(--ac)" : "transparent", borderColor: i < pin.length ? "var(--ac)" : "var(--bds)" }} />
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,64px)", gap: 14 }}>
          {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((d) => <Key key={d} d={d} onTap={() => push(String(d))} />)}
          {hasBiometric() ? <Key d={<i className="ti ti-fingerprint" />} onTap={bio} /> : <div />}
          <Key d={0} onTap={() => push("0")} />
          <Key d={<i className="ti ti-backspace" />} onTap={() => setPin(pin.slice(0, -1))} />
        </div>

        <button className="btn block" style={{ marginTop: 26, maxWidth: 220 }} onClick={onLogout}>Выйти из аккаунта</button>
      </div>
    </div>
  );
}

function Key({ d, onTap }) {
  return (
    <div onClick={onTap} style={{ width: 64, height: 64, borderRadius: "50%", background: "var(--s1)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22, cursor: "pointer" }}>
      {d}
    </div>
  );
}
