import { useTips } from "../lib/tips";

// Коуч-марка, привязанная к элементу. Оборачивает целевой блок:
//   <Tip tipKey="tip:protocol" title="Шаблоны приёма" text="…" place="bottom">
//     <СелекторШаблона/>
//   </Tip>
// Подсказка появляется, только когда движок сделал active === tipKey.
// «place» — с какой стороны от элемента показать (top|bottom|left|right).
export default function Tip({ tipKey, title, text, place = "bottom", children }) {
  const { active, dismiss } = useTips();
  const open = active === tipKey;

  return (
    <div className="tip-anchor">
      {children}
      {open && (
        <div className={"tip-pop tip-" + place} role="dialog" aria-label={title || "Подсказка"}>
          <div className="tip-arrow" />
          {title && <div className="tip-title">{title}</div>}
          <div className="tip-text">{text}</div>
          <button className="btn pri sm tip-ok" onClick={() => dismiss(tipKey)}>Понятно</button>
        </div>
      )}
    </div>
  );
}
