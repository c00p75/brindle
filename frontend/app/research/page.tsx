"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Navigation from "@/components/Navigation";
import { api } from "@/lib/api";
import type { BacktestMetrics } from "@/lib/types";

const PAPER_SYMBOLS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "USD/CHF", "NZD/USD", "EUR/GBP"];
const DUMMY_BOT_ID = "bot-backtest-placeholder";

export default function ResearchPage() {
  return (
    <AuthGuard>
      <Navigation />
      <div className="container">
        <Research />
      </div>
    </AuthGuard>
  );
}

const TREND_V1_DEFAULTS = { fast: 5, slow: 20, qty: 1000, min_cross_pct: 0.02, cooldown_ticks: 10 };

function Research() {
  const [strategies, setStrategies] = useState<string[]>([]);
  const [strategyId, setStrategyId] = useState("trend_v1");
  const [paramsText, setParamsText] = useState(JSON.stringify(TREND_V1_DEFAULTS, null, 2));
  const [probeBotId, setProbeBotId] = useState<string | null>(null);
  const [symbols, setSymbols] = useState<string[]>(["EUR/USD"]);
  const [bars, setBars] = useState(500);
  const [seed, setSeed] = useState("backtest-1");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<BacktestMetrics | null>(null);
  const [history, setHistory] = useState<BacktestMetrics[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [bots, runs] = await Promise.all([
          api.listBots(),
          api.listBacktests(),
        ]);
        setHistory(runs);
        if (bots.length > 0) {
          setProbeBotId(bots[0].id);
          const strats = await api.listStrategies(bots[0].id);
          setStrategies(strats);
          if (strats.length > 0) setStrategyId(strats[0]);
        }
      } catch {
        // best effort — strategy list falls back to free text
      }
    })();
  }, []);

  // Refresh defaults whenever the selected strategy changes, so users start
  // from a known-good params shape instead of stale keys.
  useEffect(() => {
    if (!probeBotId) return;
    let cancelled = false;
    (async () => {
      try {
        const schema = await api.strategyParamSchema(probeBotId, strategyId);
        if (!cancelled) setParamsText(JSON.stringify(schema, null, 2));
      } catch { /* keep current text */ }
    })();
    return () => { cancelled = true; };
  }, [probeBotId, strategyId]);

  function toggleSymbol(sym: string) {
    if (symbols.includes(sym)) setSymbols(symbols.filter((s) => s !== sym));
    else setSymbols([...symbols, sym]);
  }

  async function run() {
    setErr(null);
    setResult(null);
    let params: Record<string, unknown> = {};
    try { params = JSON.parse(paramsText); } catch { setErr("Invalid JSON in parameters"); return; }
    if (symbols.length === 0) { setErr("Select at least one symbol"); return; }
    setRunning(true);
    try {
      const m = await api.runBacktest({ strategy_id: strategyId, params, symbols, bars, seed, risk: {}, save: true });
      setResult(m);
      setHistory((h) => [m, ...h.filter((x) => x.run_id !== m.run_id)]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "backtest failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <>
      <h1>Research — Backtest Runner</h1>
      <p style={{ color: "#64748b", fontSize: 14 }}>
        Run deterministic paper-trading simulations. Results are saved to <code>experiments/</code>.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <section className="card">
          <h2 style={{ marginTop: 0 }}>Strategy</h2>
          <label>Strategy</label>
          {strategies.length > 0 ? (
            <select value={strategyId} onChange={(e) => setStrategyId(e.target.value)} style={{ width: "100%" }}>
              {strategies.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          ) : (
            <input value={strategyId} onChange={(e) => setStrategyId(e.target.value)} style={{ width: "100%" }} />
          )}
          <label style={{ marginTop: 12 }}>Parameters (JSON)</label>
          <textarea
            value={paramsText}
            onChange={(e) => setParamsText(e.target.value)}
            rows={5}
            style={{ width: "100%", fontFamily: "ui-monospace, Menlo, monospace" }}
          />
        </section>

        <section className="card">
          <h2 style={{ marginTop: 0 }}>Simulation settings</h2>
          <label>Symbols</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
            {PAPER_SYMBOLS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => toggleSymbol(s)}
                style={{
                  padding: "3px 10px", borderRadius: 12, fontSize: 12, cursor: "pointer",
                  border: symbols.includes(s) ? "2px solid #3b82f6" : "1px solid #cbd5e1",
                  background: symbols.includes(s) ? "#eff6ff" : "#fff",
                  color: symbols.includes(s) ? "#1d4ed8" : "#334155",
                  fontWeight: symbols.includes(s) ? 600 : 400,
                }}
              >
                {s}
              </button>
            ))}
          </div>
          <label>Bars</label>
          <input type="number" min={50} max={5000} value={bars}
            onChange={(e) => setBars(Number(e.target.value))} style={{ width: "100%" }} />
          <label style={{ marginTop: 12 }}>Seed (for reproducibility)</label>
          <input value={seed} onChange={(e) => setSeed(e.target.value)} style={{ width: "100%" }}
            placeholder="any string" />
        </section>
      </div>

      <div style={{ marginTop: 16, display: "flex", gap: 8, alignItems: "center" }}>
        <button className="btn" onClick={run} disabled={running}>
          {running ? "Running…" : "Run backtest"}
        </button>
      </div>

      {err && <p className="error" style={{ marginTop: 12 }}>{err}</p>}

      {result && (
        <div className="card" style={{ marginTop: 20 }}>
          <h2 style={{ marginTop: 0 }}>
            Results — <code style={{ fontWeight: 400, fontSize: 14 }}>{result.run_id}</code>
          </h2>
          <MetricsGrid m={result} />
        </div>
      )}

      {history.length > 0 && (
        <div className="card" style={{ marginTop: 20 }}>
          <h2 style={{ marginTop: 0 }}>Past runs</h2>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", background: "#f8fafc" }}>
                <th style={th}>Run ID</th>
                <th style={th}>Strategy</th>
                <th style={th}>Symbols</th>
                <th style={{ ...th, textAlign: "right" }}>Bars</th>
                <th style={{ ...th, textAlign: "right" }}>PnL</th>
                <th style={{ ...th, textAlign: "right" }}>Win rate</th>
                <th style={{ ...th, textAlign: "right" }}>Sharpe</th>
                <th style={{ ...th, textAlign: "right" }}>Max DD%</th>
                <th style={th}>Completed</th>
              </tr>
            </thead>
            <tbody>
              {history.map((m) => (
                <tr key={m.run_id} style={{ borderTop: "1px solid #e2e8f0" }}>
                  <td style={{ ...td, fontFamily: "ui-monospace, Menlo, monospace", fontSize: 12 }}>{m.run_id}</td>
                  <td style={td}>{m.strategy_id}</td>
                  <td style={{ ...td, fontSize: 12 }}>{m.symbols.join(", ")}</td>
                  <td style={{ ...td, textAlign: "right" }}>{m.bars_simulated.toLocaleString()}</td>
                  <td style={{ ...td, textAlign: "right", color: m.total_realized_pnl >= 0 ? "#15803d" : "#b91c1c", fontWeight: 600 }}>
                    {m.total_realized_pnl >= 0 ? "+" : ""}{m.total_realized_pnl.toFixed(2)}
                  </td>
                  <td style={{ ...td, textAlign: "right" }}>{(m.win_rate * 100).toFixed(1)}%</td>
                  <td style={{ ...td, textAlign: "right" }}>{m.sharpe_ratio.toFixed(2)}</td>
                  <td style={{ ...td, textAlign: "right", color: m.max_drawdown_pct > 20 ? "#b91c1c" : undefined }}>
                    {m.max_drawdown_pct.toFixed(1)}%
                  </td>
                  <td style={{ ...td, fontSize: 12 }}>{new Date(m.completed_at_ms).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function MetricsGrid({ m }: { m: BacktestMetrics }) {
  const items = [
    { label: "Total orders", value: m.total_orders.toLocaleString() },
    { label: "Filled", value: m.filled_orders.toLocaleString() },
    { label: "Rejected", value: m.rejected_orders.toLocaleString() },
    { label: "Realized PnL", value: `${m.total_realized_pnl >= 0 ? "+" : ""}${m.total_realized_pnl.toFixed(2)}`, color: m.total_realized_pnl >= 0 ? "#15803d" : "#b91c1c" },
    { label: "Win trades", value: m.win_trades.toString() },
    { label: "Loss trades", value: m.loss_trades.toString() },
    { label: "Win rate", value: `${(m.win_rate * 100).toFixed(1)}%` },
    { label: "Sharpe ratio", value: m.sharpe_ratio.toFixed(3) },
    { label: "Max drawdown", value: `${m.max_drawdown_pct.toFixed(2)}%`, color: m.max_drawdown_pct > 20 ? "#b91c1c" : undefined },
  ];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
      {items.map(({ label, value, color }) => (
        <div key={label} style={{ padding: 12, background: "#f8fafc", borderRadius: 8 }}>
          <div style={{ fontSize: 12, color: "#64748b" }}>{label}</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: color ?? "#0f172a" }}>{value}</div>
        </div>
      ))}
    </div>
  );
}

const th: React.CSSProperties = { padding: "10px 12px", fontWeight: 600, fontSize: 13 };
const td: React.CSSProperties = { padding: "10px 12px", fontSize: 14 };
