import { useEffect, useRef, useState } from "react";

// Холст для наброска.
//
// Зачем он в медицинском приложении: врачи чертят пациенту схему на бумажке,
// и бумажка теряется. Здесь она остаётся в заметке, а оттуда может уехать в
// карту и в памятку, которую пациент унесёт домой.
//
// Чего браузер не умеет и обещать нельзя: отклонения ладони (положил руку —
// появится лишняя линия) и плавности родного приложения. Это набросок, а не
// замена Procreate.

const COLORS = ["#16202C", "#2563EB", "#C4322B", "#1E7A52"];
const SIZES = [2, 4, 8];

export default function DrawCanvas({ value = "", onChange, onClose }) {
  const ref = useRef(null);
  const drawing = useRef(false);
  const strokes = useRef([]);          // для отмены последнего штриха
  const [color, setColor] = useState(COLORS[0]);
  const [size, setSize] = useState(SIZES[1]);
  const [eraser, setEraser] = useState(false);

  useEffect(() => {
    const cv = ref.current;
    // Рисуем в размер экрана с учётом плотности пикселей: иначе на телефоне
    // линия получается мыльной.
    const dpr = window.devicePixelRatio || 1;
    const rect = cv.getBoundingClientRect();
    cv.width = Math.round(rect.width * dpr);
    cv.height = Math.round(rect.height * dpr);
    const ctx = cv.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, rect.width, rect.height);
    if (value) {
      const img = new Image();
      img.onload = () => ctx.drawImage(img, 0, 0, rect.width, rect.height);
      img.src = value;
    }
  }, []);

  function pos(e) {
    const r = ref.current.getBoundingClientRect();
    const t = e.touches ? e.touches[0] : e;
    return { x: t.clientX - r.left, y: t.clientY - r.top,
             // Нажим пера: на iPad с карандашом линия живее. Мышь отдаёт 0.5.
             p: e.pressure !== undefined && e.pressure > 0 ? e.pressure : 0.5 };
  }

  function start(e) {
    e.preventDefault();
    const cv = ref.current;
    strokes.current.push(cv.toDataURL("image/png"));   // снимок ДО штриха — для отмены
    if (strokes.current.length > 20) strokes.current.shift();
    drawing.current = true;
    const ctx = cv.getContext("2d");
    const { x, y } = pos(e);
    ctx.beginPath();
    ctx.moveTo(x, y);
  }

  function move(e) {
    if (!drawing.current) return;
    e.preventDefault();
    const ctx = ref.current.getContext("2d");
    const { x, y, p } = pos(e);
    ctx.strokeStyle = eraser ? "#fff" : color;
    ctx.lineWidth = eraser ? size * 4 : size * (0.6 + p);
    ctx.lineTo(x, y);
    ctx.stroke();
  }

  function end() {
    if (!drawing.current) return;
    drawing.current = false;
    onChange?.(ref.current.toDataURL("image/png"));
  }

  function undo() {
    const prev = strokes.current.pop();
    if (!prev) return;
    const cv = ref.current;
    const ctx = cv.getContext("2d");
    const rect = cv.getBoundingClientRect();
    const img = new Image();
    img.onload = () => {
      ctx.clearRect(0, 0, rect.width, rect.height);
      ctx.drawImage(img, 0, 0, rect.width, rect.height);
      onChange?.(cv.toDataURL("image/png"));
    };
    img.src = prev;
  }

  function clearAll() {
    const cv = ref.current;
    const ctx = cv.getContext("2d");
    const rect = cv.getBoundingClientRect();
    strokes.current.push(cv.toDataURL("image/png"));
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, rect.width, rect.height);
    onChange?.(cv.toDataURL("image/png"));
  }

  return (
    <div className="draw-wrap">
      <div className="draw-tools">
        {COLORS.map((c) => (
          <button key={c} className={"draw-color" + (!eraser && color === c ? " on" : "")}
                  style={{ background: c }} aria-label="Цвет"
                  onClick={() => { setColor(c); setEraser(false); }} />
        ))}
        <span className="draw-sep" />
        {SIZES.map((s) => (
          <button key={s} className={"draw-size" + (size === s ? " on" : "")}
                  onClick={() => setSize(s)} aria-label="Толщина">
            <span style={{ width: s + 2, height: s + 2 }} />
          </button>
        ))}
        <span className="draw-sep" />
        <button className={"draw-btn" + (eraser ? " on" : "")} onClick={() => setEraser(!eraser)}
                title="Ластик"><i className="ti ti-eraser" /></button>
        <button className="draw-btn" onClick={undo} title="Отменить"><i className="ti ti-arrow-back-up" /></button>
        <button className="draw-btn" onClick={clearAll} title="Очистить"><i className="ti ti-trash" /></button>
        {onClose && (
          <button className="draw-btn" onClick={onClose} title="Свернуть">
            <i className="ti ti-chevron-up" />
          </button>
        )}
      </div>

      <canvas ref={ref} className="draw-canvas"
              onPointerDown={start} onPointerMove={move}
              onPointerUp={end} onPointerLeave={end} onPointerCancel={end} />

      <div className="sub" style={{ marginTop: 6 }}>
        Набросок для объяснения пациенту. Рисунок хранится картинкой — искать
        по нему нельзя.
      </div>
    </div>
  );
}
