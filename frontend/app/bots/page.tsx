"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Navigation from "@/components/Navigation";
import { api, getUser } from "@/lib/api";
import { can } from "@/lib/rbac";
import type { Bot } from "@/lib/types";

export default function BotsPage() {
  return (
    <AuthGuard>
      <Navigation />
      <div className="container">
        <BotsList />
      </div>
    </AuthGuard>
  );
}

function BotsList() {
  const [bots, setBots] = useState<Bot[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const user = getUser();

  async function refresh() {
    try { setBots(await api.listBots()); }
    catch (e) { setErr(e instanceof Error ? e.message : "failed"); }
  }
  useEffect(() => { refresh(); }, []);

  async function action(id: string, fn: (id: string) => Promise<Bot>) {
    try { await fn(id); await refresh(); }
    catch (e) { alert(e instanceof Error ? e.message : "failed"); }
  }

  return (
    <>
      <div className="section-header">
        <div>
          <h1 style={{ marginBottom: 4 }}>Bots</h1>
          <p style={{ fontSize: 14, color: "#64748b", margin: 0 }}>
            {bots.length} bot{bots.length !== 1 ? "s" : ""} ·{" "}
            {bots.filter((b) => b.state === "running").length} running
          </p>
        </div>
        {can(user?.role, "bot:create") && (
          <Link href="/bots/new" className="btn" style={{ textDecoration: "none" }}>
            + New bot
          </Link>
        )}
      </div>

      {err && <p className="error" style={{ marginBottom: 16 }}>{err}</p>}

      {bots.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "56px 24px" }}>
          <div style={{ width: 48, height: 48, borderRadius: 14, background: "#f0fdfa", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
            <svg width="24" height="24" fill="none" viewBox="0 0 24 24">
              <rect x="4" y="9" width="16" height="12" rx="3" stroke="#0d9488" strokeWidth="1.5"/>
              <path d="M9 9V7a3 3 0 116 0v2" stroke="#0d9488" strokeWidth="1.5"/>
              <circle cx="9" cy="15" r="1.5" fill="#0d9488"/>
              <circle cx="15" cy="15" r="1.5" fill="#0d9488"/>
            </svg>
          </div>
          <p style={{ color: "#64748b", fontSize: 15, marginBottom: 16 }}>No bots yet. Create one to get started.</p>
          {can(user?.role, "bot:create") && (
            <Link href="/bots/new" className="btn" style={{ textDecoration: "none" }}>+ New bot</Link>
          )}
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>State</th>
                <th>Active config</th>
                <th>Owner</th>
                <th>Last updated</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {bots.map((b) => (
                <tr key={b.id}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div style={{
                        width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                        background: b.state === "running" ? "#0d9488" : b.state === "error" || b.state === "halted" ? "#be123c" : "#94a3b8",
                        boxShadow: b.state === "running" ? "0 0 0 3px rgba(13,148,136,0.18)" : "none",
                      }} />
                      <Link href={`/bots/${b.id}`} style={{ fontWeight: 600, color: "#0f172a", textDecoration: "none" }}>
                        {b.name}
                      </Link>
                    </div>
                    <div style={{ fontSize: 12, color: "#94a3b8", marginLeft: 18, marginTop: 2, fontFamily: "ui-monospace, monospace" }}>
                      {b.id}
                    </div>
                  </td>
                  <td><span className={`pill ${b.state}`}>{b.state}</span></td>
                  <td>
                    {b.active_config_version
                      ? <span style={{ background: "#f0fdfa", color: "#0f766e", padding: "3px 10px", borderRadius: 6, fontSize: 13, fontWeight: 600 }}>v{b.active_config_version}</span>
                      : <span style={{ color: "#94a3b8", fontSize: 13 }}>—</span>
                    }
                  </td>
                  <td style={{ color: "#64748b", fontSize: 13 }}>{b.owner_email}</td>
                  <td style={{ color: "#94a3b8", fontSize: 13 }}>{new Date(b.updated_at_ms).toLocaleString()}</td>
                  <td>
                    <div style={{ display: "flex", gap: 6 }}>
                      {can(user?.role, "config:draft") && (
                        <Link
                          href={`/bots/${b.id}/config`}
                          className="btn secondary"
                          style={{ textDecoration: "none", fontSize: 13, padding: "6px 12px" }}
                        >
                          Config
                        </Link>
                      )}
                      {can(user?.role, "bot:start") && b.state !== "running" && b.active_config_version && (
                        <button className="btn secondary" style={{ fontSize: 13, padding: "6px 12px" }}
                          onClick={() => action(b.id, api.startBot)}>
                          Start
                        </button>
                      )}
                      {can(user?.role, "bot:stop") && b.state === "running" && (
                        <button className="btn secondary" style={{ fontSize: 13, padding: "6px 12px" }}
                          onClick={() => action(b.id, api.pauseBot)}>
                          Pause
                        </button>
                      )}
                      {can(user?.role, "bot:stop") && (b.state === "running" || b.state === "paused") && (
                        <button className="btn danger" style={{ fontSize: 13, padding: "6px 12px" }}
                          onClick={() => action(b.id, api.stopBot)}>
                          Stop
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
