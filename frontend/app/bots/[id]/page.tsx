"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, useRef, useCallback } from "react";
import AuthGuard from "@/components/AuthGuard";
import Navigation from "@/components/Navigation";
import { api, getUser, getToken } from "@/lib/api";
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
  const [lastRefreshed, setLastRefreshed] = useState<number>(0);
  const [tab, setTab] = useState<"activity" | "config" | "audit">("activity");
  const [sseConnected, setSseConnected] = useState(false);
  const sseRef = useRef<EventSource | null>(null);

  const refresh = useCallback(async () => {
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
      setLastRefreshed(Date.now());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed");
    }
  }, [id]);

  // Initial load
  useEffect(() => {
    refresh();
  }, [refresh]);

  // SSE real-time stream when bot is running
  useEffect(() => {
    if (bot?.state !== "running") {
      // Clean up SSE if bot stopped
      if (sseRef.current) {
        sseRef.current.close();
        sseRef.current = null;
        setSseConnected(false);
      }
      return;
    }

    const token = getToken();
    if (!token) return;

    // SSE must connect directly to the backend — Vercel's rewrite proxy buffers responses
    const sseBase = process.env.NEXT_PUBLIC_SSE_BASE || process.env.NEXT_PUBLIC_API_BASE || "";
    const url = `${sseBase}/api/bots/${id}/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    sseRef.current = es;

    es.addEventListener("connected", () => {
      setSseConnected(true);
    });

    es.addEventListener("order", (e) => {
      const data = JSON.parse(e.data);
      setOrders(prev => {
        const idx = prev.findIndex(o => o.client_order_id === data.client_order_id);
        if (idx >= 0) {
          const updated = [...prev];
          updated[idx] = { ...updated[idx], ...data };
          return updated;
        }
        return [data, ...prev];
      });
      setLastRefreshed(Date.now());
    });

    es.addEventListener("fill", (e) => {
      const data = JSON.parse(e.data);
      setFills(prev => {
        if (prev.some(f => f.id === data.id)) return prev;
        return [data, ...prev];
      });
      setLastRefreshed(Date.now());
    });

    es.addEventListener("position", (e) => {
      const data = JSON.parse(e.data);
      setPositions(prev => {
        const idx = prev.findIndex(p => p.symbol === data.symbol);
        if (idx >= 0) {
          const updated = [...prev];
          updated[idx] = { ...updated[idx], ...data, bot_id: id };
          return updated;
        }
        return [...prev, { ...data, bot_id: id }];
      });
      setLastRefreshed(Date.now());
    });

    es.onerror = () => {
      setSseConnected(false);
      // EventSource auto-reconnects by default
    };

    return () => {
      es.close();
      sseRef.current = null;
      setSseConnected(false);
    };
  }, [bot?.state, id]);

  if (err) return <p className="error">{err}</p>;
  if (!bot) return <p>Loading…</p>;

  async function act(fn: (id: string) => Promise<Bot>) {
    try { await fn(id); await refresh(); }
    catch (e) { alert(e instanceof Error ? e.message : "failed"); }
  }

  // Compute stats
  const totalPnl = positions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0);
  const filledOrders = orders.filter(o => o.status === "filled").length;
  const rejectedOrders = orders.filter(o => o.status === "rejected").length;
  const winTrades = fills.filter(f => f.side === "sell" && f.price > 0).length;
  const totalTrades = fills.length;

  return (
    <>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
            <h1 style={{ marginBottom: 0 }}>{bot.name}</h1>
            <span className={`pill ${bot.state}`}>{bot.state}</span>
            {bot.state === "running" && (
              <span style={{
                fontSize: 11, display: "flex", alignItems: "center", gap: 4,
                color: sseConnected ? "#008265" : "#b37600",
              }}>
                <span style={{
                  width: 6, height: 6, borderRadius: "50%",
                  background: sseConnected ? "#008265" : "#b37600",
                  display: "inline-block", animation: "pulse 2s infinite",
                }} />
                {sseConnected ? "Live" : "Connecting…"}
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: "#aaaaaa" }}>
            <code style={{ fontSize: 11 }}>{bot.id}</code>
            <span style={{ margin: "0 8px", color: "#e8eaeb" }}>·</span>
            {bot.owner_email}
            {lastRefreshed > 0 && (
              <>
                <span style={{ margin: "0 8px", color: "#e8eaeb" }}>·</span>
                <span>Updated {new Date(lastRefreshed).toLocaleTimeString()}</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Actions */}
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
        <button className="btn ghost" onClick={refresh} style={{ marginLeft: "auto" }}>
          ↻ Refresh
        </button>
      </div>

      {/* Stats Row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
        <StatCard label="Realized PnL" value={`${totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(2)}`} color={totalPnl >= 0 ? "#008265" : "#cc2626"} />
        <StatCard label="Filled Orders" value={String(filledOrders)} color="#0e0e0e" subtext={rejectedOrders > 0 ? `${rejectedOrders} rejected` : undefined} subtextColor="#cc2626" />
        <StatCard label="Open Positions" value={String(positions.filter(p => p.quantity !== 0).length)} color="#0e0e0e" />
        <StatCard label="Total Fills" value={String(totalTrades)} color="#0e0e0e" subtext={totalTrades > 0 ? `${((winTrades / totalTrades) * 100).toFixed(0)}% win rate` : undefined} subtextColor="#008265" />
      </div>

      {/* Equity Curve (always shown) */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h2 style={{ marginBottom: 14 }}>Equity Curve</h2>
        {fills.length === 0 ? (
          <div style={{ padding: "32px 0", textAlign: "center", color: "#aaaaaa" }}>
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" style={{ margin: "0 auto 12px", display: "block", opacity: 0.4 }}>
              <path d="M6 36 L14 24 L22 28 L30 18 L38 22 L42 12" stroke="#4f46e5" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="4 4" />
            </svg>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>No trades yet</div>
            <div style={{ fontSize: 12 }}>The equity curve will appear once the bot executes its first trade</div>
          </div>
        ) : (
          <EquityChart fills={fills} />
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 0, borderBottom: "2px solid #e8eaeb", marginBottom: 16 }}>
        {(["activity", "config", "audit"] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "10px 20px", fontSize: 14, fontWeight: 600, cursor: "pointer",
              background: "transparent", border: "none",
              color: tab === t ? "#4f46e5" : "#686868",
              borderBottom: tab === t ? "2px solid #4f46e5" : "2px solid transparent",
              marginBottom: -2, transition: "color 0.15s, border-color 0.15s",
              textTransform: "capitalize",
            }}
          >
            {t === "activity" ? `Activity (${orders.length})` : t === "config" ? `Config (${versions.length})` : `Audit (${audit.length})`}
          </button>
        ))}
      </div>

      {/* Activity Tab */}
      {tab === "activity" && (
        <>
          {/* Open Positions */}
          <div className="card" style={{ marginBottom: 16, padding: 0, overflow: "hidden" }}>
            <div style={{ padding: "14px 20px", borderBottom: "1px solid #e8eaeb", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h2 style={{ margin: 0 }}>Open Positions</h2>
              <span style={{ fontSize: 12, color: "#aaaaaa" }}>{positions.filter(p => p.quantity !== 0).length} active</span>
            </div>
            {positions.filter(p => p.quantity !== 0).length === 0 ? (
              <div style={{ padding: "28px 20px", textAlign: "center", color: "#aaaaaa", fontSize: 13 }}>
                No open positions — the bot will open positions when strategy conditions are met
              </div>
            ) : (
              <table>
                <thead><tr>
                  <th>Symbol</th><th style={{ textAlign: "right" }}>Qty</th>
                  <th style={{ textAlign: "right" }}>Avg price</th>
                  <th style={{ textAlign: "right" }}>Realized PnL</th><th>Updated</th>
                </tr></thead>
                <tbody>
                  {positions.filter(p => p.quantity !== 0).map((p) => (
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
            )}
          </div>

          {/* Recent Orders */}
          <div className="card" style={{ marginBottom: 16, padding: 0, overflow: "hidden" }}>
            <div style={{ padding: "14px 20px", borderBottom: "1px solid #e8eaeb", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h2 style={{ margin: 0 }}>Recent Orders</h2>
              <span style={{ fontSize: 12, color: "#aaaaaa" }}>{orders.length} total</span>
            </div>
            {orders.length === 0 ? (
              <div style={{ padding: "28px 20px", textAlign: "center", color: "#aaaaaa", fontSize: 13 }}>
                No orders submitted yet — orders will appear here as the bot trades
              </div>
            ) : (
              <table>
                <thead><tr>
                  <th>Symbol</th><th>Side</th><th>Type</th>
                  <th style={{ textAlign: "right" }}>Qty</th>
                  <th>Status</th><th>Reason</th><th>Time</th>
                </tr></thead>
                <tbody>
                  {orders.slice(0, 20).map((o) => (
                    <tr key={o.client_order_id}>
                      <td style={{ fontWeight: 600 }}>{o.symbol}</td>
                      <td>
                        <span style={{
                          display: "inline-flex", alignItems: "center", gap: 4,
                          padding: "2px 8px", borderRadius: 3, fontSize: 11, fontWeight: 700,
                          background: o.side === "buy" ? "#edfaf7" : "#fff0f0",
                          color: o.side === "buy" ? "#008265" : "#cc2626",
                        }}>
                          {o.side === "buy" ? "▲" : "▼"} {o.side.toUpperCase()}
                        </span>
                      </td>
                      <td style={{ color: "#686868" }}>{o.order_type}</td>
                      <td style={{ textAlign: "right" }}>{o.quantity?.toLocaleString() ?? "—"}</td>
                      <td><span className={`pill ${o.status}`}>{o.status}</span></td>
                      <td style={{ fontSize: 12, color: "#aaaaaa", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{o.reason ?? "—"}</td>
                      <td style={{ fontSize: 12, color: "#aaaaaa", whiteSpace: "nowrap" }}>{new Date(o.submitted_at_ms).toLocaleTimeString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Recent Fills */}
          <div className="card" style={{ marginBottom: 16, padding: 0, overflow: "hidden" }}>
            <div style={{ padding: "14px 20px", borderBottom: "1px solid #e8eaeb", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h2 style={{ margin: 0 }}>Recent Fills</h2>
              <span style={{ fontSize: 12, color: "#aaaaaa" }}>{fills.length} total</span>
            </div>
            {fills.length === 0 ? (
              <div style={{ padding: "28px 20px", textAlign: "center", color: "#aaaaaa", fontSize: 13 }}>
                No fills yet — fills appear when orders are successfully executed
              </div>
            ) : (
              <table>
                <thead><tr>
                  <th>Symbol</th><th>Side</th>
                  <th style={{ textAlign: "right" }}>Qty</th>
                  <th style={{ textAlign: "right" }}>Price</th>
                  <th style={{ textAlign: "right" }}>Fees</th>
                  <th>Time</th>
                </tr></thead>
                <tbody>
                  {fills.slice(0, 20).map((f) => (
                    <tr key={f.id}>
                      <td style={{ fontWeight: 600 }}>{f.symbol}</td>
                      <td>
                        <span style={{
                          display: "inline-flex", alignItems: "center", gap: 4,
                          padding: "2px 8px", borderRadius: 3, fontSize: 11, fontWeight: 700,
                          background: f.side === "buy" ? "#edfaf7" : "#fff0f0",
                          color: f.side === "buy" ? "#008265" : "#cc2626",
                        }}>
                          {f.side === "buy" ? "▲" : "▼"} {f.side.toUpperCase()}
                        </span>
                      </td>
                      <td style={{ textAlign: "right" }}>{f.quantity.toLocaleString()}</td>
                      <td style={{ textAlign: "right", fontFamily: "monospace" }}>{f.price.toFixed(4)}</td>
                      <td style={{ textAlign: "right", color: "#aaaaaa" }}>{f.fees.toFixed(2)}</td>
                      <td style={{ fontSize: 12, color: "#aaaaaa", whiteSpace: "nowrap" }}>{new Date(f.filled_at_ms).toLocaleTimeString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {/* Config Tab */}
      {tab === "config" && (
        <>
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
        </>
      )}

      {/* Audit Tab */}
      {tab === "audit" && (
        <div className="card">
          <h2 style={{ marginBottom: 14 }}>Audit trail</h2>
          {audit.length === 0 ? (
            <p style={{ color: "#aaaaaa" }}>No events recorded yet.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
              {audit.slice(0, 30).map((e, i) => (
                <div key={e.id} style={{
                  display: "flex", gap: 12, fontSize: 13, padding: "10px 0",
                  borderBottom: i < audit.length - 1 ? "1px solid #f2f3f4" : "none",
                }}>
                  <span style={{ color: "#aaaaaa", whiteSpace: "nowrap", flexShrink: 0, fontFamily: "monospace", fontSize: 11 }}>
                    {new Date(e.at_ms).toLocaleString()}
                  </span>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{
                      display: "inline-block", width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                      background: e.outcome === "error" ? "#cc2626" : e.action.includes("start") ? "#008265" : e.action.includes("stop") ? "#b37600" : "#4f46e5",
                    }} />
                    <span>
                      <b style={{ color: "#0e0e0e" }}>{e.action}</b>
                      <span style={{ color: "#aaaaaa" }}> by {e.actor_email} ({e.actor_role})</span>
                      {e.outcome === "error" && <span style={{ color: "#cc2626" }}> — {e.reason}</span>}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Pulse animation */}
      <style>{`
        @keyframes pulse {
          0% { opacity: 1; }
          50% { opacity: 0.4; }
          100% { opacity: 1; }
        }
      `}</style>
    </>
  );
}

function StatCard({ label, value, color, subtext, subtextColor }: {
  label: string; value: string; color: string; subtext?: string; subtextColor?: string;
}) {
  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "#aaaaaa", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color, letterSpacing: "-0.03em", lineHeight: 1 }}>{value}</div>
      {subtext && <div style={{ fontSize: 11, color: subtextColor || "#aaaaaa", marginTop: 6 }}>{subtext}</div>}
    </div>
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

  const W = 600, H = 140, PAD = 8;
  const minY = Math.min(...points);
  const maxY = Math.max(...points);
  const rangeY = maxY - minY || 1;
  const toX = (i: number) => PAD + (i / (points.length - 1)) * (W - PAD * 2);
  const toY = (v: number) => H - PAD - ((v - minY) / rangeY) * (H - PAD * 2);
  const polyline = points.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");
  const zeroY = toY(0).toFixed(1);
  const lastPnl = points[points.length - 1];
  const color = lastPnl >= 0 ? "#008265" : "#cc2626";
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
