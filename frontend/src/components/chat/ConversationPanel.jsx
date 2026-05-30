import { useEffect, useRef } from "react";

function MessageBubble({ message }) {
  if (message.role === "user") {
    return (
      <article className="message message--user">
        <div className="message__meta">
          <p className="message__label">Operator Input</p>
          <span>TX</span>
        </div>
        <p>{message.answer}</p>
      </article>
    );
  }

  return (
    <article className={`message message--assistant${message.isHistory ? " message--history" : ""}`}>
      <div className="message__meta">
        <p className="message__label">{message.title || "CMD-CTR"}</p>
        <span>{message.mode === "decision" ? "COUNCIL" : "CORE"}</span>
      </div>
      <p style={{ whiteSpace: "pre-wrap" }}>{message.answer}</p>
      {message.reasoning ? <p className="message__reasoning">{message.reasoning}</p> : null}
      {message.sources?.length ? (
        <div className="source-list">
          {message.sources.map((source) => (
            <a key={source.url} className="source-card" href={source.url} rel="noreferrer" target="_blank">
              <strong>{source.title}</strong>
              <span>{source.source}</span>
              {source.snippet ? <p>{source.snippet}</p> : null}
            </a>
          ))}
        </div>
      ) : null}
    </article>
  );
}

export default function ConversationPanel({
  messages,
  pending,
  error,
  mode,
  draft,
  onDraftChange,
  onSubmit,
  onClear,
}) {
  const listRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, pending]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    const success = await onSubmit(draft);
    if (!success) {
      inputRef.current?.focus();
    }
  }

  async function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      await onSubmit(draft);
    }
  }

  return (
    <section className="panel conversation-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Mission Core / Assistant Bus</p>
          <h2>Assistant Channel</h2>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {onClear ? (
            <button
              type="button"
              onClick={onClear}
              title="Clear conversation history"
              style={{
                background: "transparent",
                border: "1px solid var(--border)",
                color: "var(--muted)",
                padding: "0.2rem 0.6rem",
                borderRadius: "4px",
                fontSize: "0.7rem",
                cursor: "pointer",
                letterSpacing: "0.05em",
              }}
            >
              CLEAR
            </button>
          ) : null}
          <span className={`state-pill state-pill--${pending ? "busy" : "idle"}`}>
            {pending ? "Thinking" : mode === "decision" ? "Decision Council Ready" : "Conversation Ready"}
          </span>
        </div>
      </div>

      <div className="channel-statusbar">
        <span>INPUT BAY / LIVE</span>
        <span>{mode === "decision" ? "COUNCIL PATH ENABLED" : "DIRECT ASSIST PATH ENABLED"}</span>
        <span>{pending ? "PROCESSING" : "READY"}</span>
      </div>

      <div className="message-list" ref={listRef}>
        {messages.length === 0 && !pending ? (
          <p style={{ color: "var(--muted)", textAlign: "center", padding: "2rem", fontSize: "0.85rem" }}>
            Initialising...
          </p>
        ) : null}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {pending ? (
          <article className="message message--assistant">
            <div className="message__meta">
              <p className="message__label">CMD-CTR</p>
              <span>PROCESSING</span>
            </div>
            <p style={{ color: "var(--muted)", fontStyle: "italic" }}>Processing...</p>
          </article>
        ) : null}
      </div>

      {error ? <div className="error-banner">{error}</div> : null}

      <form className="composer" onSubmit={handleSubmit}>
        <div className="composer__inputbay">
          <div className="composer__eyebrow">
            <span>Command Input Bay</span>
            <span>Enter / transmit</span>
          </div>
          <textarea
            ref={inputRef}
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              mode === "decision"
                ? "Submit a tradeoff, recommendation, or strategic problem for council review."
                : "Issue a command, ask a question, or say 'open [app]' to launch something."
            }
            rows={3}
          />
          <div className="composer__footer">
            <span>SHIFT+ENTER / NEW LINE</span>
            <span>{mode === "decision" ? "DECISION ENGINE ROUTE" : "CONVERSATION ROUTE"}</span>
          </div>
        </div>
        <button type="submit" disabled={pending || !draft.trim()}>
          {pending ? "Routing..." : "Transmit"}
        </button>
      </form>
    </section>
  );
}
