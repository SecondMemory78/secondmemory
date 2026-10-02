import { useEffect, useState } from "react";
import { api } from "../api";
import Tip from "./Tip";
import { useTips } from "../lib/tips";
import VoiceButton from "./VoiceButton";
import { toast } from "../lib/toast";

const FIELDS = [
  ["complaints", "Жалобы"],
  ["anamnesis_morbi", "Анамнез заболевания"],
  ["anamnesis_vitae", "Анамнез жизни"],
  ["objective", "Объективный статус"],
  ["status_localis", "Локальный статус (Status localis)"],
  ["recommendations", "Назначения и рекомендации"],
];

function copy(text) {
  if (!text) return;
  if (navigator.clipboard) navigator.clipboard.writeText(text);
  else window.prompt("Скопируйте текст:", text);
}

/**
 * Протокол приёма с полями как в амбулаторной карте / ЕМИАС.
 * Каждый блок копируется отдельной кнопкой — чтобы быстро вставлять
 * в соответствующие поля государственной системы.
 * Разметка полей будет уточнена под реальный экран ЕМИАС.
 */
export default function ProtocolTab({ id, disabled }) {
  const { show } = useTips();
  const [p, setP] = useState(null);
  const [saved, setSaved] = useState(false);
  const [tpls, setTpls] = useState({ builtin: [], custom: [] });
  const [dict, setDict] = useState(null);      // предпросмотр разбора диктовки
  const [dictText, setDictText] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.protocol(id).then(setP); }, [id]);
  useEffect(() => { api.templates().then(setTpls).catch(() => {}); }, []);
  useEffect(() => { if (tpls.builtin.length) show("tip:protocol"); }, [tpls, show]);
  if (!p) return <div className="sub">Загрузка протокола…</div>;

  const set = (k, v) => { setP({ ...p, [k]: v }); setSaved(false); };

  function applyTemplate(code) {
    if (!code) { set("template_code", ""); return; }
    const t = [...tpls.builtin, ...tpls.custom].find((x) => x.code === code);
    if (!t) return;
    // подставляем блоки-подсказки только если поля пустые (не затираем набранное)
    setP({ ...p, template_code: code,
           tpl_additional: p.tpl_additional || "",
           tpl_exam_docs: p.tpl_exam_docs || "",
           tpl_plan: p.tpl_plan || "",
           _hints: { additional: t.additional, exam_docs: t.exam_docs, plan: t.plan } });
    setSaved(false);
  }

  // Диктовка: разбираем и ПОКАЗЫВАЕМ, что куда попадёт. Ничего не сохраняем
  // молча — по «Структуре консультации» врач должен подтвердить разбор.
  async function dictate(opts) {
    setBusy(true); setDict(null);
    try {
      setDict(await api.dictateProtocol(id, opts));
    } catch (e) {
      toast(e.detail || "Не удалось разобрать диктовку", "error");
    } finally { setBusy(false); }
  }

  // Дописываем к уже набранному, а не затираем его
  function applyDictation() {
    const next = { ...p };
    for (const sec of dict.sections) {
      if (sec.key === "unsorted") continue;
      const prev = (next[sec.key] || "").trim();
      next[sec.key] = prev ? `${prev}\n${sec.text}` : sec.text;
    }
    setP(next); setSaved(false); setDict(null); setDictText("");
  }

  async function save() {
    const body = Object.fromEntries(
      ["complaints", "anamnesis_morbi", "anamnesis_vitae", "objective",
       "status_localis", "diagnosis_code", "diagnosis_text", "recommendations",
       "template_code", "tpl_additional", "tpl_exam_docs", "tpl_plan"]
        .map((k) => [k, p[k] || ""])
    );
    await api.saveProtocol(id, body);
    setSaved(true);
  }

  function copyAll() {
    const lines = [];
    for (const [k, label] of FIELDS.slice(0, 4)) if (p[k]) lines.push(`${label}: ${p[k]}`);
    if (p.diagnosis_code || p.diagnosis_text)
      lines.push(`Диагноз: ${[p.diagnosis_code, p.diagnosis_text].filter(Boolean).join(" ")}`);
    if (p.status_localis) lines.push(`Локальный статус: ${p.status_localis}`);
    if (p.recommendations) lines.push(`Рекомендации: ${p.recommendations}`);
    copy(lines.join("\n\n"));
  }

  return (
    <>
      {p._draft && (
        <div className="banner b-ac" style={{ cursor: "default" }}>
          <i className="ti ti-wand" /> Черновик собран автоматически — проверьте и дополните
        </div>
      )}

      <div className="copyrow"><span className="lbl">Заполнить голосом или текстом</span></div>
      <div className="card" style={{ marginBottom: 12, opacity: disabled ? 0.5 : 1 }}>
        <div className="sub" style={{ marginBottom: 8 }}>
          Продиктуйте приём подряд — разложу по разделам и покажу, что куда попадёт.
          Пустые разделы останутся пустыми: отсутствие данных — не то же самое, что норма.
        </div>
        <textarea className="input" rows={2} value={dictText} disabled={disabled || busy}
                  onChange={(e) => setDictText(e.target.value)}
                  placeholder="Например: жалобы — никтурия 3 раза; анамнез — около года; диагноз ДГПЖ"
                  style={{ resize: "vertical", marginBottom: 8 }} />
        <div className="btnrow" style={{ marginTop: 0 }}>
          <button className="btn sm" style={{ flex: 1 }} disabled={disabled || busy || !dictText.trim()}
                  onClick={() => dictate({ text: dictText })}>
            {busy ? "Разбираю…" : "Разобрать текст"}
          </button>
          {!disabled && <VoiceButton label="Продиктовать" onResult={(blob) => dictate({ blob })} />}
        </div>

        {dict && (
          <div style={{ marginTop: 12 }}>
            <div className="sub" style={{ marginBottom: 6 }}>
              Разобрано ({dict.source === "ии" ? "ИИ" : "по ключевым словам"}) · {dict.status}
            </div>
            {dict.transcript && (
              <div className="sub" style={{ marginBottom: 8 }}>Распознано: «{dict.transcript}»</div>
            )}
            {dict.sections.length === 0 && <div className="sub dng">Не удалось выделить разделы.</div>}
            {dict.sections.map((sec) => (
              <div key={sec.key} className="row" style={{ alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>
                    {sec.label}{sec.key === "unsorted" && " (не разобрано — не перенесётся)"}
                  </div>
                  <div className="sub" style={{ marginTop: 2 }}>{sec.text}</div>
                </div>
              </div>
            ))}
            <div className="btnrow">
              <button className="btn sm" style={{ flex: 1 }} onClick={() => setDict(null)}>Отмена</button>
              <button className="btn pri sm" style={{ flex: 1 }} onClick={applyDictation}
                      disabled={!dict.sections.some((x) => x.key !== "unsorted")}>
                Перенести в протокол
              </button>
            </div>
            <div className="sub" style={{ marginTop: 6 }}>
              Текст добавится к уже набранному, не заменяя его. Сохранить не забудьте ниже.
            </div>
          </div>
        )}
      </div>

      <div className="copyrow"><span className="lbl">Шаблон приёма</span></div>
      <Tip tipKey="tip:protocol" place="bottom" title="Шаблоны приёма — это подсказки"
           text="Выберите тип приёма (например, «Повышенный ПСА») — форма подскажет, что важно заполнить: дополнительные поля, осмотр, план. Шаблон ничего не назначает автоматически, вы заполняете сами.">
      <select className="input" value={p.template_code || ""} onChange={(e) => applyTemplate(e.target.value)} style={{ marginBottom: 8 }}>
        <option value="">Без шаблона</option>
        <optgroup label="Типовые приёмы">
          {tpls.builtin.map((t) => <option key={t.code} value={t.code}>{t.code} · {t.name}</option>)}
        </optgroup>
        {tpls.custom.length > 0 && (
          <optgroup label="Мои шаблоны">
            {tpls.custom.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
          </optgroup>
        )}
      </select>
      </Tip>

      {p.template_code && (() => {
        const t = [...tpls.builtin, ...tpls.custom].find((x) => x.code === p.template_code) || {};
        const blocks = [["tpl_additional", "Дополнительные поля", t.additional],
                        ["tpl_exam_docs", "Осмотр и документы", t.exam_docs],
                        ["tpl_plan", "План и результат приёма", t.plan]];
        return blocks.map(([k, label, hint]) => (
          <div key={k} style={{ marginBottom: 8 }}>
            <div className="copyrow"><span className="lbl">{label}</span>
              <span className="cp" onClick={() => copy(p[k])}><i className="ti ti-copy" /> копировать</span></div>
            {hint && <div className="sub" style={{ marginBottom: 4, fontSize: 11.5, lineHeight: 1.5 }}>{hint}</div>}
            <textarea className="input" value={p[k] || ""} onChange={(e) => set(k, e.target.value)} placeholder="заполните по подсказке выше" />
          </div>
        ));
      })()}

      {FIELDS.slice(0, 4).map(([k, label]) => (
        <Block key={k} label={label} value={p[k]} onCopy={() => copy(p[k])}>
          <textarea className="input" value={p[k] || ""} onChange={(e) => set(k, e.target.value)} />
        </Block>
      ))}

      <div className="copyrow">
        <span className="lbl">Диагноз (МКБ-10)</span>
        <span className="cp" onClick={() => copy([p.diagnosis_code, p.diagnosis_text].filter(Boolean).join(" "))}>
          <i className="ti ti-copy" /> копировать
        </span>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <input className="input" style={{ maxWidth: 120 }} placeholder="N40.0"
          value={p.diagnosis_code || ""} onChange={(e) => set("diagnosis_code", e.target.value)} />
        <input className="input" placeholder="формулировка диагноза"
          value={p.diagnosis_text || ""} onChange={(e) => set("diagnosis_text", e.target.value)} />
      </div>

      {FIELDS.slice(4).map(([k, label]) => (
        <Block key={k} label={label} value={p[k]} onCopy={() => copy(p[k])}>
          <textarea className="input" value={p[k] || ""} onChange={(e) => set(k, e.target.value)} />
        </Block>
      ))}

      <div className="btnrow">
        <button className="btn pri" style={{ flex: 1, opacity: disabled ? 0.5 : 1 }} disabled={disabled} onClick={save}>
          {saved ? "Сохранено ✓" : "Сохранить"}
        </button>
        <button className="btn" onClick={copyAll}><i className="ti ti-clipboard-text" /> Копировать всё</button>
      </div>
    </>
  );
}

function Block({ label, onCopy, children }) {
  return (
    <>
      <div className="copyrow">
        <span className="lbl">{label}</span>
        <span className="cp" onClick={onCopy}><i className="ti ti-copy" /> копировать</span>
      </div>
      {children}
    </>
  );
}
