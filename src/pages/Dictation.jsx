import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import Button from "../components/Button";
import VoiceButton from "../components/VoiceButton";
import Tip from "../components/Tip";
import { useTips } from "../lib/tips";
import { toast } from "../lib/toast";

const TYPE_LABEL = { patient_note: "Заметка пациенту", task: "Задача", call: "Звонок", idea: "Идея" };
const TYPE_ICON = { patient_note: "ti-note", task: "ti-checkbox", call: "ti-phone", idea: "ti-bulb" };

export default function Dictation() {
  const nav = useNavigate();
  const { show } = useTips();
  const [text, setText] = useState("");
  const [dic, setDic] = useState(null);
  const [result, setResult] = useState(null);
  const [search, setSearch] = useState({});

  // Подсказка про смешанную диктовку — когда система распознала больше одного пациента.
  useEffect(() => {
    if (!dic?.segments) return;
    const names = new Set(dic.segments.map((s) => s.extracted_name || s.resolved_patient_id).filter(Boolean));
    if (names.size > 1) show("tip:dictation");
  }, [dic, show]);

  async function analyze() {
    if (!text.trim()) return;
    if (!navigator.onLine) {
      const { enqueue } = await import("../lib/outbox");
      await enqueue("dictation", { text });
      toast("Нет сети — заметка сохранена и отправится сама, когда связь появится", "success");
      setText("");
      return;
    }
    try {
      setDic(await api.createDictation(text));
    } catch (e) {
      if (e && e.status === 0) {   // сеть отвалилась в процессе — в очередь
        const { enqueue } = await import("../lib/outbox");
        await enqueue("dictation", { text });
        toast("Связь пропала — заметка в очереди, отправится автоматически", "info");
        setText("");
      }
    }
  }
  async function reload() { setDic(await api.getDictation(dic.id)); }
  async function assign(sid, pid) { await api.assignSegment(dic.id, sid, pid); reload(); }
  async function findFor(sid, q) {
    setSearch({ ...search, [sid]: q ? await api.patients(q).catch(() => []) : null });
  }
  async function confirm() { setResult(await api.confirmDictation(dic.id)); reload(); }

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
        <div className="ttl">Надиктовать несколько дел</div>
      </div>

      {!dic && (
        <>
          <div className="sub" style={{ marginBottom: 10 }}>
            Скажите или впишите всё подряд — про разных пациентов, звонки, задачи, идеи.
            Система разберёт на части, узнает пациентов и разложит по местам.
          </div>
          <textarea className="input" style={{ minHeight: 120 }} value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Напр.: Иванову назначил тамсулозин. Петрову контроль PSA через 3 месяца. Завтра в 12 позвонить Сидорову." />
          <div className="btnrow" style={{ marginTop: 10 }}>
            <VoiceButton onResult={(t) => setText((text ? text + " " : "") + t)} />
            <Button className="btn pri" style={{ flex: 1 }} disabled={!text.trim()} onClick={analyze}>Разобрать</Button>
          </div>
          <div className="sub" style={{ marginTop: 8, fontSize: 12 }}>
            Точность разбора свободной речи вырастет с ключами Yandex GPT. Механика разложения и приватность уже работают.
          </div>
        </>
      )}

      {dic && (
        <Tip tipKey="tip:dictation" place="bottom" title="Несколько пациентов в одной записи"
             text="Когда диктуете подряд про разных людей, называйте нового пациента ПЕРЕД его сведениями — тогда система правильно разложит, к кому что относится.">
          <div className="sub" style={{ marginBottom: 10 }}>Проверьте разбор и, где нужно, укажите пациента.</div>
        </Tip>
      )}

      {dic && (
        <>
          {dic.segments.map((seg) => (
            <div key={seg.id} className="card" style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontSize: 12.5, fontWeight: 600 }}>
                  <i className={"ti " + (TYPE_ICON[seg.seg_type] || "ti-dots")} /> {TYPE_LABEL[seg.seg_type] || seg.seg_type}
                </span>
                <span className="sub">{seg.status === "assigned" ? "✓ готов" : seg.status === "committed" ? "внесён" : ""}</span>
              </div>
              <div style={{ fontSize: 13 }}>{seg.content}{seg.when_text ? ` · ${seg.when_text}` : ""}</div>

              {seg.seg_type === "patient_note" && seg.status === "pending" && (
                <div style={{ marginTop: 8 }}>
                  {seg.identity?.action === "use" && seg.identity.candidates[0] && (
                    <button className="btn pri sm block" onClick={() => assign(seg.id, seg.identity.candidates[0].id)}>
                      Это {seg.identity.candidates[0].name} — в его карту
                    </button>
                  )}
                  {(seg.identity?.action === "choose" || seg.identity?.action === "similar") &&
                    seg.identity.candidates.map((cnd) => (
                      <div key={cnd.id} className="row" style={{ cursor: "pointer" }} onClick={() => assign(seg.id, cnd.id)}>
                        <span style={{ fontSize: 13 }}>{cnd.name}{cnd.birth_date ? " · " + cnd.birth_date : ""}</span>
                        <i className="ti ti-plus acc" />
                      </div>
                    ))}
                  <input className="input" placeholder="Найти пациента вручную" style={{ marginTop: 6 }}
                    onChange={(e) => findFor(seg.id, e.target.value)} />
                  {(search[seg.id] || []).slice(0, 5).map((p) => (
                    <div key={p.id} className="row" style={{ cursor: "pointer" }} onClick={() => assign(seg.id, p.id)}>
                      <span style={{ fontSize: 13 }}>{p.short_name}</span><i className="ti ti-plus acc" />
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}

          {result && (
            <div className="banner b-ac" style={{ cursor: "default", marginBottom: 10 }}>
              Разложено: {result.applied.length}.
              {result.pending_choice.length > 0 && ` Ждут выбора пациента: ${result.pending_choice.length}.`}
              {result.blocked.length > 0 && ` Без согласия: ${result.blocked.length}.`}
            </div>
          )}
          {!result && (
            <div className="btnrow">
              <button className="btn sm dng-solid" style={{ flex: 1 }} onClick={async () => { await api.discardDictation(dic.id); nav(-1); }}>Отменить</button>
              <Button className="btn pri sm" style={{ flex: 1 }} onClick={confirm}>Разложить по местам</Button>
            </div>
          )}
          {result && <button className="btn block" onClick={() => nav(-1)}>Готово</button>}
        </>
      )}
    </>
  );
}
