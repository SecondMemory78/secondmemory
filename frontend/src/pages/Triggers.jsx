import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { confirmAction } from "../lib/confirm";

export default function Triggers() {
  const nav = useNavigate();
  const [list, setList] = useState([]);
  const [busy, setBusy] = useState("");

  function load() { api.triggers().then(setList).catch(() => setList([])); }
  useEffect(() => { load(); }, []);

  async function run() {
    setBusy("Проверяю…");
    const r = await api.runTriggers();
    setBusy("");
    alert(r.created ? `Заведено контролей: ${r.created}. Смотрите в «Задачах».` : "Новых совпадений нет — всё под контролем.");
    load();
  }
  async function remove(id) {
    if (!(await confirmAction({ title: "Удалить триггер?", danger: true, confirmText: "Удалить" }))) return;
    await api.deleteTrigger(id); load();
  }

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav("/more")} />
        <div className="ttl">Автослежение</div>
      </div>
      <div className="sub" style={{ marginBottom: 12 }}>
        Триггер следит за условием и сам заводит контроль, когда показатель пересекает порог.
      </div>

      {list.length === 0 && (
        <div className="empty"><i className="ti ti-bell-plus" />
          <div style={{ fontSize: 13, marginBottom: 4 }}>Триггеров пока нет</div>
          <div className="muted" style={{ fontSize: 12 }}>Создайте из «Поиск → Срез по картотеке».</div>
        </div>
      )}

      {list.map((t) => (
        <div key={t.id} className="row">
          <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
            <i className="ti ti-bell acc" style={{ marginTop: 2 }} />
            <div>
              <div style={{ fontSize: 13.5 }}>{t.name}</div>
              <div className="sub">{t.matches > 0 ? `сейчас подходит: ${t.matches}` : "совпадений нет"}</div>
            </div>
          </div>
          <i className="ti ti-trash muted" style={{ cursor: "pointer" }} onClick={() => remove(t.id)} />
        </div>
      ))}

      {list.length > 0 && (
        <button className="btn pri block" style={{ marginTop: 16 }} onClick={run} disabled={!!busy}>
          <i className="ti ti-player-play" /> {busy || "Проверить и завести контроли"}
        </button>
      )}
    </>
  );
}
