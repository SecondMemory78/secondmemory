import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { SkeletonList, Empty } from "../components/Loading";
import Button from "../components/Button";

export default function StartVisit() {
  const nav = useNavigate();
  const [session, setSession] = useState(null);
  const [list, setList] = useState(null);   // null = грузится
  const [q, setQ] = useState("");
  const [params] = useSearchParams();

  // Ассистент не нашёл пациента и предложил создать карту: открываем форму
  // с подставленной фамилией. Создаёт всё равно врач — голосом карту не заводим.
  useEffect(() => {
    const sn = (params.get("new") || "").trim();
    if (sn) { setQ(sn); openForm({ last_name: sn }); }
  }, []);
  const [form, setForm] = useState(null);   // null | {last_name,...}
  const [dupes, setDupes] = useState(null); // предупреждение о похожих
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.activeSession().then(setSession).catch(() => setSession({ active: false }));
    api.patients("").then(setList).catch(() => setList([]));
  }, []);

  async function start(pid) {
    // Приём требует согласия на обработку ПДн (152-ФЗ). Если согласия ещё нет —
    // не падаем, а ведём в карту пациента, где согласие оформляется.
    try {
      await api.startEncounter(pid, "приём");
      await api.startSession(pid).catch(() => {});
    } catch { /* нет согласия / иная причина — просто откроем карту */ }
    nav(`/patients/${pid}`);
  }

  function openForm(prefill) {
    setForm({ last_name: "", first_name: "", middle_name: "", birth_date: "", phone: "", ...(prefill || {}) });
  }

  async function save() {
    if (!form.last_name.trim() || busy) return;
    setBusy(true);
    try {
      // пустую дату не шлём пустой строкой — иначе 422 на поле date
      const probe = { ...form };
      if (!probe.birth_date) delete probe.birth_date;
      // сперва проверяем похожих (правила PAT) — не создаём вслепую
      const r = await api.checkIdentity(probe).catch(() => null);
      if (r && (r.action === "similar" || r.action === "choose" || r.action === "conflict") && r.candidates?.length) {
        setDupes(r);            // покажем предупреждение с кандидатами
        return;
      }
      await doCreateAndStart();
    } finally { setBusy(false); }
  }

  async function doCreateAndStart() {
    // пустую дату/поля не шлём пустой строкой — иначе бэкенд отвергает (422 на date)
    const body = { ...form };
    if (!body.birth_date) delete body.birth_date;
    const p = await api.createPatient(body);
    setForm(null); setDupes(null);
    await start(p.id);          // создали — и сразу открываем приём с ним
  }

  const filtered = (list || []).filter((p) =>
    q ? `${p.last_name} ${p.first_name} ${p.middle_name || ""}`.toLowerCase().includes(q.toLowerCase()) : true
  );

  // Разложим введённый в поиск запрос на «Фамилия Имя Отчество» для предзаполнения формы
  function prefillFromQuery() {
    const parts = q.trim().split(/\s+/);
    return { last_name: parts[0] || "", first_name: parts[1] || "", middle_name: parts[2] || "" };
  }

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav(-1)} />
        <div className="ttl" style={{ flex: 1 }}>Начать приём</div>
        <i className="ti ti-user-plus act" title="Новый пациент" onClick={() => openForm()} />
      </div>

      {session?.active && (
        <div className="card" style={{ margin: "6px 0 16px" }}>
          <div style={{ display: "flex", gap: 9, alignItems: "flex-start", marginBottom: 12 }}>
            <i className="ti ti-history acc" style={{ fontSize: 19, marginTop: 1 }} />
            <div>
              <div style={{ fontSize: 13.5, fontWeight: 500 }}>Продолжить приём?</div>
              <div className="sub" style={{ marginTop: 2 }}>
                Вы работали с пациентом {session.patient_name} — пауза {session.idle_minutes} мин
              </div>
            </div>
          </div>
          <div className="btnrow" style={{ marginTop: 0 }}>
            <button className="btn pri" style={{ flex: 1 }} onClick={() => nav(`/patients/${session.patient_id}`)}>Продолжить</button>
            <button className="btn" onClick={() => setSession({ active: false })}>Новый пациент</button>
          </div>
        </div>
      )}

      {dupes && (
        <div className="card" style={{ marginBottom: 12, borderLeft: "3px solid var(--wn)" }}>
          <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 4 }}>
            <i className="ti ti-alert-triangle wn" /> {dupes.action === "conflict" ? "Противоречие данных" : "Возможно, такой пациент уже есть"}
          </div>
          <div className="sub" style={{ marginBottom: 8 }}>
            Проверьте — вдруг это тот же человек. Можно открыть существующую карточку и начать приём с ней.
          </div>
          {dupes.candidates.map((cnd) => (
            <div key={cnd.id} className="row" style={{ cursor: "pointer" }} onClick={() => start(cnd.id)}>
              <div style={{ display: "flex", gap: 11, alignItems: "center" }}>
                <div className="avatar">{(cnd.last_name?.[0] || "") + (cnd.first_name?.[0] || "")}</div>
                <div>
                  <div style={{ fontSize: 13.5 }}>{cnd.last_name} {cnd.first_name} {cnd.middle_name}</div>
                  <div className="sub">{[cnd.birth_date, cnd.diagnosis_code].filter(Boolean).join(" · ")}</div>
                </div>
              </div>
              <i className="ti ti-chevron-right muted" />
            </div>
          ))}
          <div className="btnrow" style={{ marginTop: 10 }}>
            <button className="btn sm" style={{ flex: 1 }} onClick={() => setDupes(null)}>Назад</button>
            <Button className="btn pri sm" style={{ flex: 1 }} disabled={busy} onClick={doCreateAndStart}>
              Всё равно создать нового
            </Button>
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
          <div className="sub" style={{ marginBottom: 8 }}>После создания приём начнётся сразу.</div>
          <div className="btnrow">
            <button className="btn sm" style={{ flex: 1 }} onClick={() => { setForm(null); setDupes(null); }}>Отмена</button>
            <Button className="btn pri sm" style={{ flex: 1 }} disabled={!form.last_name.trim() || busy} onClick={save}>Создать и начать</Button>
          </div>
        </div>
      )}

      {!form && !dupes && (
        <>
          <div className="sub" style={{ fontWeight: 500, marginBottom: 8 }}>С кем начинаем приём?</div>
          <div className="input" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <i className="ti ti-search muted" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск пациента…"
              style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)" }} />
          </div>

          {list === null && <SkeletonList rows={5} />}

          {list !== null && filtered.length === 0 && (
            <div>
              {q ? (
                <>
                  <Empty icon="ti-search-off" title="Пациент не найден"
                         sub="Проверьте запрос или заведите новую карточку" />
                  <Button className="btn pri block" style={{ marginTop: 12 }} onClick={() => openForm(prefillFromQuery())}>
                    <i className="ti ti-user-plus" /> Новый пациент{q.trim() ? `: ${q.trim()}` : ""}
                  </Button>
                </>
              ) : (
                <>
                  <Empty icon="ti-users" title="Пациентов пока нет"
                         sub="Заведите первого — и приём начнётся сразу" />
                  <Button className="btn pri block" style={{ marginTop: 12 }} onClick={() => openForm()}>
                    <i className="ti ti-user-plus" /> Добавить первого пациента
                  </Button>
                </>
              )}
            </div>
          )}

          {filtered.map((p) => (
            <div key={p.id} className="row" style={{ cursor: "pointer" }} onClick={() => start(p.id)}>
              <div style={{ display: "flex", gap: 11, alignItems: "center" }}>
                <div className="avatar">{(p.last_name[0] || "") + (p.first_name[0] || "")}</div>
                <div>
                  <div style={{ fontSize: 13.5 }}>{p.last_name} {p.first_name} {p.middle_name}</div>
                  <div className="sub">{[p.age && p.age + " лет", p.diagnosis_code].filter(Boolean).join(" · ")}</div>
                </div>
              </div>
              <i className="ti ti-chevron-right muted" />
            </div>
          ))}
        </>
      )}
    </>
  );
}
