import { useEffect, useRef, useState } from "react";
import { getChatHistory, sendChatMessage } from "../api";

export default function ChatPanel({ projectId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    getChatHistory(projectId).then(setMessages).catch(() => {});
  }, [projectId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: "user", content: text }]);
    setSending(true);
    try {
      const reply = await sendChatMessage(projectId, text);
      setMessages((prev) => [...prev, reply]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { id: `err-${Date.now()}`, role: "assistant", content: `Error: ${err.message}` },
      ]);
    } finally {
      setSending(false);
    }
  };

  return (
    <aside className="chat-sidebar">
      <div className="chat-sidebar-header">Ask about this project</div>
      <div className="chat-messages" ref={scrollRef}>
        {messages.length === 0 && (
          <p className="chat-empty">
            Ask anything about this contract or invoices — e.g. "How is task 22 trending?" or "Summarize the
            flags on the last invoice."
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`chat-message ${m.role}`}>
            {m.content}
          </div>
        ))}
        {sending && <div className="chat-message assistant">…</div>}
      </div>
      <form className="chat-input-row" onSubmit={handleSend}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question…"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend(e);
            }
          }}
        />
        <button type="submit" className="btn btn-primary btn-sm" disabled={sending || !input.trim()}>
          Send
        </button>
      </form>
    </aside>
  );
}
