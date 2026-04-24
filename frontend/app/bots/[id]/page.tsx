"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Navigation from "@/components/Navigation";
import { api, getUser } from "@/lib/api";
import { can } from "@/lib/rbac";
import type { AuditEvent, Bot, ConfigVersion, Order, Position } from "@/lib/types";

export default function BotDetailsPage() {
  return (
    <AuthGuard>
      <Navigation />
      <div className="container">
        <BotDetails />
      </div>
    </AuthGuard>
  );
}

function BotDetails() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const user = getUser();
  const [bot, setBot] = useState<Bot | null>(null);
  const [versions, setVersions] = useState<ConfigVersion[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    try {
      const [b, v, pos, ord, a] = await Promise.all([
        api.getBot(id),
        api.listConfigs(id),
        api.listPositions(id),
        api.listOrders(id),
        api.listAudit(),
      ]);
      setBot(b);
      setVersions(v);
      setPositions(pos);
      setOrders(ord);
      setAudit(a.filter((e) => e.resource_id === id || e.resource_id.startsWith(`${id}:`)));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed");
    }
  }
  useEffect(() => { refresh(); }, [id]);

  if (err) return <p className="error">{err}</p>;
  if (!bot) return <p>Loading…</p>;

  async function act(fn: (id: string) => Promise<Bot>) {
    try { await fn(id); await refresh(); }
    catch (e) { alert(e instanceof Error ? e.message : "failed"); }
  }

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ marginBottom: 4 }}>{bot.name}</h1>
          <div style={{ fontSize: 13, color: "#64748b" }}>
            <code>{bot.id}</code> · owner {bot.owner_email}
          </div>
        </div>
        <span className={`pill ${bot.state}`}>{bot.state}</span>
      </div>

      <div style={{ display: "flex", gap: 8, margin: "16px 0" }}>
        {can(user?.role, "config:draft") && (
          <Link href={`/bots/${bot.id}/config`} className="btn" style={{ textDecoration: "none" }}>Edit configuration</Link>
        )}
        {can(user?.role, "bot:start") && bot.state !== "running" && bot.active_config_version && (
          <button className="btn secondary" onClick={() => act(api.startBot)}>Start</button>
        )}
        {can(user?.role, "bot:stop") && bot.state === "running" && (
          <button className="btn secondary" onClick={() => act(api.pauseBot)}>Pause</button>
        )}
        {can(user?.role, "bot:stop") && (bot.state === "running" || bot.state === "paused") && (
          <button className="btn danger" onClick={() => act(api.stopBot)}>Stop</button>
        )}
      </div>

      {positions.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2 style={{ marginTop: 0 }}>Open positions</h2>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", background: "#f8fafc" }}>
                <th style={th}>Symbol</th>
                <th style={{ ...th, textAlign: "right" }}>Qty</th>
                <th style={{ ...th, textAlign: "right" }}>Avg price</th>
                <th style={{ ...th, textAlign: "right" }}>Realized PnL</th>
                <th style={th}>Updated</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.symbol} style={{ borderTop: "1px solid #e2e8f0" }}>
                  <td style={td}><b>{p.symbol}</b></td>
                  <td style={{ ...td, textAlign: "right" }}>{p.quantity.toLocaleString()}</td>
                  <td style={{ ...td, textAlign: "right" }}>
                    {p.avg_price != null ? p.avg_price.toFixed(5) : "—"}
                  </td>
                  <td style={{ ...td, textAlign: "right", color: p.realized_pnl >= 0 ? "#15803d" : "#b91c1c" }}>
                    {p.realized_pnl >= 0 ? "+" : ""}{p.realized_pnl.toFixed(2)}
                  </td>
                  <td style={td}>{new Date(p.updated_at_ms).toLocaleTimeString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {orders.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2 style={{ marginTop: 0 }}>Recent orders</h2>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", background: "#f8fafc" }}>
                <th style={th}>Symbol</th>
                <th style={th}>Side</th>
                <th style={th}>Type</th>
                <th style={{ ...th, textAlign: "right" }}>Qty</th>
                <th style={th}>Status</th>
                <th style={th}>Reason</th>
                <th style={th}>Submitted</th>
              </tr>
            </thead>
            <tbody>
              {orders.slice(0, 20).map((o) => (
                <tr key={o.client_order_id} style={{ borderTop: "1px solid #e2e8f0" }}>
                  <td style={td}>{o.symbol}</td>
                  <td style={{ ...td, color: o.side === "buy" ? "#15803d" : "#b91c1c", fontWeight: 600 }}>
                    {o.side.toUpperCase()}
                  </td>
                  <td style={td}>{o.order_type}</td>
                  <td style={{ ...td, textAlign: "right" }}>{o.quantity.toLocaleString()}</td>
                  <td style={td}><span className={`pill ${o.status}`}>{o.status}</span></td>
                  <td style={{ ...td, fontSize: 12, color: "#64748b" }}>{o.reason ?? "—"}</td>
                  <td style={td}>{new Date(o.submitted_at_ms).toLocaleTimeString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <h2 style={{ marginTop: 0 }}>Configuration versions</h2>
        {versions.length === 0 ? (
          <p>No versions yet. <Link href={`/bots/${bot.id}/config`}>Create a draft</Link>.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", background: "#f8fafc" }}>
                <th style={th}>Version</th><th style={th}>Status</th><th style={th}>By</th>
                <th style={th}>Approved by</th><th style={th}>Applied</th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => (
                <tr key={v.version} style={{ borderTop: "1px solid #e2e8f0" }}>
                  <td style={td}>#{v.version}</td>
                  <td style={td}><span className={`pill ${v.status}`}>{v.status}</span></td>
                  <td style={td}>{v.created_by}</td>
                  <td style={td}>{v.approved_by ?? <em style={{ color: "#94a3b8" }}>—</em>}</td>
                  <td style={td}>{v.applied_at_ms ? new Date(v.applied_at_ms).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Audit trail</h2>
        {audit.length === 0 ? (
          <p>No events.</p>
        ) : (
          <ul style={{ paddingLeft: 18, fontSize: 14 }}>
            {audit.slice(0, 20).map((e) => (
              <li key={e.id}>
                <b>{e.action}</b> by {e.actor_email} ({e.actor_role}){" "}
                — {new Date(e.at_ms).toLocaleString()}
                {e.outcome === "error" && <span style={{ color: "#b91c1c" }}> — {e.reason}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

const th: React.CSSProperties = { padding: "10px 12px", fontWeight: 600, fontSize: 13 };
const td: React.CSSProperties = { padding: "10px 12px", fontSize: 14 };
