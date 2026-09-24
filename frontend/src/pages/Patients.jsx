import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { SkeletonList, Empty } from "../components/Loading";
import Button from "../components/Button";
import Tip from "../components/Tip";
import { useTips } from "../lib/tips";

export default function Patients() {
  const nav = useNavigate();
  const { show } = useTips();
  const [q, setQ] = useState("");
  const [list, setList] = useState(null);   // null = грузится
  const [form, setForm] = useState(null);   // null | {last_name,...}
  const [dupes, setDupes] = useState(null); // предупреждение о похожих

  useEffect(() => { if (dupes?.candidates?.length) show("tip:identity"); }, [dupes, show]);

  function load(query) {
    api.patients(query).then(setList).catch(() => setList([]));
  }
  useEffect(() => { load(""); }, []);
  useEffect(() => {
    const t = setTimeout(() => load(q), 200);
    return () => clearTimeout(t);
  }, [q]);

  async function save() {
    if (!form.last_name.trim()) return;
    // сперва проверяем похожих (правила PAT) — не создаём вслепую
    const r = await api.checkIdentity(form).catch(() => null);
    if (r && (r.action === "similar" || r.action === "choose" || r.action === "conflict") && r.candidates?.length) {
      setDupes(r);            // покажем предупреждение с кандидатами
      return;
    }
    await doCreate();
  }
  async function doCreate() {
    const p = await api.createPatient(form);
    setForm(null); setDupes(null); load("");
    nav(`/patients/${p.id}`);        // в карте сразу предложит оформить согласие
  }

  return (
    <>
      <div className="hd">
        <div className="ttl" style={{flex:1}}>Пациенты</div>
        <i className="ti ti-users-group act" title="Список отделения (много пациентов)" onClick={()=>nav("/photo-batch")} />
        <i className="ti ti-plus act" onClick={() => setForm({ last_name: "", first_name: "", middle_name: "", birth_date: "", phone: "" })} />
      </div>

      {dupes && (
        <div className="card" style={{ marginBottom: 12, borderLeft: "3px solid var(--wn)" }}>
          <Tip tipKey="tip:identity" place="bottom" title="Выберите нужного человека"
               text="Нашлись тёзки. Сверьте по дате рождения и другим данным и выберите существующую карточку. Создавайте нового только если это точно другой человек — так истории пациентов не смешаются.">
          <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 4 }}>
            <i className="ti ti-alert-triangle wn" /> {dupes.action === "conflict" ? "Противоречие данных" : "Возможно, такой пациент уже есть"}
          </div>
          </Tip>
          <div className="sub" style={{ marginBottom: 8 }}>
            {dupes.action === "conflict"
              ? (dupes.message || "Проверьте данные перед созданием.")
              : "Выберите существующую карточку или создайте нового, если это точно другой человек."}
          </div>
          {dupes.candidates.map((cnd) => (
            <div key={cnd.id} className="row" style={{ cursor: "pointer" }} onClick={() => { setForm(null); setDupes(null); nav(`/patients/${cnd.id}`); }}>
              <div>
                <div style={{ fontSize: 13 }}>{cnd.name}</div>
                <div className="sub">{cnd.birth_date ? cnd.birth_date.split("-").reverse().join(".") : "дата рождения не указана"}{cnd.sex ? " · " + cnd.sex : ""}</div>
              </div>
              <i className="ti ti-chevron-right muted" />
            </div>
          ))}
          <div className="btnrow" style={{ marginTop: 10 }}>
            <button className="btn sm" style={{ flex: 1 }} onClick={() => setDupes(null)}>Назад</button>
            <button className="btn sm dng-solid" style={{ flex: 1 }} onClick={doCreate}>Всё равно создать нового</button>
          </div>
        </div>
      )}

      {form && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="sec-label" style={{ marginTop: 0 }}>Новый пациент</div>
          <input className="input" placeholder="Фамилия*" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} style={{ marginBottom: 8 }} />
          <input className="input" placeholder="Имя" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} style={{ marginBottom: 8 }} />
          <input className="input" placeholder="Отчество" value={form.middle_name} onChange={(e) => setForm({ ...form, middle_name: e.target.value })} style={{ marginBottom: 8 }} />
          <input className="input" type="date" value={form.birth_date} onChange={(e) => setForm({ ...form, birth_date: e.target.value })} style={{ marginBottom: 8 }} />
          <input className="input" placeholder="Телефон" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} style={{ marginBottom: 8 }} />
          <div className="btnrow">
            <button className="btn sm" style={{ flex: 1 }} onClick={() => setForm(null)}>Отмена</button>
            <Button className="btn pri sm" style={{ flex: 1 }} disabled={!form.last_name.trim()} onClick={save}>Создать</Button>
          </div>
        </div>
      )}

      <div className="input" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <i className="ti ti-search muted" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Имя, диагноз (напр. ДГПЖ)…"
          style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)" }}
        />
      </div>

      {list === null && <SkeletonList rows={5} />}
      {list !== null && list.length === 0 && (
        q ? <Empty icon="ti-search-off" title="Ничего не найдено" sub="Попробуйте изменить запрос" />
          : <Empty icon="ti-users" title="Пациентов пока нет" sub="Добавьте первого пациента кнопкой ниже" />
      )}
      {(list || []).map((p) => (
        <div key={p.id} className="row" style={{ cursor: "pointer" }} onClick={() => nav(`/patients/${p.id}`)}>
          <div style={{ display: "flex", gap: 11, alignItems: "center" }}>
            <div className="avatar">{initials(p)}</div>
            <div>
              <div style={{ fontSize: 13.5 }}>{p.last_name} {p.first_name} {p.middle_name}</div>
              <div className="sub">{[p.age && p.age + " лет", p.diagnosis_code].filter(Boolean).join(" · ")}</div>
            </div>
          </div>
          <i className="ti ti-chevron-right muted" />
        </div>
      ))}
    </>
  );
}

function initials(p) {
  return (p.last_name[0] || "") + (p.first_name[0] || "");
}
