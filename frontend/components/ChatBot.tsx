"use client";

import { useEffect, useRef, useState } from "react";
import { getToken } from "../lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  actions?: string[];
}

interface ChatResponse {
  reply: string;
  session_id: string;
  actions: string[];
}

const API_BASE =
  typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"
    : "http://localhost:8000";

async function sendMessage(
  message: string,
  sessionId: string | null
): Promise<ChatResponse> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<ChatResponse>;
}

const ACTION_LABEL: Record<string, string> = {
  list_bots: "Listed bots",
  get_bot: "Fetched bot",
  start_bot: "Started bot",
  stop_bot: "Stopped bot",
  pause_bot: "Paused bot",
  list_alerts: "Fetched alerts",
  acknowledge_alert: "Acknowledged alert",
  get_audit_log: "Read audit log",
  list_positions: "Fetched positions",
  list_orders: "Fetched orders",
  create_bot: "Created bot",
  run_backtest: "Ran backtest",
};

function ActionPill({ action }: { action: string }) {
  const label = ACTION_LABEL[action] ?? action;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontSize: 11,
        background: "#e0e7ff",
        color: "#3730a3",
        borderRadius: 12,
        padding: "2px 8px",
        marginRight: 4,
        marginTop: 4,
      }}
    >
      ⚡ {label}
    </span>
  );
}

function TypingIndicator() {
  return (
    <div style={{ display: "flex", gap: 4, padding: "12px 16px", alignItems: "center" }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: "#6366f1",
            animation: `bounce 1.2s ${i * 0.2}s infinite`,
          }}
        />
      ))}
    </div>
  );
}

export default function ChatBot() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [authed, setAuthed] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setAuthed(!!getToken());
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  if (!authed) return null;

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);
    try {
      const data = await sendMessage(text, sessionId);
      setSessionId(data.session_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply, actions: data.actions },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${err instanceof Error ? err.message : "Something went wrong"}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleClear() {
    setMessages([]);
    setSessionId(null);
  }

  return (
    <>
      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
          40% { transform: translateY(-6px); opacity: 1; }
        }
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(16px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0) scale(1); }
        }
        .chat-msg { line-height: 1.55; white-space: pre-wrap; word-break: break-word; }
      `}</style>

      {/* Floating toggle button */}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Toggle assistant"
        style={{
          position: "fixed",
          bottom: 24,
          right: 24,
          zIndex: 9999,
          width: 52,
          height: 52,
          borderRadius: "50%",
          background: open ? "#4f46e5" : "#6366f1",
          border: "none",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 4px 20px rgba(99,102,241,0.5)",
          transition: "background 0.2s, transform 0.2s",
          transform: open ? "rotate(45deg)" : "none",
          fontSize: 22,
          color: "#fff",
        }}
      >
        {open ? "✕" : "✦"}
      </button>

      {/* Chat panel */}
      {open && (
        <div
          style={{
            position: "fixed",
            bottom: 88,
            right: 24,
            zIndex: 9998,
            width: 360,
            maxHeight: "70vh",
            display: "flex",
            flexDirection: "column",
            background: "#ffffff",
            borderRadius: 16,
            boxShadow: "0 8px 40px rgba(0,0,0,0.18)",
            overflow: "hidden",
            animation: "slideUp 0.2s ease",
            border: "1px solid #e0e7ff",
          }}
        >
          {/* Header */}
          <div
            style={{
              background: "linear-gradient(135deg, #6366f1, #4f46e5)",
              padding: "14px 16px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 18 }}>✦</span>
              <div>
                <div style={{ color: "#fff", fontWeight: 700, fontSize: 14, lineHeight: 1.2 }}>
                  Brindle Assistant
                </div>
                <div style={{ color: "#c7d2fe", fontSize: 11 }}>Powered by Groq · Llama 3.3 70B</div>
              </div>
            </div>
            <button
              onClick={handleClear}
              title="Clear conversation"
              style={{
                background: "rgba(255,255,255,0.15)",
                border: "none",
                borderRadius: 8,
                color: "#fff",
                cursor: "pointer",
                fontSize: 12,
                padding: "4px 8px",
              }}
            >
              Clear
            </button>
          </div>

          {/* Messages */}
          <div
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "12px 12px 4px",
              display: "flex",
              flexDirection: "column",
              gap: 10,
              background: "#f8f9ff",
            }}
          >
            {messages.length === 0 && (
              <div
                style={{
                  textAlign: "center",
                  color: "#94a3b8",
                  fontSize: 13,
                  marginTop: 24,
                  padding: "0 16px",
                }}
              >
                <div style={{ fontSize: 28, marginBottom: 8 }}>✦</div>
                <div style={{ fontWeight: 600, color: "#6366f1", marginBottom: 4 }}>
                  How can I help?
                </div>
                <div>Try: "Show me all bots" · "Start bot_xyz" · "Run a backtest on EUR/USD"</div>
              </div>
            )}

            {messages.map((msg, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: msg.role === "user" ? "flex-end" : "flex-start",
                }}
              >
                <div
                  className="chat-msg"
                  style={{
                    maxWidth: "85%",
                    padding: "10px 13px",
                    borderRadius:
                      msg.role === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
                    background: msg.role === "user" ? "#6366f1" : "#fff",
                    color: msg.role === "user" ? "#fff" : "#1e293b",
                    fontSize: 13.5,
                    boxShadow:
                      msg.role === "user"
                        ? "0 2px 8px rgba(99,102,241,0.3)"
                        : "0 1px 4px rgba(0,0,0,0.08)",
                  }}
                >
                  {msg.content}
                </div>
                {msg.actions && msg.actions.length > 0 && (
                  <div style={{ maxWidth: "85%", marginTop: 4 }}>
                    {msg.actions.map((a, j) => (
                      <ActionPill key={j} action={a} />
                    ))}
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div style={{ alignSelf: "flex-start" }}>
                <div
                  style={{
                    background: "#fff",
                    borderRadius: "16px 16px 16px 4px",
                    boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
                  }}
                >
                  <TypingIndicator />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input bar */}
          <div
            style={{
              padding: "10px 12px",
              borderTop: "1px solid #e0e7ff",
              background: "#fff",
              display: "flex",
              gap: 8,
              alignItems: "center",
            }}
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Ask me anything..."
              disabled={loading}
              style={{
                flex: 1,
                border: "1.5px solid #e0e7ff",
                borderRadius: 10,
                padding: "8px 12px",
                fontSize: 13.5,
                outline: "none",
                background: "#f8f9ff",
                color: "#1e293b",
                transition: "border-color 0.2s",
              }}
              onFocus={(e) => (e.target.style.borderColor = "#6366f1")}
              onBlur={(e) => (e.target.style.borderColor = "#e0e7ff")}
            />
            <button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              style={{
                background: loading || !input.trim() ? "#c7d2fe" : "#6366f1",
                border: "none",
                borderRadius: 10,
                color: "#fff",
                cursor: loading || !input.trim() ? "not-allowed" : "pointer",
                padding: "8px 14px",
                fontSize: 16,
                transition: "background 0.2s",
                flexShrink: 0,
              }}
            >
              ➤
            </button>
          </div>
        </div>
      )}
    </>
  );
}
