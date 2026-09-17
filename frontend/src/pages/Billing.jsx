import { useEffect, useState } from "react";
import { api } from "../api";
import { Spinner } from "../components/Loading";
import Toggle from "../components/Toggle";

export default function Billing() {
  const [plans, setPlans] = useState([]);
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");

  function load() {
    api.billingPlans().then(setPlans).catch(() => {});
    api.billingStatus().then(setStatus).catch(() => {});
  }
  useEffect(() => { load(); }, []);

  // возврат с оплаты ЮKassa (?paid=1): вебхук может прийти с задержкой — опрашиваем статус
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (!params.get("paid")) return;
    setMsg("Проверяем оплату…");
    let tries = 0;
    const timer = setInterval(async () => {
      tries += 1;
      const st = await api.billingStatus().catch(() => null);
      if (st?.active) {
        setStatus(st); setMsg("Оплата прошла — подписка активна.");
        clearInterval(timer);
        window.history.replaceState({}, "", "/billing");
      } else if (tries >= 5) {
        setMsg("Оплата обрабатывается. Если статус не обновился — обновите страницу через минуту.");
        clearInterval(timer);
      }
    }, 2000);
    return () => clearInterval(timer);
  }, []);

  async function pick(key) {
    setBusy(key); setMsg("");
    try {
      const r = await api.subscribe(key);
      if (r.activated) {
        setMsg("Подписка активирована. Можно работать со всеми функциями.");
        load();
      } else if (r.confirmation_url) {
        window.location.href = r.confirmation_url;   // редирект на оплату ЮKassa
      }
    } catch (e) {
      setMsg(e.detail || "Не удалось оформить подписку.");
    } finally { setBusy(""); }
  }

  async function toggleRenew() {
    const v = !status.auto_renew;
    await api.setAutoRenew(v);
    setStatus({ ...status, auto_renew: v });
  }

  return (
    <>
      <div className="hd"><div className="ttl">Подписка</div></div>

      {status?.active && (
        <div className="banner b-ac" style={{ cursor: "default", marginBottom: 14 }}>
          <i className="ti ti-circle-check" /> Подписка активна до {status.period_end?.slice(0, 10).split("-").reverse().join(".")}
          {" · "}{status.days_left} дн. осталось
        </div>
      )}
      {!status?.active && (
        <div className="sub" style={{ marginBottom: 16 }}>
          Без подписки доступен только просмотр. Выберите тариф, чтобы вносить пациентов, приёмы, заметки и пользоваться распознаванием.
        </div>
      )}
      {msg && <div className="banner b-ac" style={{ cursor: "default", marginBottom: 14 }}>{msg}</div>}

      {plans.length === 0 && <Spinner label="Загружаю тарифы…" />}
      {plans.map((p) => (
        <div key={p.key} className="card" style={{ marginBottom: 10, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 14.5, fontWeight: 600 }}>{p.label}{p.discount > 0 && <span className="acc" style={{ marginLeft: 8, fontSize: 12 }}>−{p.discount}%</span>}</div>
            <div className="sub">{p.price.toLocaleString("ru-RU")} ₽{p.months > 1 && <> · {p.price_per_month.toLocaleString("ru-RU")} ₽/мес</>}</div>
          </div>
          <button className="btn pri sm" disabled={busy === p.key} onClick={() => pick(p.key)}>
            {busy === p.key ? "…" : status?.plan === p.key && status?.active ? "Продлить" : "Выбрать"}
          </button>
        </div>
      ))}

      {status?.active && (
        <Toggle label="Автопродление" sub="спишем автоматически по тому же тарифу; письмо придёт заранее"
          on={status.auto_renew} onClick={toggleRenew} />
      )}
    </>
  );
}
