"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getToken, api } from "../lib/api";
import { events, GLOBAL_EVENTS } from "../lib/events";

interface ChatSession {
  id: string;
  title: string;
  updated_at_ms: number;
}

  suggested_replies?: string[];
  isError?: boolean;
}

interface ChatResponse {
  reply: string;
  session_id: string;
  actions: string[];
  entities: any[];
  steps: string[];
  suggested_replies: string[];
}

function BotCard({ bot }: { bot: any }) {
  return (
    <div style={{
      background: "#fff",
      border: "1px solid #e2e8f0",
      borderRadius: 12,
      padding: 12,
      marginTop: 8,
      display: "flex",
      flexDirection: "column",
      gap: 4,
      boxShadow: "0 4px 12px rgba(0,0,0,0.05)"
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: "#1e293b" }}>{bot.name}</span>
        <span style={{ 
          fontSize: 10, 
          padding: "2px 6px", 
          borderRadius: 10, 
          background: bot.state === "running" ? "#dcfce7" : "#f1f5f9",
          color: bot.state === "running" ? "#166534" : "#64748b",
          fontWeight: 600,
          textTransform: "uppercase"
        }}>{bot.state}</span>
      </div>
      <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
        <div>
          <div style={{ fontSize: 10, color: "#94a3b8" }}>ID</div>
          <div style={{ fontSize: 11, fontFamily: "monospace" }}>{bot.id}</div>
        </div>
        {bot.active_config_version && (
          <div>
            <div style={{ fontSize: 10, color: "#94a3b8" }}>Config</div>
            <div style={{ fontSize: 11 }}>v{bot.active_config_version}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function ProgressIndicator({ steps }: { steps: string[] }) {
  return (
    <div style={{ padding: "8px 12px", background: "#f8fafc", borderRadius: 12, border: "1px solid #e2e8f0", marginTop: 8, maxWidth: "85%" }}>
      {steps.map((step, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, opacity: i === steps.length - 1 ? 1 : 0.5 }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#6366f1" }} />
          <span style={{ fontSize: 11, color: "#475569" }}>{step}</span>
        </div>
      ))}
    </div>
  );
}

const DEFAULT_SUGGESTIONS = [
  "Check my top performing bots",
  "Analyze performance for last 24h",
  "Show me recent trade logs",
  "What is my current risk exposure?",
];

function SmartSuggestions({ onSelect, suggestions = DEFAULT_SUGGESTIONS }: { onSelect: (s: string) => void, suggestions?: string[] }) {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12, justifyContent: "center" }}>
      {suggestions.map((s, i) => (
        <button
          key={i}
          onClick={() => onSelect(s)}
          style={{
            padding: "6px 12px",
            background: "#fff",
            border: "1px solid #e2e8f0",
            borderRadius: 20,
            fontSize: 12,
            color: "#6366f1",
            cursor: "pointer",
            boxShadow: "0 2px 6px rgba(0,0,0,0.05)",
            transition: "all 0.2s"
          }}
        >
          {s}
        </button>
      ))}
    </div>
  );
}


