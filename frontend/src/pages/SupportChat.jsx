import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

const REPLY_PROMISE = "Обычно отвечаем в течение пары часов, 9:00–22:00";

export default function SupportChat() {
  const nav = useNavigate();
  const [thread, setThread] = useState(null);       // текущее открытое
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [view, setView] = useState("chat");          // chat | history | thread
  const [threads, setThreads] = useState([]);
  const [opened, setOpened] = useState(null);         // просматриваемое закрытое
  const end = useRef(null);

  async function loadCurrent() {
    const r = await api.supportThread();
    setThread(r.thread);
    setMessages(r.thread?.messages || []);
    if (r.unread) api.supportRead();
    scrollDown();
  }
  function scrollDown() { setTimeout(() => end.current?.scrollIntoView({ behavior: "smooth" }), 40); }

  useEffect(() => {
    loadCurrent();
    // ответ поддержки подтягивается сам — как в референсе, опрос раз в 20с
    const t = setInterval(() => { if (view === "chat") loadCurrent(); }, 20000);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, [view]);

  async function openHistory() {
    setView("history");
    setThreads(await api.supportHistory());
  }
  async function openThread(t) {
    setOpened(t); setView("thread");
    const dto = await api.supportThreadMessages(t.id);
    setMessages(dto.messages || []);
    scrollDown();
  }
  function backToChat() { setOpened(null); setView("chat"); loadCurrent(); }

  async function send() {
    const body = text.trim();
    if (!body || sending) return;
    setSending(true);
    // оптимистично показываем сразу
    setMessages((m) => [...m, { id: "tmp-" + Date.now(), from_staff: false, body, created_at: new Date().toISOString(), pending: true }]);
    setText(""); scrollDown();
    try {
      const dto = await api.supportSend(body);
      setThread(dto); setMessages(dto.messages || []);
    } catch {
      setMessages((m) => m.map((x) => x.pending ? { ...x, pending: false, failed: true } : x));
    } finally { setSending(false); scrollDown(); }
  }

  const closed = threads.filter((t) => t.status === "closed");
  const readOnly = view === "thread";

  return (
    <>
      <div className="hd">
        <i className="ti ti-arrow-left back" onClick={() => view === "chat" ? nav("/more") : backToChat()} />
        <div className="ttl">{view === "history" ? "История обращений" : view === "thread" ? (opened?.subject || "Обращение") : "Поддержка"}</div>
        {view === "chat" && <i className="ti ti-history act" title="История" onClick={openHistory} />}
      </div>

      {view === "chat" && <div className="sub" style={{ marginBottom: 12 }}>{REPLY_PROMISE}</div>}

      {view === "history" ? (
        <>
          {closed.length === 0 && <div className="empty"><i className="ti ti-inbox" /><div className="sub">Закрытых обращений пока нет</div></div>}
          {threads.map((t) => (
            <div key={t.id} className="row" style={{ cursor: "pointer" }} onClick={() => openThread(t)}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.subject || "Обращение"}</div>
                <div className="sub" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.preview}</div>
              </div>
              <span className={"pill " + (t.status === "open" ? "" : "")} style={{ fontSize: 10, padding: "2px 8px", borderRadius: 999, background: t.status === "open" ? "var(--acbg)" : "var(--s1)", color: t.status === "open" ? "var(--act)" : "var(--tm)" }}>
                {t.status === "open" ? "открыто" : "решено"}
              </span>
            </div>
          ))}
        </>
      ) : (
        <>
          {view === "thread" && (
            <div className="banner b-ac" style={{ cursor: "default" }}>
              <i className="ti ti-circle-check" /> Обращение решено. Чтобы задать новый вопрос, вернитесь к текущему чату.
            </div>
          )}

          {messages.length === 0 && view === "chat" && (
            <div className="empty"><i className="ti ti-lifebuoy" />
              <div style={{ fontSize: 13, marginBottom: 4 }}>Опишите, что случилось — постараемся помочь</div>
              <div className="muted" style={{ fontSize: 12 }}>Обычно одно обращение — один вопрос.</div>
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
            {messages.map((m) => (
              <div key={m.id} style={{
                maxWidth: "82%", padding: "9px 12px", borderRadius: 14, fontSize: 13, lineHeight: 1.5,
                alignSelf: m.from_staff ? "flex-start" : "flex-end",
                background: m.from_staff ? "var(--s1)" : "var(--ac)",
                color: m.from_staff ? "var(--tp)" : "#fff", opacity: m.pending ? 0.6 : 1,
              }}>
                {m.from_staff && <div style={{ fontSize: 10, fontWeight: 600, opacity: 0.7, marginBottom: 2 }}>Поддержка</div>}
                <div style={{ whiteSpace: "pre-wrap" }}>{m.body}</div>
                <div style={{ fontSize: 10, opacity: 0.6, marginTop: 3 }}>{new Date(m.created_at).toLocaleString("ru-RU")}</div>
                {m.failed && <div style={{ fontSize: 10, marginTop: 3, color: "#ffd7d3" }}>Не отправилось — проверьте связь</div>}
              </div>
            ))}
            <div ref={end} />
          </div>

          {thread?.status === "closed" && view === "chat" && (
            <div className="muted" style={{ fontSize: 12, textAlign: "center", marginBottom: 10 }}>
              Прошлое обращение закрыто. Новое сообщение откроет новое.
            </div>
          )}

          {!readOnly && (
            <div className="input" style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
              <textarea value={text} onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                rows={1} placeholder="Сообщение…"
                style={{ border: 0, background: "transparent", outline: "none", flex: 1, font: "inherit", color: "var(--tp)", resize: "none", maxHeight: 96 }} />
              <i className="ti ti-send acc" style={{ fontSize: 20, cursor: "pointer", opacity: text.trim() ? 1 : 0.4 }} onClick={send} />
            </div>
          )}
        </>
      )}
    </>
  );
}
