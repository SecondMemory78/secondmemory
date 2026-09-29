// График динамики одного показателя во времени.
// Подтверждённые значения — сплошная линия с точками; pending — полая точка.
// Если в пороге есть число (напр. «> 4,0») — рисуем пунктирную линию порога.

function parseThreshold(threshold) {
  if (!threshold) return null;
  const m = String(threshold).match(/(\d+[.,]?\d*)/);
  return m ? parseFloat(m[1].replace(",", ".")) : null;
}

export default function TrendChart({ points, unit = "", threshold = "", label }) {
  const pts = (points || []).filter((p) => p.value_num != null);
  if (pts.length === 0) return null;

  const W = 300, H = 96, PAD = 26, TOP = 10;
  const vals = pts.map((p) => p.value_num);
  const thr = parseThreshold(threshold);
  let min = Math.min(...vals, thr != null ? thr : Infinity);
  let max = Math.max(...vals, thr != null ? thr : -Infinity);
  if (min === max) { min -= 1; max += 1; }
  const pad = (max - min) * 0.15;
  min -= pad; max += pad;

  const x = (i) => PAD + (pts.length === 1 ? (W - 2 * PAD) / 2 : i * (W - 2 * PAD) / (pts.length - 1));
  const y = (v) => TOP + (H - TOP - 16) * (1 - (v - min) / (max - min));

  const line = pts.map((p, i) => `${x(i).toFixed(1)},${y(p.value_num).toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  const first = pts[0];
  const up = pts.length > 1 && last.value_num > first.value_num;
  const down = pts.length > 1 && last.value_num < first.value_num;

  return (
    <div className="card" style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{label}</div>
        <div className="mono" style={{ fontSize: 15 }}>
          {last.value_num} <span className="sub" style={{ fontSize: 11 }}>{unit}</span>
          {up && <span className="dng" style={{ marginLeft: 4 }}>↑</span>}
          {down && <span className="acc" style={{ marginLeft: 4 }}>↓</span>}
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%" }}>
        {/* линия порога */}
        {thr != null && thr >= min && thr <= max && (
          <>
            <line x1={PAD} x2={W - PAD} y1={y(thr)} y2={y(thr)} stroke="var(--dn)" strokeWidth="1" strokeDasharray="4 3" opacity="0.5" />
            <text x={W - PAD} y={y(thr) - 3} textAnchor="end" fontSize="8" fill="var(--dn)">порог {thr}</text>
          </>
        )}
        {/* линия динамики */}
        {pts.length > 1 && <polyline points={line} fill="none" stroke="var(--ac)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />}
        {/* точки */}
        {pts.map((p, i) => (
          <circle key={i} cx={x(i)} cy={y(p.value_num)} r={p.status === "pending" ? 3 : 3.5}
            fill={p.status === "pending" ? "var(--s0)" : "var(--ac)"} stroke="var(--ac)" strokeWidth="1.5" />
        ))}
        {/* подписи крайних дат */}
        <text x={PAD} y={H - 2} fontSize="8" fill="var(--ts)">{(first.date || "").slice(0, 7)}</text>
        {pts.length > 1 && <text x={W - PAD} y={H - 2} textAnchor="end" fontSize="8" fill="var(--ts)">{(last.date || "").slice(0, 7)}</text>}
        {/* мин/макс по оси Y */}
        <text x="2" y={y(max) + 3} fontSize="8" fill="var(--ts)">{+max.toFixed(1)}</text>
        <text x="2" y={y(min) + 3} fontSize="8" fill="var(--ts)">{+min.toFixed(1)}</text>
      </svg>
      {threshold && <div className="sub" style={{ fontSize: 11, marginTop: 2 }}>{threshold}</div>}
    </div>
  );
}