async function sendMessage(
  message: string,
  sessionId: string | null
): Promise<ChatResponse> {
  const token = getToken();
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(error);
  }
  return (await res.json()) as ChatResponse;
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
  archive_bot: "Archived bot",
  update_bot_config: "Updated config",
  get_bot_analytics: "Analyzed metrics",
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
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setAuthed(!!getToken());
  }, [open]);

  useEffect(() => {
    if (open) {
      loadSessions();
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const loadSessions = async () => {
    try {
      const data = await api.listChatSessions();
      setSessions(data as any);
    } catch (err) {
      console.error("Failed to load sessions", err);
    }
  };

  const startNewChat = () => {
    setMessages([]);
    setSessionId(null);
    setIsHistoryOpen(false);
  };

  const switchSession = async (id: string) => {
    setSessionId(id);
    setIsHistoryOpen(false);
    setLoading(true);
    try {
      const history = await api.getChatHistory(id);
      setMessages(history.map(m => ({
        role: m.role as "user" | "assistant",
        content: m.content,
        actions: m.role === "assistant" ? [] : undefined
      })));
    } catch (err) {
      console.error("Failed to load history", err);
    } finally {
      setLoading(false);
    }
  };

  const deleteSession = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await api.deleteChatSession(id);
      setSessions(prev => prev.filter(s => s.id !== id));
      if (sessionId === id) startNewChat();
    } catch (err) {
      console.error("Failed to delete session", err);
    }
  };

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);
    try {
      const data = await sendMessage(text, sessionId);
      if (!sessionId) {
        setSessionId(data.session_id);
        loadSessions();
      }
      if (data.actions && data.actions.length > 0) {
        events.emit(GLOBAL_EVENTS.STATE_CHANGED);
      }
      setMessages((prev) => [
        ...prev,
        { 
          role: "assistant", 
          content: data.reply, 
          actions: data.actions,
          entities: data.entities,
          steps: data.steps,
          suggested_replies: data.suggested_replies
        },
      ]);
        {
          role: "assistant",
          content: `${err instanceof Error ? err.message : "Something went wrong"}`,
          isError: true,
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
        .chat-msg { line-height: 1.55; word-break: break-word; }
        .chat-msg p { margin: 0 0 8px 0; }
        .chat-msg p:last-child { margin-bottom: 0; }
        .chat-msg ul, .chat-msg ol { margin: 8px 0; padding-left: 20px; }
        .chat-msg li { margin-bottom: 4px; }
        .chat-msg code { 
          font-family: 'JetBrains Mono', monospace; 
          font-size: 0.9em; 
          background: rgba(0,0,0,0.06); 
          padding: 2px 4px; 
          border-radius: 4px; 
        }
        .chat-msg-user code { background: rgba(255,255,255,0.2); }
        .chat-msg pre { 
          background: #1e293b; 
          color: #f8fafc; 
          padding: 12px; 
          border-radius: 8px; 
          overflow-x: auto; 
          margin: 8px 0;
        }
        .chat-msg pre code { background: transparent; padding: 0; color: inherit; font-size: 12px; }
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
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ width: 32, height: 32, background: "rgba(255,255,255,0.2)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>✦</div>
              <div>
                <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: "#fff" }}>Brindle Assistant</h3>
                <p style={{ margin: 0, fontSize: 11, opacity: 0.8, color: "#fff" }}>Powered by Groq · Llama 3.3 70B</p>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={() => setIsHistoryOpen(!isHistoryOpen)}
                title="View chat history"
                style={{
                  background: "rgba(255,255,255,0.15)",
                  border: "none",
                  color: "#fff",
                  padding: "6px",
                  borderRadius: 8,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {isHistoryOpen ? (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                ) : (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                )}
              </button>
              <button
                onClick={startNewChat}
                title="New chat"
                style={{
                  background: "rgba(255,255,255,0.15)",
                  border: "none",
                  color: "#fff",
                  padding: "6px",
                  borderRadius: 8,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              </button>
            </div>
          </div>

          {/* Body */}
          {isHistoryOpen ? (
            <div style={{ flex: 1, overflowY: "auto", padding: 16, background: "#f8f9ff" }}>
              <h4 style={{ margin: "0 0 16px 0", fontSize: 14, color: "#64748b" }}>Recent Chats</h4>
              {sessions.length === 0 ? (
                <div style={{ textAlign: "center", color: "#94a3b8", marginTop: 40, fontSize: 13 }}>No history yet</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {sessions.map(s => (
                    <div
                      key={s.id}
                      onClick={() => switchSession(s.id)}
                      style={{ padding: "12px 16px", background: sessionId === s.id ? "#f1f5f9" : "#fff", border: "1px solid #e2e8f0", borderRadius: 12, cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}
                    >
                      <span style={{ fontSize: 13, fontWeight: 500, color: "#334155", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.title}</span>
                      <button onClick={(e) => deleteSession(e, s.id)} style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer" }}>✕</button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
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
                <div style={{ textAlign: "center", color: "#94a3b8", marginTop: 100 }}>
                  <div style={{ fontSize: 32, marginBottom: 12 }}>👋</div>
                  <h4 style={{ margin: 0, color: "#1e293b" }}>How can I help you today?</h4>
                  <p style={{ fontSize: 12, marginTop: 8, color: "#64748b" }}>
                    Ask me to list bots, check performance, or run a backtest.
                  </p>
                  <SmartSuggestions onSelect={(s) => { setInput(s); }} />
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
                      borderRadius: msg.role === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
                      background: msg.role === "user" ? "#6366f1" : "#fff",
                      color: msg.role === "user" ? "#fff" : "#1e293b",
                      fontSize: 13.5,
                      border: msg.role === "assistant" ? "1px solid #e2e8f0" : "none",
                      boxShadow: msg.role === "user" ? "0 2px 8px rgba(99,102,241,0.3)" : "0 1px 4px rgba(0,0,0,0.08)",
                    }}
                  >
                    <ReactMarkdown 
                      remarkPlugins={[remarkGfm]}
                      components={{
                        a: ({node, ...props}) => <a {...props} style={{ color: msg.role === "user" ? "#fff" : "#6366f1", textDecoration: "underline" }} target="_blank" rel="noopener noreferrer" />
                      }}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                  {msg.steps && msg.steps.length > 0 && <ProgressIndicator steps={msg.steps} />}
                  {msg.entities && msg.entities.length > 0 && (
                    <div style={{ maxWidth: "85%", display: "flex", flexDirection: "column", gap: 4 }}>
                      {msg.entities.map((ent, j) => (
                        <BotCard key={j} bot={ent} />
                      ))}
                    </div>
                  )}
                  {msg.actions && msg.actions.length > 0 && (
                    </div>
                  )}
                  {msg.isError && (
                    <button
                      onClick={() => {
                        // Find the last user message
                        const lastUserMsg = [...messages].reverse().find(m => m.role === "user");
                        if (lastUserMsg) {
                          setInput(lastUserMsg.content);
                          // Tiny delay to ensure state update before sending
                          setTimeout(handleSend, 0);
                        }
                      }}
                      style={{
                        marginTop: 8,
                        padding: "6px 12px",
                        background: "#fee2e2",
                        border: "1px solid #fecaca",
                        borderRadius: 8,
                        fontSize: 12,
                        color: "#991b1b",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        fontWeight: 500
                      }}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.3"/></svg>
                      Retry
                    </button>
                  )}
                  {msg.suggested_replies && msg.suggested_replies.length > 0 && (
                    <div style={{ alignSelf: "center", width: "100%", display: "flex", justifyContent: "center" }}>
                      <SmartSuggestions 
                        suggestions={msg.suggested_replies} 
                        onSelect={(s) => { 
                          setInput(s); 
                          // Auto-send after a tiny delay to show the input filling
                          setTimeout(() => {
                            const btn = document.querySelector('button[title="Send"]') as HTMLButtonElement;
                            if (btn) btn.click();
                            else handleSend(); // Fallback if ref or query fails
                          }, 50);
                        }} 
                      />
                    </div>
                  )}
                </div>
              ))}

              {loading && (
                <div style={{ alignSelf: "flex-start" }}>
                  <div style={{ background: "#fff", borderRadius: "16px 16px 16px 4px", boxShadow: "0 1px 4px rgba(0,0,0,0.08)" }}>
                    <TypingIndicator />
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}

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
              title="Send"
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
