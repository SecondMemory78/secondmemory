import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { SkeletonList, Empty } from "../components/Loading";

const AREA = {
  patient: { icon: "ti-user", label: "Карта пациента" },
  calendar: { icon: "ti-calendar", label: "Календарь" },
  tasks: { icon: "ti-checklist", label: "Задачи" },
  denied: { icon: "ti-hand-stop", label: "Отклонено" },
  unknown: { icon: "ti-dots", label: "Прочее" },
};
const DEST = { appointment: "/calendar", reminder: "/tasks", patient: "/patients/" };

export default function AssistantLog() {
  const nav = useNavigate();
  const [rows, setRows] = useState(null);

  useEffect(() => { api.assistantActions().then(setRows).catch(() => setRows([])); }, []);

  function openEntity(a) {
    if (a.entity_type === "patient" && a.entity_id) nav("/patients/" + a.entity_id);
    else if (a.entity_type === "appointment") nav("/calendar");
    else if (a.entity_type === "reminder") nav("/tasks");
  }

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => nav("/more")} />
        <div className="ttl">Что сделал ассистент</div>
      </div>
      <div className="sub" style={{ marginBottom: 12 }}>
        История голосовых и текстовых команд: что вы сказали и что ассистент сделал.
      </div>

      {rows === null && <SkeletonList rows={5} />}
      {rows !== null && rows.length === 0 && (
        <Empty icon="ti-message-2" title="Пока пусто"
               sub="Скажите или напишите команду — например, «запиши Иванова на среду в 10:00»" />
      )}

      {(rows || []).map((a) => {
        const area = AREA[a.area] || AREA.unknown;
        const clickable = a.ok && (a.entity_id || a.entity_type === "appointment" || a.entity_type === "reminder");
        return (
          <div key={a.id} className="row" style={{ cursor: clickable ? "pointer" : "default", alignItems: "flex-start" }}
               onClick={() => clickable && openEntity(a)}>
            <div style={{ display: "flex", gap: 11, alignItems: "flex-start" }}>
              <i className={"ti " + area.icon + (a.ok ? " acc" : " dng")} style={{ fontSize: 18, marginTop: 2 }} />
              <div>
                <div style={{ fontSize: 13.5 }}>{a.message || a.input_text}</div>
                <div className="sub" style={{ marginTop: 2 }}>
                  <i className={"ti " + (a.channel === "voice" ? "ti-microphone" : "ti-keyboard")} style={{ fontSize: 12 }} />
                  {" "}«{a.input_text}» · {area.label} · {a.created_at.slice(11, 16)}
                </div>
              </div>
            </div>
            {clickable && <i className="ti ti-chevron-right muted" style={{ marginTop: 4 }} />}
          </div>
        );
      })}
    </>
  );
}
