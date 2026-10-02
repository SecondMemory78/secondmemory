/** Выбор времени в 24-часовом формате — гарантированно без AM/PM. */
export default function TimeField({ value = "09:00", onChange }) {
  const [h, m] = value.split(":");
  const hours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0"));
  const mins = ["00", "05", "10", "15", "20", "25", "30", "35", "40", "45", "50", "55"];
  if (!mins.includes(m)) mins.push(m);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <select className="input" style={{ width: 74, textAlign: "center" }} value={h}
        onChange={(e) => onChange(`${e.target.value}:${m}`)}>
        {hours.map((x) => <option key={x} value={x}>{x}</option>)}
      </select>
      <span style={{ fontWeight: 600, color: "var(--tm)" }}>:</span>
      <select className="input" style={{ width: 74, textAlign: "center" }} value={m}
        onChange={(e) => onChange(`${h}:${e.target.value}`)}>
        {mins.sort().map((x) => <option key={x} value={x}>{x}</option>)}
      </select>
    </div>
  );
}
