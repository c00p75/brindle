"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Navigation from "@/components/Navigation";
import { api, getUser } from "@/lib/api";
import { can } from "@/lib/rbac";
import type { AuditEvent, Bot, ConfigVersion, Fill, Order, Position } from "@/lib/types";

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
  const [fills, setFills] = useState<Fill[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    try {
      const [b, v, pos, ord, fl, a] = await Promise.all([
        api.getBot(id),
        api.listConfigs(id),
        api.listPositions(id),
        api.listOrders(id),
        api.listFills(id),
        api.listAudit(),
      ]);
      setBot(b);
      setVersions(v);
      setPositions(pos);
      setOrders(ord);
      setFills(fl);
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
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
            <h1 style={{ marginBottom: 0 }}>{bot.name}</h1>
            <span className={`pill ${bot.state}`}>{bot.state}</span>
          </div>
          <div style={{ fontSize: 12, color: "#aaaaaa" }}>
            <code style={{ fontSize: 11 }}>{bot.id}</code>
            <span style={{ margin: "0 8px", color: "#e8eaeb" }}>·</span>
            {bot.owner_email}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
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
        <div className="card" style={{ marginBottom: 16, padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid #e8eaeb" }}><h2>Open positions</h2></div>
          <table>
            <thead><tr>
              <th>Symbol</th><th style={{ textAlign: "right" }}>Qty</th>
              <th style={{ textAlign: "right" }}>Avg price</th>
              <th style={{ textAlign: "right" }}>Realized PnL</th><th>Updated</th>
            </tr></thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.symbol}>
                  <td><b>{p.symbol}</b></td>
                  <td style={{ textAlign: "right" }}>{p.quantity.toLocaleString()}</td>
                  <td style={{ textAlign: "right" }}>{p.avg_price != null ? p.avg_price.toFixed(5) : "—"}</td>
                  <td style={{ textAlign: "right" }} className={p.realized_pnl >= 0 ? "positive" : "negative"}>
                    {p.realized_pnl >= 0 ? "+" : ""}{p.realized_pnl.toFixed(2)}
                  </td>
                  <td style={{ color: "#aaaaaa", fontSize: 12 }}>{new Date(p.updated_at_ms).toLocaleTimeString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {fills.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2 style={{ marginBottom: 14 }}>Equity curve</h2>
          <EquityChart fills={fills} />
        </div>
      )}

      {orders.length > 0 && (
        <div className="card" style={{ marginBottom: 16, padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid #e8eaeb" }}><h2>Recent orders</h2></div>
          <table>
            <thead><tr>
              <th>Symbol</th><th>Side</th><th>Type</th>
              <th style={{ textAlign: "right" }}>Qty</th>
              <th>Status</th><th>Reason</th><th>Submitted</th>
            </tr></thead>
            <tbody>
              {orders.slice(0, 20).map((o) => (
                <tr key={o.client_order_id}>
                  <td style={{ fontWeight: 600 }}>{o.symbol}</td>
                  <td className={o.side === "buy" ? "positive" : "negative"}>{o.side.toUpperCase()}</td>
                  <td style={{ color: "#686868" }}>{o.order_type}</td>
                  <td style={{ textAlign: "right" }}>{o.quantity.toLocaleString()}</td>
                  <td><span className={`pill ${o.status}`}>{o.status}</span></td>
                  <td style={{ fontSize: 12, color: "#aaaaaa" }}>{o.reason ?? "—"}</td>
                  <td style={{ fontSize: 12, color: "#aaaaaa" }}>{new Date(o.submitted_at_ms).toLocaleTimeString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {versions.some((v) => v.status === "pending_approval") && can(user?.role, "config:approve") && (
        <div className="card" style={{ marginBottom: 16, borderLeft: "3px solid #b37600" }}>
          <h2 style={{ color: "#b37600", marginBottom: 12 }}>Pending approval</h2>
          {versions.filter((v) => v.status === "pending_approval").map((v) => (
            <div key={v.version} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 0", borderTop: "1px solid #f2f3f4" }}>
              <span style={{ fontSize: 14 }}>
                <b>v{v.version}</b> <span style={{ color: "#aaaaaa" }}>— drafted by {v.created_by}</span>
              </span>
              <button className="btn" style={{ fontSize: 13, padding: "7px 16px" }}
                onClick={async () => {
                  try { await api.approveConfig(id, v.version); await refresh(); }
                  catch (e) { alert(e instanceof Error ? e.message : "failed"); }
                }}>
                Approve
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="card" style={{ marginBottom: 16, padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "14px 20px", borderBottom: "1px solid #e8eaeb" }}><h2>Configuration versions</h2></div>
        {versions.length === 0 ? (
          <div style={{ padding: 20 }}>
            <p style={{ color: "#aaaaaa" }}>No versions yet. <Link href={`/bots/${bot.id}/config`}>Create a draft</Link>.</p>
          </div>
        ) : (
          <table>
            <thead><tr>
              <th>Version</th><th>Status</th><th>By</th>
              <th>Approved by</th><th>Applied</th>
              {can(user?.role, "config:rollback") && <th></th>}
            </tr></thead>
            <tbody>
              {versions.map((v) => (
                <tr key={v.version}>
                  <td><span style={{ fontFamily: "monospace", fontWeight: 700 }}>#{v.version}</span></td>
                  <td><span className={`pill ${v.status}`}>{v.status}</span></td>
                  <td style={{ fontSize: 13, color: "#686868" }}>{v.created_by}</td>
                  <td style={{ fontSize: 13, color: "#aaaaaa" }}>{v.approved_by ?? "—"}</td>
                  <td style={{ fontSize: 12, color: "#aaaaaa" }}>{v.applied_at_ms ? new Date(v.applied_at_ms).toLocaleString() : "—"}</td>
                  {can(user?.role, "config:rollback") && (
                    <td>
                      {v.status === "superseded" && (
                        <button className="btn ghost" style={{ fontSize: 12, padding: "5px 10px" }}
                          onClick={async () => {
                            if (!confirm(`Roll back to v${v.version}? A new draft will be created.`)) return;
                            try { await api.rollback(id, v.version); await refresh(); }
                            catch (e) { alert(e instanceof Error ? e.message : "failed"); }
                          }}>
                          Rollback
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2 style={{ marginBottom: 14 }}>Audit trail</h2>
        {audit.length === 0 ? (
          <p style={{ color: "#aaaaaa" }}>No events.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {audit.slice(0, 20).map((e) => (
              <div key={e.id} style={{ display: "flex", gap: 12, fontSize: 13, padding: "8px 0", borderBottom: "1px solid #f2f3f4" }}>
                <span style={{ color: "#aaaaaa", whiteSpace: "nowrap", flexShrink: 0 }}>{new Date(e.at_ms).toLocaleString()}</span>
                <span><b style={{ color: "#0e0e0e" }}>{e.action}</b>
                  <span style={{ color: "#aaaaaa" }}> by {e.actor_email} ({e.actor_role})</span>
                  {e.outcome === "error" && <span style={{ color: "#cc2626" }}> — {e.reason}</span>}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function EquityChart({ fills }: { fills: Fill[] }) {
  const sorted = [...fills].sort((a, b) => a.filled_at_ms - b.filled_at_ms);
  const points: number[] = [0];
  let cum = 0;
  for (const f of sorted) {
    cum += f.side === "sell" ? f.quantity * f.price - f.fees : -(f.quantity * f.price + f.fees);
    points.push(cum);
  }

  const W = 600, H = 120, PAD = 8;
  const minY = Math.min(...points);
  const maxY = Math.max(...points);
  const rangeY = maxY - minY || 1;
  const toX = (i: number) => PAD + (i / (points.length - 1)) * (W - PAD * 2);
  const toY = (v: number) => H - PAD - ((v - minY) / rangeY) * (H - PAD * 2);
  const polyline = points.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");
  const zeroY = toY(0).toFixed(1);
  const lastPnl = points[points.length - 1];
  const color = lastPnl >= 0 ? "#008265" : "#cc2626";
  const fillColor = lastPnl >= 0 ? "rgba(0,130,101,0.08)" : "rgba(204,38,38,0.06)";
  const areaPoints = `${toX(0).toFixed(1)},${H - PAD} ${polyline} ${toX(points.length - 1).toFixed(1)},${H - PAD}`;

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H, display: "block" }}>
        <defs>
          <linearGradient id="eq-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.15"/>
            <stop offset="100%" stopColor={color} stopOpacity="0"/>
          </linearGradient>
        </defs>
        <line x1={PAD} y1={zeroY} x2={W - PAD} y2={zeroY} stroke="#e8eaeb" strokeWidth={1} strokeDasharray="4 4"/>
        <polygon points={areaPoints} fill="url(#eq-grad)" />
        <polyline points={polyline} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
        <circle cx={toX(points.length - 1)} cy={toY(lastPnl)} r={4} fill={color} />
      </svg>
      <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 13, color: "#aaaaaa" }}>
        <span>{fills.length} fill{fills.length !== 1 ? "s" : ""}</span>
        <span>Final PnL: <span style={{ fontWeight: 700, color }}>{lastPnl >= 0 ? "+" : ""}{lastPnl.toFixed(2)}</span></span>
      </div>
    </div>
  );
}
