"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Navigation from "@/components/Navigation";
import { api } from "@/lib/api";
import type { PortfolioAnalytics, PortfolioBotRow, PortfolioDayRow } from "@/lib/types";

export default function AnalyticsPage() {
  return (
    <AuthGuard>
      <Navigation />
      <div className="container">
        <PortfolioAnalyticsView />
      </div>
    </AuthGuard>
  );
}

function PortfolioAnalyticsView() {
  const [data, setData] = useState<PortfolioAnalytics | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getPortfolioAnalytics()
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ padding: 48, color: "#aaa", textAlign: "center" }}>Loading…</div>;
  if (err) return <p className="error">{err}</p>;
  if (!data || !data.daily.length) return <p style={{ color: "#aaa" }}>No trade history yet.</p>;

  const { account, daily, bots } = data;
  const netPos = account.net_change >= 0;
  const netColor = netPos ? "#008265" : "#cc2626";
  const ddColor = "#cc2626";
  const beWr = account.break_even_win_rate;

  return (
    <>
      <div className="section-header">
        <div>
          <h1 style={{ marginBottom: 2 }}>Portfolio Analytics</h1>
          <p style={{ fontSize: 13, color: "#aaa" }}>
            Real Deriv account performance since first trade · paper trading only
          </p>
        </div>
      </div>

      {/* ── Summary cards ─────────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
        <SummaryCard
          label="Opening Balance"
          value={`$${account.opening_balance.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          sub="before first trade"
        />
        <SummaryCard
          label="Current Balance"
          value={`$${account.current_balance.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          sub={`peak $${account.peak_balance.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
        />
        <SummaryCard
          label="Net Change"
          value={`${netPos ? "+" : ""}$${Math.abs(account.net_change).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          sub={account.net_change_pct != null ? `${account.net_change_pct >= 0 ? "+" : ""}${account.net_change_pct.toFixed(1)}%` : undefined}
          valueColor={netColor}
        />
        <SummaryCard
          label="Max Drawdown"
          value={`-$${Math.abs(account.max_drawdown).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          sub={account.max_drawdown_pct != null ? `${account.max_drawdown_pct.toFixed(1)}% from peak` : undefined}
          valueColor={ddColor}
        />
      </div>

      {/* ── Balance chart ──────────────────────────────────────────────────── */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 14 }}>
          <h2>Account Balance History</h2>
          <div style={{ display: "flex", gap: 20, fontSize: 12, color: "#aaa" }}>
            <span>{account.total_trades.toLocaleString()} trades</span>
            <span>
              Win rate:{" "}
              <span style={{ fontWeight: 700, color: account.overall_win_rate >= beWr ? "#008265" : "#cc2626" }}>
                {(account.overall_win_rate * 100).toFixed(1)}%
              </span>
              {" "}(break-even: {(beWr * 100).toFixed(1)}%)
            </span>
          </div>
        </div>
        <BalanceChart daily={daily} openingBalance={account.opening_balance} />
      </div>

      {/* ── Rolling win-rate trend ─────────────────────────────────────────── */}
      {daily.length >= 3 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 14 }}>
            <h2>7-Day Rolling Win Rate</h2>
            <span style={{ fontSize: 12, color: "#aaa" }}>
              Break-even: {(beWr * 100).toFixed(1)}%
            </span>
          </div>
          <RollingWinRateChart daily={daily} beWr={beWr} />
        </div>
      )}

      {/* ── Daily activity ─────────────────────────────────────────────────── */}
      <div className="card" style={{ marginBottom: 20, padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "16px 20px 14px", borderBottom: "1px solid #e8eaeb" }}>
          <h2>Daily Activity</h2>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th style={{ textAlign: "right" }}>Trades</th>
                <th style={{ textAlign: "right" }}>Won</th>
                <th style={{ textAlign: "right" }}>Lost</th>
                <th style={{ textAlign: "right" }}>Win%</th>
                <th style={{ textAlign: "right" }}>Day P&amp;L</th>
                <th style={{ textAlign: "right" }}>Balance</th>
              </tr>
            </thead>
            <tbody>
              {daily.map((row) => <DayRow key={row.date} row={row} beWr={beWr} />)}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Per-bot performance ────────────────────────────────────────────── */}
      <div className="card" style={{ marginBottom: 20, padding: 0, overflow: "hidden" }}>
        <div style={{ padding: "16px 20px 12px", borderBottom: "1px solid #e8eaeb" }}>
          <h2 style={{ marginBottom: 2 }}>Bot Performance</h2>
          <p style={{ fontSize: 12, color: "#aaa", margin: 0 }}>
            Actual P&amp;L: +pnl for wins, −stake for losses. Break-even win rate: {(beWr * 100).toFixed(1)}%
          </p>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Bot</th>
                <th style={{ textAlign: "right" }}>Trades</th>
                <th style={{ textAlign: "right" }}>W / L</th>
                <th>Win Rate</th>
                <th style={{ textAlign: "right" }}>Avg Stake</th>
                <th style={{ textAlign: "right" }}>Real P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {bots.map((bot) => <BotRow key={bot.bot_id} bot={bot} beWr={beWr} />)}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Readiness assessment ───────────────────────────────────────────── */}
      <ReadinessCard account={account} bots={bots} beWr={beWr} />
    </>
  );
}

