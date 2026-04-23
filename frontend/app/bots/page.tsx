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
    try {
      setBots(await api.listBots());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed");
    }
  }
  useEffect(() => { refresh(); }, []);

  async function action(id: string, fn: (id: string) => Promise<Bot>) {
    try { await fn(id); await refresh(); }
    catch (e) { alert(e instanceof Error ? e.message : "failed"); }
  }

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Bots</h1>
        {can(user?.role, "bot:create") && (
          <Link href="/bots/new" className="btn" style={{ textDecoration: "none" }}>+ New bot</Link>
        )}
      </div>
      {err && <p className="error">{err}</p>}

      {bots.length === 0 ? (
        <div className="card">No bots yet. Create one to get started.</div>
      ) : (
        <div className="card">
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", background: "#f8fafc" }}>
                <th style={th}>Name</th>
                <th style={th}>State</th>
                <th style={th}>Active config</th>
                <th style={th}>Owner</th>
                <th style={th}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {bots.map((b) => (
                <tr key={b.id} style={{ borderTop: "1px solid #e2e8f0" }}>
                  <td style={td}><Link href={`/bots/${b.id}`}>{b.name}</Link></td>
                  <td style={td}><span className={`pill ${b.state}`}>{b.state}</span></td>
                  <td style={td}>{b.active_config_version ?? <em style={{ color: "#94a3b8" }}>none</em>}</td>
                  <td style={td}>{b.owner_email}</td>
                  <td style={{ ...td, display: "flex", gap: 6 }}>
                    {can(user?.role, "bot:start") && b.state !== "running" && b.active_config_version && (
                      <button className="btn secondary" onClick={() => action(b.id, api.startBot)}>Start</button>
                    )}
                    {can(user?.role, "bot:stop") && b.state === "running" && (
                      <button className="btn secondary" onClick={() => action(b.id, api.pauseBot)}>Pause</button>
                    )}
                    {can(user?.role, "bot:stop") && (b.state === "running" || b.state === "paused") && (
                      <button className="btn danger" onClick={() => action(b.id, api.stopBot)}>Stop</button>
                    )}
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

const th: React.CSSProperties = { padding: "10px 12px", fontWeight: 600, fontSize: 13 };
const td: React.CSSProperties = { padding: "10px 12px", fontSize: 14 };
