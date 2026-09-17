// Единые состояния загрузки/пустоты для всех страниц.

export function Spinner({ label }) {
  return (
    <div className="loading-wrap">
      <div className="spinner" />
      {label && <div className="sub">{label}</div>}
    </div>
  );
}

export function SkeletonList({ rows = 4 }) {
  return (
    <div style={{ marginTop: 4 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skel skel-row" />
      ))}
    </div>
  );
}

export function Empty({ icon = "ti-inbox", title = "Пусто", sub }) {
  return (
    <div className="empty">
      <i className={"ti " + icon} />
      <div style={{ fontSize: 13 }}>{title}</div>
      {sub && <div className="sub" style={{ marginTop: 4 }}>{sub}</div>}
    </div>
  );
}