// ── Balance Chart (SVG polyline) ───────────────────────────────────────────────
function BalanceChart({ daily, openingBalance }: { daily: PortfolioDayRow[]; openingBalance: number }) {
  const points = daily.map((d) => d.running_balance);
  if (points.length < 2) return null;

  const W = 800, H = 160, PAD_X = 8, PAD_Y = 12;
  const minY = Math.min(...points, openingBalance);
  const maxY = Math.max(...points, openingBalance);
  const rangeY = maxY - minY || 1;
  const toX = (i: number) => PAD_X + (i / (points.length - 1)) * (W - PAD_X * 2);
  const toY = (v: number) => H - PAD_Y - ((v - minY) / rangeY) * (H - PAD_Y * 2);

  const lastVal = points[points.length - 1];
  const color = lastVal >= openingBalance ? "#008265" : "#cc2626";
  const baselineY = toY(openingBalance).toFixed(1);
  const polyline = points.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");
  const area = `${toX(0).toFixed(1)},${H - PAD_Y} ${polyline} ${toX(points.length - 1).toFixed(1)},${H - PAD_Y}`;

  // Date labels: first, middle, last
  const labelIdxs = [0, Math.floor((daily.length - 1) / 2), daily.length - 1];

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H, display: "block" }}>
        <defs>
          <linearGradient id="port-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.12" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Opening balance reference line */}
        <line x1={PAD_X} y1={baselineY} x2={W - PAD_X} y2={baselineY}
          stroke="#d0d5d9" strokeWidth={1} strokeDasharray="4 3" />
        <polygon points={area} fill="url(#port-grad)" />
        <polyline points={polyline} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
        <circle cx={toX(points.length - 1)} cy={toY(lastVal)} r={4} fill={color} />
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 11, color: "#bbb" }}>
        {labelIdxs.map((i) => (
          <span key={i}>{daily[i].date}</span>
        ))}
      </div>
    </div>
  );
}

// ── Rolling Win-Rate Chart ────────────────────────────────────────────────────
function RollingWinRateChart({ daily, beWr }: { daily: PortfolioDayRow[]; beWr: number }) {
  // Compute 7-day rolling win rate: for each day, sum won/total over the
  // preceding 7 days (inclusive). Skip days with no trades in the window.
  const rolling: { date: string; wr: number | null }[] = daily.map((_, i) => {
    const window = daily.slice(Math.max(0, i - 6), i + 1);
    const totalTrades = window.reduce((s, d) => s + d.trades, 0);
    if (totalTrades === 0) return { date: daily[i].date, wr: null };
    const totalWon = window.reduce((s, d) => s + d.won, 0);
    return { date: daily[i].date, wr: totalWon / totalTrades };
  });

  const withData = rolling.filter((r) => r.wr !== null);
  if (withData.length < 2) return null;

  const W = 800, H = 120, PAD_X = 8, PAD_Y = 12;
  const values = withData.map((r) => r.wr as number);
  const minY = Math.min(...values, beWr, 0.3);
  const maxY = Math.max(...values, beWr, 0.75);
  const rangeY = maxY - minY || 0.1;

  const toX = (i: number) => PAD_X + (i / (withData.length - 1)) * (W - PAD_X * 2);
  const toY = (v: number) => H - PAD_Y - ((v - minY) / rangeY) * (H - PAD_Y * 2);

  const beY = toY(beWr).toFixed(1);
  const polyline = withData.map((r, i) => `${toX(i).toFixed(1)},${toY(r.wr as number).toFixed(1)}`).join(" ");
  const lastWr = withData[withData.length - 1].wr as number;
  const lineColor = lastWr >= beWr ? "#008265" : "#cc2626";

  const labelIdxs = [0, Math.floor((withData.length - 1) / 2), withData.length - 1];

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H, display: "block" }}>
        {/* Break-even line */}
        <line x1={PAD_X} y1={beY} x2={W - PAD_X} y2={beY}
          stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="5 3" />
        <text x={W - PAD_X - 2} y={parseFloat(beY) - 4}
          textAnchor="end" fontSize={10} fill="#b37600">
          BE {(beWr * 100).toFixed(1)}%
        </text>
        <polyline points={polyline} fill="none" stroke={lineColor} strokeWidth={2} strokeLinejoin="round" />
        <circle cx={toX(withData.length - 1)} cy={toY(lastWr)} r={4} fill={lineColor} />
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 11, color: "#bbb" }}>
        {labelIdxs.map((i) => (
          <span key={i}>{withData[i].date}</span>
        ))}
      </div>
    </div>
  );
}

