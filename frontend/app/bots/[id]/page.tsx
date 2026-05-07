"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, useRef, useCallback } from "react";
import AuthGuard from "@/components/AuthGuard";
import Navigation from "@/components/Navigation";
import { api, getUser, getToken } from "@/lib/api";
import { can } from "@/lib/rbac";
import type { AnalyticsBucket, AuditEvent, BalanceSnapshot, Bot, BrokerBalance, ConfigVersion, ContractsSummary, Fill, Order, Position, TickEvent } from "@/lib/types";

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
  const [balance, setBalance] = useState<BrokerBalance | null>(null);
  const [contractsSummary, setContractsSummary] = useState<ContractsSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<number>(0);
  const [tab, setTab] = useState<"activity" | "analytics" | "config" | "audit">("activity");
  const [balanceHistory, setBalanceHistory] = useState<BalanceSnapshot[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsBucket[]>([]);
  const [timeRange, setTimeRange] = useState<"1h" | "24h" | "7d" | "30d">("24h");
  const [sseConnected, setSseConnected] = useState(false);
  const [panelOpen, setPanelOpen] = useState(true);
  const [ticks, setTicks] = useState<Record<string, TickEvent>>({});
  const sseRef = useRef<EventSource | null>(null);

  const refresh = useCallback(async () => {
    try {
      const now = Date.now();
      // Window length per range
      const ranges: Record<typeof timeRange, number> = {
        "1h": 3_600_000, "24h": 86_400_000,
        "7d": 604_800_000, "30d": 2_592_000_000,
      };
      // Bucket granularity per range — chosen so charts have ~24-60 buckets
      // (more is noise, less is uninformative). 24h-day-bucket = 1 bar = useless.
      const granularity: Record<typeof timeRange, "minute" | "hour" | "day"> = {
        "1h": "minute", "24h": "hour",
        "7d": "hour", "30d": "day",
      };
      // Scale list-endpoint limit so 30-day windows aren't truncated to 100.
      const listLimit: Record<typeof timeRange, number> = {
        "1h": 100, "24h": 500, "7d": 2000, "30d": 5000,
      };
      const since_ms = now - ranges[timeRange];
      const lim = listLimit[timeRange];

      const [b, v, pos, ord, fl, a, summary, hist, an] = await Promise.all([
        api.getBot(id),
        api.listConfigs(id),
        api.listPositions(id),
        api.listOrders(id, lim, since_ms),
        api.listFills(id, lim, since_ms),
        api.listAudit(),
        // Pass the window so the headline stat cards reflect the selected range,
        // not all-time. Without this, "Last hour" showed all-time win rate.
        api.contractsSummary(id, since_ms, now).catch(() => null),
        api.listBalanceHistory(id, since_ms),
        api.getAnalytics(id, since_ms, now, granularity[timeRange]).catch(() => []),
      ]);
      setBot(b);
      setVersions(v);
      setPositions(pos);
      setOrders(ord);
      setFills(fl);
      // Audit endpoint isn't time-filterable server-side; clip client-side
      // to the window so the audit tab matches the selected range too.
      setAudit(a.filter((e) =>
        (e.resource_id === id || e.resource_id.startsWith(`${id}:`)) &&
        e.at_ms >= since_ms
      ));
      setContractsSummary(summary);
      setBalanceHistory(hist);
      setAnalytics(an);
      setLastRefreshed(Date.now());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed");
    }
    api.brokerBalance(id).then(setBalance).catch(() => {});
  }, [id, timeRange]);

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

    // Use the relative URL so it goes through the Vercel Next.js proxy
    // This avoids Mixed Content (HTTPS -> HTTP) errors
    const url = `/api/bots/${id}/stream?token=${encodeURIComponent(token)}`;
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

    es.addEventListener("tick", (e) => {
      const data = JSON.parse(e.data) as TickEvent;
      setTicks(prev => ({ ...prev, [data.symbol]: data }));
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
    <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
      {/* Main Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
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
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginLeft: "auto" }}>
          <select 
            value={timeRange} 
            onChange={(e) => setTimeRange(e.target.value as any)}
            className="btn ghost"
            style={{ padding: "4px 12px", height: 32, fontSize: 13 }}
          >
            <option value="1h">Last hour</option>
            <option value="24h">Last 24h</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
          <button className="btn ghost" onClick={refresh}>
            ↻ Refresh
          </button>
        </div>
        {bot.state === "running" && (
          <button
            className="btn ghost"
            onClick={() => setPanelOpen(o => !o)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              background: panelOpen ? "#eff6ff" : undefined,
              border: panelOpen ? "1px solid #4f46e5" : undefined,
              color: panelOpen ? "#4f46e5" : undefined,
            }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <rect x="1" y="1" width="12" height="12" rx="2" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M9 1v12" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M5 5h1M5 7h1M5 9h1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
            </svg>
            Monitor
          </button>
        )}
      </div>

      {/* Strategy monitor panel */}
      {/* Moved outside the main content column */}
      
      {/* Stats Row — broker balance + contract P&L (the source-of-truth metrics).
          For Deriv binary-option bots, position-based PnL is meaningless — every
          contract is a fixed-stake bet, not a forex position. So we show:
          - actual broker balance (live)
          - net change since session start
          - contract counts and win rate (with profitability threshold context) */}
      {(() => {
        const cs = contractsSummary;
        const settled = cs ? cs.won_count + cs.lost_count : 0;
        const winPct = cs && settled > 0 ? cs.win_rate * 100 : null;
        const winColor = winPct == null ? "#aaaaaa"
          : winPct >= 52 ? "#008265"
          : winPct >= 50 ? "#b37600"
          : "#cc2626";
        const isDerivBot = bot.active_config_version != null
          && versions.find(v => v.version === bot.active_config_version)?.config?.broker?.type === "deriv";

        // Virtual Allocation Logic
        const allocation = bot.allocation;
        const pnl = cs?.realized_pnl ?? 0;
        
        if (allocation) {
          const virtualBalance = allocation + pnl;
          const pnlPct = (pnl / allocation) * 100;
          const pnlValue = `${pnl >= 0 ? "+" : ""}$${pnl.toFixed(2)}`;
          const pnlPctStr = `${pnl >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%`;

          return (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
              <StatCard label="Virtual Balance" value={`$${virtualBalance.toFixed(2)}`} color="#4f46e5"
                subtext={`$${allocation.toFixed(2)} starting allocation`} subtextColor="#aaaaaa" />
              <StatCard label="Virtual P&L" value={pnlValue} color={pnl >= 0 ? "#008265" : "#cc2626"}
                subtext={`${pnlPctStr} change on allocation`} subtextColor={pnl >= 0 ? "#008265" : "#cc2626"} />
              <StatCard label="Contracts (open / won / lost)"
                value={cs ? `${cs.open_count} / ${cs.won_count} / ${cs.lost_count}` : "—"}
                color="#0e0e0e"
                subtext={cs && cs.total_count > 0 ? `${cs.total_count} total` : undefined} />
              <StatCard label="Win rate"
                value={winPct != null ? `${winPct.toFixed(1)}%` : "—"}
                color={winColor}
                subtext={winPct != null ? (winPct >= 52 ? "above breakeven" : "below 52% breakeven") : undefined}
                subtextColor={winColor} />
            </div>
          );
        }

        // Standard Balance Logic (Legacy/Master)
        const balValue = balance && balance.available != null && balance.currency
          ? `${balance.currency === "USD" ? "$" : ""}${balance.available.toFixed(2)}`
          : "—";
        const startBal = balance?.starting_balance ?? null;
        const netChange = (balance?.available != null && startBal != null)
          ? balance.available - startBal
          : null;
        const startStr = startBal != null
          ? `${balance?.starting_balance_currency === "USD" ? "$" : ""}${startBal.toFixed(2)}`
          : "—";
        const netStr = netChange == null
          ? (startBal == null ? "baseline not yet captured" : undefined)
          : `${netChange >= 0 ? "+" : ""}$${netChange.toFixed(2)} since baseline (${startStr})`;
        const netColor = netChange == null ? "#aaaaaa" : netChange >= 0 ? "#008265" : "#cc2626";

        const pnlValue = cs ? `${cs.realized_pnl >= 0 ? "+" : ""}$${cs.realized_pnl.toFixed(2)}` : "—";
        const pnlColor = cs ? (cs.realized_pnl >= 0 ? "#008265" : "#cc2626") : "#aaaaaa";

        return (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
            <StatCard label="Broker balance" value={balValue} color="#0e0e0e"
              subtext={netStr} subtextColor={netColor} />
            <StatCard label={isDerivBot ? "Contracts P&L (tracked)" : "Realized PnL"}
              value={pnlValue} color={pnlColor}
              subtext={isDerivBot ? "internal record — broker balance is source of truth" : undefined}
              subtextColor="#aaaaaa" />
            <StatCard label="Contracts (open / won / lost)"
              value={cs ? `${cs.open_count} / ${cs.won_count} / ${cs.lost_count}` : "—"}
              color="#0e0e0e"
              subtext={cs && cs.total_count > 0 ? `${cs.total_count} total` : undefined} />
            <StatCard label="Win rate"
              value={winPct != null ? `${winPct.toFixed(1)}%` : "—"}
              color={winColor}
              subtext={winPct != null ? (winPct >= 52 ? "above breakeven" : "below 52% breakeven") : undefined}
              subtextColor={winColor} />
          </div>
        );
      })()}

      {/* Equity Curve — real broker balance series. */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h2 style={{ marginBottom: 4 }}>Live Equity Curve</h2>
        <p style={{ fontSize: 11, color: "#aaaaaa", marginTop: 0, marginBottom: 14 }}>
          Real broker balance history. High-water mark tracking and drawdown are measured against this series.
        </p>
        {balanceHistory.length < 2 ? (
          <div style={{ padding: "32px 0", textAlign: "center", color: "#aaaaaa" }}>
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" style={{ margin: "0 auto 12px", display: "block", opacity: 0.4 }}>
              <path d="M6 36 L14 24 L22 28 L30 18 L38 22 L42 12" stroke="#4f46e5" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="4 4" />
            </svg>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Insufficient history</div>
            <div style={{ fontSize: 12 }}>The equity curve needs at least two data points to render.</div>
          </div>
        ) : (
          <EquityChart data={balanceHistory} baseline={balance?.starting_balance} />
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 0, borderBottom: "2px solid #e8eaeb", marginBottom: 16 }}>
        {(["activity", "analytics", "config", "audit"] as const).map(t => (
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
            {t === "activity" ? `Activity (${orders.length})` : t === "config" ? `Config (${versions.length})` : t === "analytics" ? "Analytics" : `Audit (${audit.length})`}
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
      {/* Analytics Tab */}
      {tab === "analytics" && (
        <>
          <NarrativeCard botId={id} timeRange={timeRange} />
        <div className="card" style={{ padding: 0, overflow: "hidden", marginBottom: 16 }}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid #e8eaeb" }}>
            <h2 style={{ margin: 0 }}>Performance Analytics ({timeRange})</h2>
          </div>
          {analytics.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center", color: "#aaaaaa" }}>
              No contract data available for this time range to generate analytics.
            </div>
          ) : (
            <table>
              <thead><tr>
                <th>Time Bucket</th>
                <th style={{ textAlign: "right" }}>Contracts</th>
                <th style={{ textAlign: "right" }}>Win Rate</th>
                <th style={{ textAlign: "right" }}>PnL</th>
                <th style={{ textAlign: "right" }}>Staked</th>
              </tr></thead>
              <tbody>
                {analytics.map((b) => (
                  <tr key={b.bucket_ms}>
                    <td><b>{new Date(b.bucket_ms).toLocaleString(undefined, {
                      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
                    })}</b></td>
                    <td style={{ textAlign: "right" }}>{b.total}</td>
                    <td style={{ textAlign: "right", color: b.win_rate >= 0.52 ? "#008265" : "#cc2626" }}>
                      {(b.win_rate * 100).toFixed(1)}%
                    </td>
                    <td style={{ textAlign: "right" }} className={b.pnl >= 0 ? "positive" : "negative"}>
                      {b.pnl >= 0 ? "+" : ""}{b.pnl.toFixed(2)}
                    </td>
                    <td style={{ textAlign: "right", color: "#686868" }}>${b.staked.toFixed(2)}</td>
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

      {/* Animations */}
      <style>{`
        @keyframes pulse {
          0% { opacity: 1; }
          50% { opacity: 0.4; }
          100% { opacity: 1; }
        }
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
      `}</style>
      </div>

      {/* Strategy Monitor Sidegrid */}
      <StrategyPanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        ticks={ticks}
        botState={bot.state}
        sseConnected={sseConnected}
      />
    </div>
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

const SIGNAL_META: Record<string, { color: string; bg: string; icon: string }> = {
  warming_up:  { color: "#686868", bg: "#f2f3f4", icon: "⏳" },
  watching:    { color: "#4f46e5", bg: "#eff6ff", icon: "👁" },
  cooldown:    { color: "#b37600", bg: "#fffbeb", icon: "⏸" },
  signal_buy:  { color: "#008265", bg: "#edfaf7", icon: "▲" },
  signal_sell: { color: "#cc2626", bg: "#fff0f0", icon: "▼" },
  weak_signal: { color: "#9c4f00", bg: "#fff7ed", icon: "~" },
};

function StrategyPanel({
  open, onClose, ticks, botState, sseConnected,
}: {
  open: boolean;
  onClose: () => void;
  ticks: Record<string, TickEvent>;
  botState: string;
  sseConnected: boolean;
}) {
  if (!open) return null;

  const symbols = Object.keys(ticks);

  return (
    <>
      {/* Panel */}
      <div style={{
        width: 340, flexShrink: 0,
        background: "#fff",
        border: "1px solid #e8eaeb",
        borderRadius: 8,
        display: "flex", flexDirection: "column",
        overflow: "hidden",
        position: "sticky",
        top: 24,
        maxHeight: "calc(100vh - 48px)",
        animation: "slideIn 0.22s ease",
      }}>
        {/* Panel header */}
        <div style={{
          padding: "16px 20px", borderBottom: "1px solid #e8eaeb",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          position: "sticky", top: 0, background: "#fff", zIndex: 1,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="1" y="1" width="14" height="14" rx="2.5" stroke="#4f46e5" strokeWidth="1.5"/>
              <path d="M10 1v14" stroke="#4f46e5" strokeWidth="1.5"/>
              <path d="M5 6h2M5 8h2M5 10h2" stroke="#4f46e5" strokeWidth="1.2" strokeLinecap="round"/>
            </svg>
            <span style={{ fontWeight: 700, fontSize: 14, color: "#0e0e0e" }}>Strategy Monitor</span>
            {sseConnected && (
              <span style={{
                width: 6, height: 6, borderRadius: "50%",
                background: "#008265", display: "inline-block",
                animation: "pulse 2s infinite",
              }} />
            )}
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none", border: "none", cursor: "pointer",
              color: "#686868", fontSize: 18, lineHeight: 1, padding: "2px 4px",
            }}
          >×</button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, padding: "16px 20px", display: "flex", flexDirection: "column", gap: 20, overflowY: "auto" }}>
          {botState !== "running" ? (
            <div style={{ textAlign: "center", padding: "32px 0", color: "#aaaaaa" }}>
              <div style={{ fontSize: 28, marginBottom: 12 }}>⏹</div>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Bot is not running</div>
              <div style={{ fontSize: 12 }}>Start the bot to see live strategy state.</div>
            </div>
          ) : symbols.length === 0 ? (
            <div style={{ textAlign: "center", padding: "32px 0", color: "#aaaaaa" }}>
              <div style={{ fontSize: 28, marginBottom: 12, animation: "pulse 2s infinite" }}>📡</div>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Waiting for first tick…</div>
              <div style={{ fontSize: 12 }}>Strategy data will appear here once the bot processes its first market bar.</div>
            </div>
          ) : (
            symbols.map(sym => <SymbolCard key={sym} tick={ticks[sym]} />)
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: "12px 20px", borderTop: "1px solid #e8eaeb",
          fontSize: 11, color: "#aaaaaa", textAlign: "center",
        }}>
          Updates every ~1 second via live stream
        </div>
      </div>
    </>
  );
}

function SymbolCard({ tick }: { tick: TickEvent }) {
  const meta = SIGNAL_META[tick.signal.status] ?? SIGNAL_META.watching;
  const age = Math.round((Date.now() - tick.ts_ms) / 1000);
  const indicators = Object.entries(tick.indicators);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Symbol + price */}
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <span style={{ fontWeight: 700, fontSize: 15, color: "#0e0e0e" }}>{tick.symbol}</span>
        <span style={{ fontFamily: "ui-monospace, Menlo, monospace", fontWeight: 700, fontSize: 16, color: "#0e0e0e" }}>
          {tick.mark_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 5 })}
        </span>
      </div>

      {/* Signal status badge */}
      <div style={{
        borderRadius: 8, padding: "10px 12px",
        background: meta.bg, border: `1px solid ${meta.color}22`,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
          <span style={{ fontSize: 13 }}>{meta.icon}</span>
          <span style={{ fontWeight: 700, fontSize: 13, color: meta.color }}>{tick.signal.label}</span>
        </div>
        <div style={{ fontSize: 12, color: "#686868", lineHeight: 1.5 }}>{tick.signal.detail}</div>
        {tick.signal.cooldown_remaining > 0 && (
          <div style={{
            marginTop: 6, height: 4, borderRadius: 2,
            background: "#e8eaeb", overflow: "hidden",
          }}>
            <div style={{
              height: "100%", borderRadius: 2,
              background: meta.color,
              width: `${Math.min(100, (tick.signal.cooldown_remaining / 10) * 100)}%`,
              transition: "width 0.5s",
            }} />
          </div>
        )}
      </div>

      {/* Data warm-up progress bar */}
      {tick.signal.status === "warming_up" && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#aaaaaa", marginBottom: 4 }}>
            <span>Warming up</span>
            <span>{tick.bars_available} / {tick.bars_needed} bars</span>
          </div>
          <div style={{ height: 4, borderRadius: 2, background: "#e8eaeb", overflow: "hidden" }}>
            <div style={{
              height: "100%", borderRadius: 2, background: "#4f46e5",
              width: `${Math.min(100, (tick.bars_available / tick.bars_needed) * 100)}%`,
              transition: "width 0.5s",
            }} />
          </div>
        </div>
      )}

      {/* Indicators */}
      {indicators.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#aaaaaa", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
            Indicators
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {indicators.map(([key, val]) => (
              <div key={key} style={{
                background: "#f8fafc", borderRadius: 6, padding: "8px 10px",
              }}>
                <div style={{ fontSize: 10, color: "#aaaaaa", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 2 }}>
                  {key.replace(/_/g, " ")}
                </div>
                <div style={{ fontFamily: "ui-monospace, Menlo, monospace", fontSize: 13, fontWeight: 600, color: "#0e0e0e" }}>
                  {typeof val === "number" ? val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 5 }) : val}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Position + meta */}
      <div style={{ display: "flex", gap: 8 }}>
        <div style={{
          flex: 1, background: "#f8fafc", borderRadius: 6, padding: "8px 10px",
          display: "flex", flexDirection: "column", gap: 2,
        }}>
          <div style={{ fontSize: 10, color: "#aaaaaa", textTransform: "uppercase", letterSpacing: "0.05em" }}>Position</div>
          <div style={{ fontFamily: "ui-monospace, Menlo, monospace", fontSize: 13, fontWeight: 600, color: tick.position_qty !== 0 ? "#0e0e0e" : "#aaaaaa" }}>
            {tick.position_qty !== 0 ? tick.position_qty.toLocaleString() : "Flat"}
          </div>
        </div>
        <div style={{
          flex: 1, background: "#f8fafc", borderRadius: 6, padding: "8px 10px",
          display: "flex", flexDirection: "column", gap: 2,
        }}>
          <div style={{ fontSize: 10, color: "#aaaaaa", textTransform: "uppercase", letterSpacing: "0.05em" }}>Last update</div>
          <div style={{ fontSize: 13, color: "#686868" }}>
            {age < 5 ? "Just now" : `${age}s ago`}
          </div>
        </div>
      </div>

      {/* Bars available */}
      <div style={{ fontSize: 11, color: "#aaaaaa", textAlign: "right" }}>
        {tick.bars_available} bars loaded · {tick.strategy_id}
      </div>
    </div>
  );
}

function EquityChart({ data, baseline }: { data: BalanceSnapshot[], baseline?: number | null }) {
  const points = data.map(d => d.balance);
  const baselineVal = baseline ?? points[0];

  const W = 600, H = 140, PAD = 8;
  const minY = Math.min(...points, baselineVal);
  const maxY = Math.max(...points, baselineVal);
  const rangeY = maxY - minY || 1;
  const toX = (i: number) => PAD + (i / (points.length - 1)) * (W - PAD * 2);
  const toY = (v: number) => H - PAD - ((v - minY) / rangeY) * (H - PAD * 2);
  
  const polyline = points.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");
  const baselineY = toY(baselineVal).toFixed(1);
  const lastVal = points[points.length - 1];
  const netChange = lastVal - baselineVal;
  const color = netChange >= 0 ? "#008265" : "#cc2626";
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
        <line x1={PAD} y1={baselineY} x2={W - PAD} y2={baselineY} stroke="#e8eaeb" strokeWidth={1} strokeDasharray="4 4"/>
        <polygon points={areaPoints} fill="url(#eq-grad)" />
        <polyline points={polyline} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
        <circle cx={toX(points.length - 1)} cy={toY(lastVal)} r={4} fill={color} />
      </svg>
      <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 13, color: "#aaaaaa" }}>
        <span>{data.length} observations</span>
        <span>Net change: <span style={{ fontWeight: 700, color }}>{netChange >= 0 ? "+" : ""}{netChange.toFixed(2)}</span></span>
      </div>
    </div>
  );
}


function NarrativeCard({ botId, timeRange }: {
  botId: string;
  timeRange: "1h" | "24h" | "7d" | "30d";
}) {
  const [text, setText] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function generate() {
    setErr(null);
    setLoading(true);
    try {
      const now = Date.now();
      const ranges: Record<typeof timeRange, number> = {
        "1h": 3_600_000, "24h": 86_400_000, "7d": 604_800_000, "30d": 2_592_000_000,
      };
      const granularity: Record<typeof timeRange, "minute" | "hour" | "day"> = {
        "1h": "minute", "24h": "hour", "7d": "hour", "30d": "day",
      };
      const r = await api.botNarrative(botId, now - ranges[timeRange], now, granularity[timeRange]);
      setText(r.narrative_md);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>✨ AI Performance Narrative ({timeRange})</h2>
        <button className="btn ghost" disabled={loading} onClick={generate} style={{ fontSize: 12 }}>
          {loading ? "Generating…" : text ? "Regenerate" : "Generate"}
        </button>
      </div>
      {err && <p style={{ color: "#cc2626", fontSize: 13 }}>{err}</p>}
      {!text && !err && !loading && (
        <p style={{ color: "#aaaaaa", fontSize: 13, margin: 0 }}>
          Click <b>Generate</b> for a plain-English summary of this windows performance.
          Uses Groq (llama-3.3-70b) on aggregated server-side data — no individual trades sent to the LLM.
        </p>
      )}
      {text && (
        <div style={{ fontSize: 14, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{text}</div>
      )}
    </div>
  );
}
