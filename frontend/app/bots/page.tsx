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

  const running = bots.filter((b) => b.state === "running").length;

  return (
    <>
      <div className="section-header">
        <div>
          <h1 style={{ marginBottom: 2 }}>Bots</h1>
          <p style={{ fontSize: 13, color: "#aaaaaa" }}>
            {bots.length} configured · {running} running
          </p>
        </div>
        {can(user?.role, "bot:create") && (
          <Link href="/bots/new" className="btn" style={{ textDecoration: "none" }}>+ New bot</Link>
        )}
      </div>

      {err && <p className="error" style={{ marginBottom: 16 }}>{err}</p>}

      {bots.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "64px 24px" }}>
          <div style={{ width: 56, height: 56, borderRadius: 8, background: "#fff5f5", border: "1px solid #ffd0d0", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 20px" }}>
            <svg width="28" height="28" fill="none" viewBox="0 0 28 28">
              <rect x="5" y="10" width="18" height="14" rx="3" stroke="#ff444f" strokeWidth="1.5"/>
              <path d="M10 10V8a4 4 0 018 0v2" stroke="#ff444f" strokeWidth="1.5"/>
              <circle cx="10.5" cy="17" r="1.5" fill="#ff444f"/>
              <circle cx="17.5" cy="17" r="1.5" fill="#ff444f"/>
            </svg>
          </div>
          <p style={{ color: "#686868", fontSize: 15, marginBottom: 20, fontWeight: 600 }}>No bots configured yet</p>
          {can(user?.role, "bot:create") && (
            <Link href="/bots/new" className="btn" style={{ textDecoration: "none" }}>+ New bot</Link>
          )}
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table>
            <thead>
              <tr>
                <th>Bot</th>
                <th>State</th>
                <th>Active config</th>
                <th>Owner</th>
                <th>Last updated</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {bots.map((b) => (
                <tr key={b.id}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{
                        width: 7, height: 7, borderRadius: "50%", flexShrink: 0, display: "inline-block",
                        background: b.state === "running" ? "#008265" : b.state === "error" || b.state === "halted" ? "#cc2626" : "#d6dadc",
                        boxShadow: b.state === "running" ? "0 0 0 3px rgba(0,130,101,0.15)" : "none",
                      }} />
                      <div>
                        <Link href={`/bots/${b.id}`} style={{ fontWeight: 700, color: "#0e0e0e", display: "block" }}>
                          {b.name}
                        </Link>
                        <span style={{ fontSize: 11, color: "#d6dadc", fontFamily: "monospace" }}>{b.id}</span>
                      </div>
                    </div>
                  </td>
                  <td><span className={`pill ${b.state}`}>{b.state}</span></td>
                  <td>
                    {b.active_config_version
                      ? <span style={{ background: "#f2f3f4", color: "#555", padding: "3px 8px", borderRadius: 3, fontSize: 12, fontWeight: 700, fontFamily: "monospace" }}>
                          v{b.active_config_version}
                        </span>
                      : <span style={{ color: "#d6dadc" }}>—</span>
                    }
                  </td>
                  <td style={{ color: "#686868", fontSize: 13 }}>{b.owner_email}</td>
                  <td style={{ color: "#aaaaaa", fontSize: 12 }}>{new Date(b.updated_at_ms).toLocaleString()}</td>
                  <td>
                    <div style={{ display: "flex", gap: 6 }}>
                      {can(user?.role, "config:draft") && (
                        <Link href={`/bots/${b.id}/config`} className="btn ghost"
                          style={{ textDecoration: "none", fontSize: 12, padding: "5px 10px" }}>
                          Config
                        </Link>
                      )}
                      {can(user?.role, "bot:start") && b.state !== "running" && b.active_config_version && (
                        <button className="btn secondary" style={{ fontSize: 12, padding: "5px 10px" }}
                          onClick={() => action(b.id, api.startBot)}>Start</button>
                      )}
                      {can(user?.role, "bot:stop") && b.state === "running" && (
                        <button className="btn ghost" style={{ fontSize: 12, padding: "5px 10px" }}
                          onClick={() => action(b.id, api.pauseBot)}>Pause</button>
                      )}
                      {can(user?.role, "bot:stop") && (b.state === "running" || b.state === "paused") && (
                        <button className="btn danger" style={{ fontSize: 12, padding: "5px 10px" }}
                          onClick={() => action(b.id, api.stopBot)}>Stop</button>
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
