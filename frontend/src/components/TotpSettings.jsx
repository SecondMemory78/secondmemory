import { useEffect, useState } from "react";
import { api } from "../api";
import { toast } from "../lib/toast";
import { confirmAction } from "../lib/confirm";

export default function TotpSettings() {
  const [enabled, setEnabled] = useState(null);   // null=грузится
  const [setup, setSetup] = useState(null);        // {secret, otpauth_uri} во время подключения
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [backupCodes, setBackupCodes] = useState(null);   // показываем ОДИН раз после активации/перевыпуска
  const [remaining, setRemaining] = useState(null);
  const [regen, setRegen] = useState(false);       // форма ввода кода для перевыпуска

  function load() {
    api.totpStatus().then((r) => {
      setEnabled(r.totp_enabled);
      if (r.totp_enabled) api.totpBackupCount().then((x) => setRemaining(x.remaining)).catch(() => {});
    }).catch(() => setEnabled(false));
  }
  useEffect(() => { load(); }, []);

  async function begin() {
    setBusy(true);
    const r = await api.totpSetup().catch(() => null);
    setBusy(false);
    if (!r) return toast("Не удалось начать подключение", "error");
    setSetup(r); setCode("");
  }

  async function activate() {
    if (code.length < 6) return;
    setBusy(true);
    try {
      const r = await api.totpActivate(code);
      toast("Двухфакторная защита включена", "success");
      setSetup(null); setCode("");
      if (r.backup_codes) setBackupCodes(r.backup_codes);   // показать коды один раз
      load();
    } catch {
      toast("Код неверен — проверьте приложение и время на телефоне", "error");
    }
    setBusy(false);
  }

  async function disable() {
    setSetup(null);
    const ok = await confirmAction({
      title: "Отключить приложение-аутентификатор?",
      message: "Вход снова будет только по коду на почту. Введите текущий код из приложения для подтверждения.",
      confirmText: "Продолжить",
    });
    if (!ok) return;
    setSetup({ disabling: true }); setCode("");
  }

  async function confirmDisable() {
    if (code.length < 6) return;
    setBusy(true);
    try {
      await api.totpDisable(code);
      toast("Приложение-аутентификатор отключено", "success");
      setSetup(null); setCode(""); setRemaining(null); load();
    } catch {
      toast("Код неверен", "error");
    }
    setBusy(false);
  }

  async function doRegen() {
    if (code.length < 6) return;
    setBusy(true);
    try {
      const r = await api.totpRegenerateBackup(code);
      setBackupCodes(r.backup_codes); setRegen(false); setCode(""); load();
      toast("Резервные коды перевыпущены", "success");
    } catch {
      toast("Код неверен", "error");
    }
    setBusy(false);
  }

  function copyBackup() {
    navigator.clipboard?.writeText((backupCodes || []).join("\n"));
    toast("Коды скопированы", "success");
  }

  if (enabled === null) return null;

  return (
    <>
      <div className="row" onClick={() => (enabled ? disable() : (setup ? setSetup(null) : begin()))}
           style={{ cursor: "pointer" }}>
        <div>
          <div style={{ fontSize: 13 }}>Приложение-аутентификатор (2FA)</div>
          <div className="sub" style={{ marginTop: 2 }}>
            {enabled ? "включено — вход по коду из приложения" : "надёжнее кода на почту; почта останется резервом"}
          </div>
        </div>
        <i className={"ti " + (enabled ? "ti-check acc" : "ti-chevron-right muted")} />
      </div>

      {setup && !setup.disabling && (
        <div className="card" style={{ marginBottom: 8 }}>
          <div className="sub" style={{ marginBottom: 8 }}>
            1. В Google Authenticator / Aegis выберите «Ввести ключ вручную» и введите:
          </div>
          <div style={{ fontFamily: "monospace", fontSize: 15, fontWeight: 600, letterSpacing: 1,
                        background: "var(--s1)", padding: "10px 12px", borderRadius: 8, wordBreak: "break-all",
                        marginBottom: 6 }}>
            {setup.secret}
          </div>
          <button className="btn sm" style={{ marginBottom: 10 }}
                  onClick={() => { navigator.clipboard?.writeText(setup.secret); toast("Ключ скопирован", "success"); }}>
            Скопировать ключ
          </button>
          <div className="sub" style={{ marginBottom: 6 }}>2. Введите 6-значный код из приложения:</div>
          <input className="input" inputMode="numeric" maxLength={6} placeholder="000000" value={code}
                 onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                 style={{ marginBottom: 8, letterSpacing: 6, textAlign: "center", fontSize: 18 }} />
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn" onClick={() => { setSetup(null); setCode(""); }}>Отмена</button>
            <button className="btn pri" disabled={busy || code.length < 6} onClick={activate}>Включить</button>
          </div>
        </div>
      )}

      {setup && setup.disabling && (
        <div className="card" style={{ marginBottom: 8 }}>
          <div className="sub" style={{ marginBottom: 6 }}>Введите текущий код из приложения для отключения:</div>
          <input className="input" inputMode="numeric" maxLength={6} placeholder="000000" value={code}
                 onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                 style={{ marginBottom: 8, letterSpacing: 6, textAlign: "center", fontSize: 18 }} />
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn" onClick={() => { setSetup(null); setCode(""); }}>Отмена</button>
            <button className="btn dng-solid" disabled={busy || code.length < 6} onClick={confirmDisable}>Отключить</button>
          </div>
        </div>
      )}
      {backupCodes && (
        <div className="card" style={{ marginBottom: 8, borderLeft: "3px solid var(--wn)" }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Резервные коды — сохраните сейчас</div>
          <div className="sub" style={{ marginBottom: 8 }}>
            Каждый код одноразовый. Пригодятся, если недоступны и приложение, и почта. Показываются один раз.
          </div>
          <div style={{ fontFamily: "monospace", fontSize: 14, lineHeight: 1.7, background: "var(--s1)",
                        padding: "10px 12px", borderRadius: 8, marginBottom: 8 }}>
            {backupCodes.map((c) => <div key={c}>{c}</div>)}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn sm" onClick={copyBackup}>Скопировать</button>
            <button className="btn sm pri" onClick={() => setBackupCodes(null)}>Я сохранил</button>
          </div>
        </div>
      )}

      {enabled && remaining !== null && !backupCodes && (
        <div className="row" onClick={() => { setRegen(!regen); setCode(""); }} style={{ cursor: "pointer" }}>
          <div>
            <div style={{ fontSize: 13 }}>Резервные коды</div>
            <div className="sub" style={{ marginTop: 2 }}>осталось {remaining} · перевыпустить</div>
          </div>
          <i className="ti ti-refresh muted" />
        </div>
      )}

      {regen && (
        <div className="card" style={{ marginBottom: 8 }}>
          <div className="sub" style={{ marginBottom: 6 }}>Введите код из приложения — старые резервные коды перестанут действовать:</div>
          <input className="input" inputMode="numeric" maxLength={6} placeholder="000000" value={code}
                 onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                 style={{ marginBottom: 8, letterSpacing: 6, textAlign: "center", fontSize: 18 }} />
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn" onClick={() => { setRegen(false); setCode(""); }}>Отмена</button>
            <button className="btn pri" disabled={busy || code.length < 6} onClick={doRegen}>Перевыпустить</button>
          </div>
        </div>
      )}
    </>
  );
}