// ── Day row ────────────────────────────────────────────────────────────────────
function DayRow({ row, beWr }: { row: PortfolioDayRow; beWr: number }) {
  const hasActivity = row.trades > 0;
  const pnlColor = row.real_pnl > 0 ? "#008265" : row.real_pnl < 0 ? "#cc2626" : "#aaa";
  const wrColor = row.win_rate != null
    ? (row.win_rate >= beWr ? "#008265" : "#cc2626")
    : "#aaa";

  return (
    <tr>
      <td style={{ fontWeight: 600, color: "#0e0e0e", whiteSpace: "nowrap" }}>{row.date}</td>
      <td style={{ textAlign: "right", color: hasActivity ? "#0e0e0e" : "#ccc" }}>
        {hasActivity ? row.trades : "—"}
      </td>
      <td style={{ textAlign: "right", color: hasActivity ? "#008265" : "#ccc" }}>
        {hasActivity ? row.won : "—"}
      </td>
      <td style={{ textAlign: "right", color: hasActivity ? "#cc2626" : "#ccc" }}>
        {hasActivity ? row.lost : "—"}
      </td>
      <td style={{ textAlign: "right", color: wrColor, fontWeight: 600 }}>
        {row.win_rate != null ? `${(row.win_rate * 100).toFixed(1)}%` : "—"}
      </td>
      <td style={{ textAlign: "right", fontWeight: 700, color: pnlColor }}>
        {hasActivity
          ? `${row.real_pnl >= 0 ? "+" : ""}$${Math.abs(row.real_pnl).toFixed(2)}`
          : "—"}
      </td>
      <td style={{ textAlign: "right", fontWeight: 600 }}>
        ${row.running_balance.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </td>
    </tr>
  );
}

// ── Bot row with win-rate bar ──────────────────────────────────────────────────
function BotRow({ bot, beWr }: { bot: PortfolioBotRow; beWr: number }) {
  const profitable = bot.real_pnl > 0;
  const aboveBreakEven = bot.win_rate >= beWr;
  const pnlColor = profitable ? "#008265" : "#cc2626";
  const barColor = aboveBreakEven ? "#008265" : "#cc2626";
  const barPct = Math.min(bot.win_rate * 100, 100);
  const bePct = Math.min(beWr * 100, 100);

  return (
    <tr>
      <td>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
            background: aboveBreakEven ? "#008265" : "#cc2626",
          }} />
          <span style={{ fontWeight: 600 }}>{bot.name}</span>
        </div>
      </td>
      <td style={{ textAlign: "right" }}>{bot.trades}</td>
      <td style={{ textAlign: "right", fontSize: 12, color: "#555" }}>
        <span style={{ color: "#008265" }}>{bot.won}</span>
        {" / "}
        <span style={{ color: "#cc2626" }}>{bot.lost}</span>
      </td>
      <td style={{ minWidth: 180 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {/* Win-rate bar */}
          <div style={{ flex: 1, height: 6, background: "#f0f0f0", borderRadius: 3, position: "relative" }}>
            <div style={{
              position: "absolute", left: 0, top: 0, height: "100%",
              width: `${barPct}%`, background: barColor, borderRadius: 3,
              transition: "width 0.3s",
            }} />
            {/* Break-even marker */}
            <div style={{
              position: "absolute", top: -3, bottom: -3,
              left: `${bePct}%`, width: 2, background: "#888", borderRadius: 1,
            }} />
          </div>
          <span style={{ fontSize: 12, fontWeight: 700, color: barColor, whiteSpace: "nowrap", minWidth: 38 }}>
            {(bot.win_rate * 100).toFixed(1)}%
          </span>
        </div>
      </td>
      <td style={{ textAlign: "right", fontSize: 12, color: "#686868" }}>
        ${bot.avg_stake.toFixed(2)}
      </td>
      <td style={{ textAlign: "right", fontWeight: 700, color: pnlColor }}>
        {bot.real_pnl >= 0 ? "+" : ""}${Math.abs(bot.real_pnl).toFixed(2)}
      </td>
    </tr>
  );
}

// ── Readiness assessment ───────────────────────────────────────────────────────
function ReadinessCard({ account, bots, beWr }: {
  account: PortfolioAnalytics["account"];
  bots: PortfolioBotRow[];
  beWr: number;
}) {
  const activeBots = bots.filter((b) => !b.name.includes("Brindle Trend")); // tournament only
  const profitableBots = activeBots.filter((b) => b.win_rate >= beWr);
  const profitableCount = profitableBots.length;
  const totalActive = activeBots.length;
  const avgWr = activeBots.length
    ? activeBots.reduce((s, b) => s + b.win_rate, 0) / activeBots.length
    : 0;
  const ddPct = Math.abs(account.max_drawdown_pct ?? 0);

  const checks: { label: string; ok: boolean; note: string }[] = [
    {
      label: "Majority of bots above break-even",
      ok: profitableCount > totalActive / 2,
      note: `${profitableCount} of ${totalActive} bots ≥ ${(beWr * 100).toFixed(1)}% win rate`,
    },
    {
      label: "Portfolio win rate above break-even",
      ok: account.overall_win_rate >= beWr,
      note: `${(account.overall_win_rate * 100).toFixed(1)}% overall (need ≥ ${(beWr * 100).toFixed(1)}%)`,
    },
    {
      label: "Max drawdown below 15%",
      ok: ddPct < 15,
      note: `${ddPct.toFixed(1)}% max drawdown from peak`,
    },
    {
      label: "Net account positive",
      ok: account.net_change >= 0,
      note: account.net_change >= 0
        ? `+$${account.net_change.toFixed(2)} since opening`
        : `-$${Math.abs(account.net_change).toFixed(2)} since opening`,
    },
    {
      label: "Sufficient trade history (≥ 500 trades)",
      ok: account.total_trades >= 500,
      note: `${account.total_trades.toLocaleString()} trades recorded`,
    },
  ];

  const passCount = checks.filter((c) => c.ok).length;
  const ready = passCount >= 4;

  return (
    <div className="card" style={{ borderLeft: `3px solid ${ready ? "#008265" : "#b37600"}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2>Real-Money Readiness</h2>
        <span style={{
          fontSize: 12, fontWeight: 800, letterSpacing: "0.06em",
          textTransform: "uppercase" as const,
          padding: "4px 10px", borderRadius: 999,
          background: ready ? "#edfaf7" : "#fff8e6",
          color: ready ? "#008265" : "#b37600",
          border: `1px solid ${ready ? "#b2e8dc" : "#f5d88c"}`,
        }}>
          {passCount}/{checks.length} checks passing
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column" as const, gap: 10 }}>
        {checks.map((c) => (
          <div key={c.label} style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <div style={{
              width: 18, height: 18, borderRadius: "50%", flexShrink: 0, marginTop: 1,
              background: c.ok ? "#edfaf7" : "#fff0f0",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              {c.ok
                ? <svg width="10" height="10" fill="none" viewBox="0 0 10 10"><path d="M2 5l2 2 4-4" stroke="#008265" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
                : <svg width="10" height="10" fill="none" viewBox="0 0 10 10"><path d="M3 3l4 4M7 3L3 7" stroke="#cc2626" strokeWidth="1.5" strokeLinecap="round" /></svg>
              }
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#0e0e0e" }}>{c.label}</div>
              <div style={{ fontSize: 12, color: "#888", marginTop: 2 }}>{c.note}</div>
            </div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 16, padding: "12px 14px", background: "#f8fafc", borderRadius: 6, fontSize: 13, color: "#555", lineHeight: 1.6 }}>
        {ready
          ? "The portfolio is showing consistent signals. Consider a small real-money pilot with strict position sizing (1% risk per trade) and monitor for at least 2 more weeks before scaling."
          : "Continue paper trading. Focus on the failing checks above — particularly bots that consistently win above the break-even threshold. A 2-week streak of positive daily P&L with ≥ 52% win rate across the portfolio would be a strong readiness signal."}
      </div>
    </div>
  );
}

// ── Shared summary card ────────────────────────────────────────────────────────
function SummaryCard({ label, value, sub, valueColor }: {
  label: string;
  value: string;
  sub?: string;
  valueColor?: string;
}) {
  return (
    <div className="card">
      <div style={{ fontSize: 11, fontWeight: 700, color: "#aaa", textTransform: "uppercase" as const, letterSpacing: "0.07em", marginBottom: 10 }}>
        {label}
      </div>
      <div className="stat-number" style={{ fontSize: 22, color: valueColor ?? "#0e0e0e" }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "#aaa", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}
