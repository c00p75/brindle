"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Navigation from "@/components/Navigation";
import { api } from "@/lib/api";
import Link from "next/link";

export default function ObservationPage() {
  const [report, setReport] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hours, setHours] = useState(24);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const data = await api.getObservationReport(hours);
        setReport(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load report");
      } finally {
        setLoading(false);
      }
    })();
  }, [hours]);

  const downloadJson = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(report, null, 2));
    const downloadAnchorNode = document.createElement('a');
    downloadAnchorNode.setAttribute("href", dataStr);
    downloadAnchorNode.setAttribute("download", `observation_${new Date().toISOString().split('T')[0]}.json`);
    document.body.appendChild(downloadAnchorNode);
    downloadAnchorNode.click();
    downloadAnchorNode.remove();
  };

  return (
    <AuthGuard>
      <Navigation />
      <div className="container">
        <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h1>Portfolio Observation</h1>
          <div style={{ display: "flex", gap: 10 }}>
            <select value={hours} onChange={(e) => setHours(Number(e.target.value))}>
              <option value={1}>Last Hour</option>
              <option value={4}>Last 4 Hours</option>
              <option value={24}>Last 24 Hours</option>
              <option value={168}>Last 7 Days</option>
            </select>
            <button onClick={downloadJson}>Export JSON</button>
          </div>
        </header>

        {loading ? (
          <p>Loading portfolio data...</p>
        ) : error ? (
          <div className="card" style={{ borderColor: "var(--red)" }}>{error}</div>
        ) : (
          <div className="card" style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border)" }}>
                  <th style={{ padding: "12px 8px" }}>Bot</th>
                  <th style={{ padding: "12px 8px" }}>Strategy</th>
                  <th style={{ padding: "12px 8px" }}>Trades</th>
                  <th style={{ padding: "12px 8px" }}>Win Rate</th>
                  <th style={{ padding: "12px 8px" }}>PnL</th>
                  <th style={{ padding: "12px 8px" }}>Rejects</th>
                  <th style={{ padding: "12px 8px" }}>Pauses</th>
                  <th style={{ padding: "12px 8px" }}>Ticks</th>
                  <th style={{ padding: "12px 8px" }}>Signals (24h)</th>
                </tr>
              </thead>
              <tbody>
                {report.map((bot) => {
                  const noTrades = bot.trades === 0 && bot.tick_count > 1000;
                  const highRejects = bot.rejection_count > 10;
                  const lowWinRate = bot.win_rate < 0.4 && bot.trades >= 10;
                  
                  const rowStyle = (noTrades || highRejects || lowWinRate) 
                    ? { backgroundColor: "rgba(255, 0, 0, 0.05)" } 
                    : {};

                  return (
                    <tr key={bot.bot_id} style={{ borderBottom: "1px solid var(--border)", ...rowStyle }}>
                      <td style={{ padding: "12px 8px" }}>
                        <Link href={`/bots/${bot.bot_id}`}>{bot.name}</Link>
                        <div style={{ fontSize: 10, opacity: 0.6 }}>{bot.symbols.join(", ")}</div>
                      </td>
                      <td style={{ padding: "12px 8px" }}>{bot.strategy_id}</td>
                      <td style={{ padding: "12px 8px" }}>{bot.trades}</td>
                      <td style={{ padding: "12px 8px" }}>{(bot.win_rate * 100).toFixed(1)}%</td>
                      <td style={{ padding: "12px 8px", color: bot.realized_pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                        ${bot.realized_pnl.toFixed(2)}
                      </td>
                      <td style={{ padding: "12px 8px", color: bot.rejection_count > 0 ? "var(--red)" : "inherit" }}>
                        {bot.rejection_count}
                      </td>
                      <td style={{ padding: "12px 8px", color: bot.auto_pauses > 0 ? "var(--red)" : "inherit" }}>
                        {bot.auto_pauses}
                      </td>
                      <td style={{ padding: "12px 8px" }}>{bot.tick_count.toLocaleString()}</td>
                      <td style={{ padding: "12px 8px" }}>
                        <div style={{ display: "flex", gap: 2, height: 20, alignItems: "flex-end" }}>
                          {Object.entries(bot.signal_status_histogram).map(([status, count]: [string, any]) => (
                            <div 
                              key={status} 
                              title={`${status}: ${count}`}
                              style={{ 
                                width: 12, 
                                height: `${Math.min(100, (count / (bot.tick_count / 60)) * 100)}%`,
                                backgroundColor: status === "intent" ? "var(--green)" : status === "watching" ? "var(--blue)" : "var(--gray)",
                                borderRadius: "2px 2px 0 0"
                              }} 
                            />
                          ))}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AuthGuard>
  );
}
