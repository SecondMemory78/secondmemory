import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { SkeletonList } from "../components/Loading";
import { confirmAction } from "../lib/confirm";
import { toast } from "../lib/toast";
import { fmtDate } from "../lib/dates";

// Выписка по эпизоду.
//
// Это не «сформировать и скачать»: документ подписывает врач своим именем,
// поэтому собранный текст — предложение. Врач правит формулировки и видит,
// чего в выписке нет и почему. Подписанную версию менять нельзя.

const WHY_RU = {
  "ждёт подтверждения врача": "ждёт вашего подтверждения",
  "есть противоречащие значения": "противоречащие значения",
  "не указана дата": "не указана дата",
  "предложено ассистентом, не подтверждено": "предложено ассистентом",
  "отменено": "отменено",
};

export default function Discharge() {
  const { eid } = useParams();
  const nav = useNavigate();
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.dischargeDraft(eid).then(setD).catch(() => setD({ error: true }));
  }, [eid]);

  async function save(patch) {
    const sections = { ...d.sections, ...patch };
    setD({ ...d, sections });                    // не ждём сервер — поле не должно «прыгать»
    const r = await api.dischargeEdit(d.id, sections);
    if (r._error) toast("Не удалось сохранить правку", "error");
  }

  async function sign() {
    const warn = d.checks?.length
      ? `Есть замечания (${d.checks.length}). Подписать всё равно?`
      : "Подписать выписку? Изменить её после этого будет нельзя.";
    if (!(await confirmAction({ title: warn, confirmText: "Подписать" }))) return;
    setBusy(true);
    const r = await api.dischargeFinalize(d.id);
    setBusy(false);
    if (r._error) { toast(r.detail || "Не удалось подписать", "error"); return; }
    setD(r);
    toast("Выписка подписана", "success");
  }

  async function revise() {
    const r = await api.dischargeRevise(d.id);
    if (r._error) { toast(r.detail || "Не удалось создать версию", "error"); return; }
    setD(r);
  }

  if (!d) return <><div className="hd"><div className="ttl">Выписка</div></div><SkeletonList /></>;
  if (d.error) return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
        <div className="ttl">Выписка</div>
      </div>
      <div className="sub">Не удалось собрать выписку по этому эпизоду.</div>
    </>
  );

  const s = d.sections || {};
  const final = d.status === "final";

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
        <div className="ttl" style={{ flex: 1 }}>
          Выписка{d.version > 1 ? ` · версия ${d.version}` : ""}
        </div>
      </div>

      {final && (
        <div className="banner b-sc" style={{ marginBottom: 12, display: "block" }}>
          <b>Подписана {fmtDate(d.finalized_at)}.</b>
          <div className="sub" style={{ marginTop: 2 }}>
            Подписанный документ не меняется. Нужна правка — создайте версию.
          </div>
          <button className="btn sm" style={{ marginTop: 8 }} onClick={revise}>
            Создать новую версию
          </button>
        </div>
      )}

      {/* Что НЕ вошло. Стоит ВЫШЕ документа намеренно: врач должен увидеть
          пропуски до того, как начнёт вычитывать текст и подписывать. */}
      {d.excluded?.length > 0 && !final && (
        <div className="banner b-wn" style={{ marginBottom: 12, display: "block" }}>
          <b>Не вошло в выписку · {d.excluded.length}</b>
          <div style={{ marginTop: 6 }}>
            {d.excluded.map((x, i) => (
              <div key={i} className="sub" style={{ lineHeight: 1.6 }}>
                · {x.what} — {WHY_RU[x.why] || x.why}
              </div>
            ))}
          </div>
          <div className="sub" style={{ marginTop: 6 }}>
            Подтвердите нужное в карте и соберите выписку заново.
          </div>
        </div>
      )}

      {d.checks?.length > 0 && !final && (
        <div className="banner b-dn" style={{ marginBottom: 12, display: "block" }}>
          <b>Стоит проверить</b>
          <div style={{ marginTop: 6 }}>
            {d.checks.map((x, i) => (
              <div key={i} className="sub" style={{ lineHeight: 1.6 }}>· {x.text}</div>
            ))}
          </div>
        </div>
      )}

      <div className="sec-label" style={{ marginTop: 0 }}>Пациент</div>
      <div className="row">
        <div>
          <div style={{ fontSize: 13.5 }}>{s.patient?.name || "—"}</div>
          {s.patient?.birth_date && <div className="sub">{fmtDate(s.patient.birth_date)}</div>}
        </div>
      </div>

      <div className="sec-label">Основной диагноз</div>
      <input className="input" value={s.diagnosis_main || ""} disabled={final}
             placeholder="не указан"
             onChange={(e) => save({ diagnosis_main: e.target.value })} />

      {s.diagnosis_other?.length > 0 && (
        <>
          <div className="sec-label">Сопутствующие</div>
          {s.diagnosis_other.map((x, i) => <div key={i} className="row"><div style={{ fontSize: 13.5 }}>{x}</div></div>)}
        </>
      )}

      {s.procedures?.length > 0 && (
        <>
          <div className="sec-label">Операции и процедуры</div>
          {s.procedures.map((p, i) => (
            <div key={i} className="row">
              <div>
                <div style={{ fontSize: 13.5 }}>{p.name}</div>
                <div className="sub">
                  {fmtDate(p.date)}{p.surgeon ? ` · ${p.surgeon}` : ""}
                  {/* Пустые осложнения НЕ превращаем в «осложнений не было» */}
                  {p.complications ? ` · осложнения: ${p.complications}` : ""}
                </div>
              </div>
            </div>
          ))}
        </>
      )}

      {s.investigations?.length > 0 && (
        <>
          <div className="sec-label">Обследования</div>
          {s.investigations.map((o, i) => (
            <div key={i} className="row">
              <div style={{ fontSize: 13.5 }}>{o.label || o.code}</div>
              <div className="mono">{o.value} {o.unit} · {fmtDate(o.date)}</div>
            </div>
          ))}
        </>
      )}

      {s.devices?.length > 0 && (
        <>
          <div className="sec-label">Остаются с пациентом</div>
          {s.devices.map((x, i) => (
            <div key={i} className="row">
              <div style={{ fontSize: 13.5 }}>
                {{ stent: "Стент", nephrostomy: "Нефростома", catheter: "Катетер" }[x.kind] || x.kind}
                {{ left: " слева", right: " справа", both: " с обеих сторон" }[x.side] || ""}
              </div>
              <div className="sub">
                {x.due_at ? `замена ${fmtDate(x.due_at)}` : "срок не назначен"}
              </div>
            </div>
          ))}
        </>
      )}

      {s.orders?.length > 0 && (
        <>
          <div className="sec-label">Назначения при выписке</div>
          {s.orders.map((r, i) => (
            <div key={i} className="row">
              <div>
                <div style={{ fontSize: 13.5 }}>{r.name || r.instruction}</div>
                <div className="sub">
                  {[r.dose, r.frequency, r.duration].filter(Boolean).join(", ")}
                </div>
              </div>
            </div>
          ))}
        </>
      )}

      <div className="sec-label">Рекомендации</div>
      <textarea className="input" rows={4} disabled={final}
                placeholder="Что сказать пациенту словами врача"
                value={s.recommendations || ""}
                onChange={(e) => save({ recommendations: e.target.value })} />

      {!final && (
        <button className="btn pri block" style={{ marginTop: 16 }}
                disabled={busy} onClick={sign}>
          <i className="ti ti-signature" /> {busy ? "Подписываю…" : "Подписать выписку"}
        </button>
      )}
    </>
  );
}
