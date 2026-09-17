import { useEffect, useState } from "react";
import { auth as authApi } from "../api";
import { setSession } from "../lib/auth";

export default function Login({ onAuthed }) {
  const [mode, setMode] = useState("login");   // login | register
  const [step, setStep] = useState("form");    // form | code
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [specialty, setSpecialty] = useState("Уролог");
  const [remember, setRemember] = useState(true);
  const [code, setCode] = useState("");
  const [devCode, setDevCode] = useState("");
  const [specs, setSpecs] = useState(["Уролог"]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { authApi.specialties().then(setSpecs).catch(() => {}); }, []);

  async function submit() {
    setErr(""); setBusy(true);
    try {
      if (mode === "register") {
        if (!email || !password || !fullName) { setErr("Заполните все поля"); setBusy(false); return; }
        if (!phone.trim()) { setErr("Укажите телефон"); setBusy(false); return; }
        const r = await authApi.register({ email, password, full_name: fullName, specialty, phone });
        setDevCode(r.dev_code || ""); setStep("code");
      } else {
        const r = await authApi.login(email, password, remember);
        if (r.code_required) { setDevCode(r.dev_code || ""); setStep("code"); }
        else { setSession(r.token, r.doctor); onAuthed(); }
      }
    } catch (e) {
      setErr(e.detail || (mode === "register" ? "Не удалось зарегистрировать (почта может быть занята)" : "Неверная почта или пароль"));
    } finally { setBusy(false); }
  }

  async function verify() {
    setErr(""); setBusy(true);
    try {
      const r = await authApi.verify(email, code, remember);
      setSession(r.token, r.doctor); onAuthed();
    } catch (e) { setErr(e.detail || "Код неверен или истёк"); }
    finally { setBusy(false); }
  }

  async function demo() {
    setErr(""); setBusy(true);
    try {
      const r = await authApi.demo();
      setSession(r.token, r.doctor); onAuthed();
    } catch { setErr("Демо недоступно — проверьте, что бэкенд запущен"); }
    finally { setBusy(false); }
  }

  const [forgot, setForgot] = useState(null);   // null | "reset"
  const [token, setToken] = useState("");
  const [newPass, setNewPass] = useState("");
  const [msg, setMsg] = useState("");
  async function sendForgot() {
    setErr(""); setMsg(""); setBusy(true);
    try {
      const r = await authApi.forgot(email);
      setMsg("Если аккаунт существует, код для сброса отправлен на почту.");
      if (r.dev_token) setToken(r.dev_token);
      setForgot("reset");
    } catch (e) { setErr(e.detail || "Не удалось отправить"); }
    finally { setBusy(false); }
  }
  async function doReset() {
    setErr(""); setBusy(true);
    try {
      await authApi.resetPassword(email, token, newPass);
      setForgot(null); setStep("form"); setMsg("Пароль изменён. Войдите с новым паролем."); setPassword("");
    } catch (e) { setErr(e.detail || "Не удалось сбросить пароль"); }
    finally { setBusy(false); }
  }

  return (
    <div className="app">
      <div className="scroll" style={{ display: "flex", flexDirection: "column", justifyContent: "center", maxWidth: 380, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 22 }}>
          <div style={{ width: 56, height: 56, borderRadius: 16, background: "var(--acbg)", color: "var(--act)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 26, margin: "0 auto 12px" }}>
            <i className="ti ti-stethoscope" />
          </div>
          <h1 style={{ fontSize: 20 }}>Вторая память</h1>
          <div className="sub" style={{ marginTop: 4 }}>карманный ординатор</div>
        </div>

        {msg && <div className="banner b-ac" style={{ marginBottom: 12, cursor: "default" }}><i className="ti ti-circle-check" /> {msg}</div>}

        {forgot === "reset" ? (
          <>
            <div className="sub" style={{ textAlign: "center", marginBottom: 12 }}>Введите код из письма и новый пароль.</div>
            {token && <div className="banner b-ac" style={{ marginBottom: 10, cursor: "default" }}><i className="ti ti-mail" /> Демо-код: <b style={{ marginLeft: 4 }}>{token}</b></div>}
            <input className="input" placeholder="Код из письма" value={token} onChange={(e) => setToken(e.target.value)} style={{ marginBottom: 10 }} />
            <input className="input" type="password" placeholder="Новый пароль (мин. 8 символов)" value={newPass} onChange={(e) => setNewPass(e.target.value)} style={{ marginBottom: 12 }} />
            {err && <div className="banner b-dn" style={{ marginBottom: 12 }}><i className="ti ti-alert-triangle" /> {err}</div>}
            <button className="btn pri block" style={{ padding: 13 }} disabled={busy || !newPass} onClick={doReset}>Сменить пароль</button>
            <button className="btn block" style={{ marginTop: 8 }} onClick={() => { setForgot(null); setErr(""); }}>Назад ко входу</button>
          </>
        ) : forgot === "request" ? (
          <>
            <div className="sub" style={{ textAlign: "center", marginBottom: 12 }}>Укажите почту — вышлем код для сброса пароля.</div>
            <input className="input" type="email" placeholder="Почта" value={email} onChange={(e) => setEmail(e.target.value)} style={{ marginBottom: 12 }} />
            {err && <div className="banner b-dn" style={{ marginBottom: 12 }}><i className="ti ti-alert-triangle" /> {err}</div>}
            <button className="btn pri block" style={{ padding: 13 }} disabled={busy || !email} onClick={sendForgot}>Отправить код</button>
            <button className="btn block" style={{ marginTop: 8 }} onClick={() => { setForgot(null); setErr(""); }}>Назад ко входу</button>
          </>
        ) : step === "form" ? (
          <>
            <div className="tabs" style={{ marginBottom: 14 }}>
              <div className={"t" + (mode === "login" ? " on" : "")} onClick={() => setMode("login")}>Вход</div>
              <div className={"t" + (mode === "register" ? " on" : "")} onClick={() => setMode("register")}>Регистрация</div>
            </div>

            {mode === "register" && (
              <>
                <input className="input" placeholder="ФИО" value={fullName} onChange={(e) => setFullName(e.target.value)} style={{ marginBottom: 10 }} />
                <input className="input" placeholder="Телефон (+7…)" value={phone} onChange={(e) => setPhone(e.target.value)} style={{ marginBottom: 10 }} />
                <select className="input" value={specialty} onChange={(e) => setSpecialty(e.target.value)} style={{ marginBottom: 10 }}>
                  {specs.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </>
            )}
            <input className="input" type="email" placeholder="Почта" value={email} onChange={(e) => setEmail(e.target.value)} style={{ marginBottom: 10 }} />
            <input className="input" type="password" placeholder="Пароль" value={password} onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()} style={{ marginBottom: 12 }} />

            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--ts)", marginBottom: 14, cursor: "pointer" }}>
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              Запомнить это устройство
            </label>

            {err && <div className="banner b-dn" style={{ marginBottom: 12 }}><i className="ti ti-alert-triangle" /> {err}</div>}

            <button className="btn pri block" style={{ padding: 13 }} disabled={busy} onClick={submit}>
              {busy ? "…" : mode === "register" ? "Зарегистрироваться" : "Войти"}
            </button>
            {mode === "login" && (
              <div style={{ textAlign: "center", marginTop: 10 }}>
                <span className="acc" style={{ fontSize: 12.5, cursor: "pointer" }} onClick={() => { setForgot("request"); setErr(""); setMsg(""); }}>Забыли пароль?</span>
              </div>
            )}

            <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "16px 0 12px" }}>
              <div style={{ flex: 1, height: 0.5, background: "var(--bd)" }} />
              <span className="muted" style={{ fontSize: 11 }}>или</span>
              <div style={{ flex: 1, height: 0.5, background: "var(--bd)" }} />
            </div>
            <button className="btn block" style={{ padding: 13 }} disabled={busy} onClick={demo}>
              <i className="ti ti-eye" /> Посмотреть демо (готовые данные)
            </button>
            <div className="muted" style={{ fontSize: 11, textAlign: "center", marginTop: 8 }}>
              Новый аккаунт стартует пустым. Демо открывает заполненную базу — пациенты, приёмы, история.
            </div>
          </>
        ) : (
          <>
            <div className="sub" style={{ textAlign: "center", marginBottom: 14 }}>
              Код отправлен на {email}. Введите его для входа.
            </div>
            {devCode && <div className="banner b-ac" style={{ marginBottom: 12, cursor: "default" }}><i className="ti ti-mail" /> Демо-код: <b style={{ marginLeft: 4 }}>{devCode}</b></div>}
            <input className="input" inputMode="numeric" placeholder="Код из письма" value={code} onChange={(e) => setCode(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && verify()} style={{ marginBottom: 12, textAlign: "center", letterSpacing: 4, fontSize: 18 }} />
            {err && <div className="banner b-dn" style={{ marginBottom: 12 }}><i className="ti ti-alert-triangle" /> {err}</div>}
            <button className="btn pri block" style={{ padding: 13 }} disabled={busy} onClick={verify}>Подтвердить</button>
            <button className="btn block" style={{ marginTop: 8 }} onClick={() => { setStep("form"); setCode(""); setErr(""); }}>Назад</button>
          </>
        )}
      </div>
    </div>
  );
}
