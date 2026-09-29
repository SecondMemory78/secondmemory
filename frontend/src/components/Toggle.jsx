export default function Toggle({ label, sub, on, onClick }) {
  return (
    <div className="row">
      <div>
        <div style={{ fontSize: 13 }}>{label}</div>
        {sub && <div className="sub" style={{ marginTop: 2 }}>{sub}</div>}
      </div>
      <div onClick={onClick} style={{ width: 34, height: 19, borderRadius: 10, background: on ? "var(--ac)" : "var(--bds)", position: "relative", cursor: "pointer", transition: ".2s" }}>
        <span style={{ position: "absolute", top: 2, left: on ? 17 : 2, width: 15, height: 15, background: "#fff", borderRadius: "50%", transition: ".2s" }} />
      </div>
    </div>
  );
}
