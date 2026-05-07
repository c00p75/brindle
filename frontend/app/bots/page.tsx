"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Navigation from "@/components/Navigation";
import { api, getUser } from "@/lib/api";
import { can } from "@/lib/rbac";
import { events, GLOBAL_EVENTS } from "@/lib/events";
import type { Bot, ContractsSummary } from "@/lib/types";

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
  const [summaries, setSummaries] = useState<Record<string, ContractsSummary>>({});
  const [err, setErr] = useState<string | null>(null);
  const user = getUser();

  async function refresh() {
    try {
      const list = await api.listBots();
      setBots(list);
      // Fan out — fetch each bot's contract summary in parallel. Best-effort: a
      // failed call shouldn't block the rest, just leave that bot's row blank.
      const entries = await Promise.all(list.map(async (b) => {
        try { return [b.id, await api.contractsSummary(b.id)] as const; }
        catch { return [b.id, null] as const; }
      }));
      const next: Record<string, ContractsSummary> = {};
      for (const [id, s] of entries) if (s) next[id] = s;
      setSummaries(next);
    }
    catch (e) { setErr(e instanceof Error ? e.message : "failed"); }
  }
  useEffect(() => {
    refresh();
    const stopListening = events.on(GLOBAL_EVENTS.STATE_CHANGED, () => {
      refresh();
    });
    const t = setInterval(refresh, 15000);
    return () => {
      stopListening();
      clearInterval(t);
    };
  }, []);

  const totals = Object.values(summaries).reduce(
    (acc, s) => ({
      pnl: acc.pnl + s.realized_pnl,
      open: acc.open + s.open_count,
      won: acc.won + s.won_count,
      lost: acc.lost + s.lost_count,
    }),
    { pnl: 0, open: 0, won: 0, lost: 0 },
  );
  const totalSettled = totals.won + totals.lost;
  const overallWinRate = totalSettled > 0 ? totals.won / totalSettled : 0;

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
        <div style={{ display: "flex", gap: 8 }}>
          {can(user?.role, "bot:stop") && running > 0 && (
            <button
              type="button"
              className="btn danger"
              onClick={async () => {
                if (!confirm(`Emergency stop all ${running} running bots?`)) return;
                try {
                  const r = await api.stopAllBots();
                  alert(`Stopped ${r.count} bot${r.count === 1 ? "" : "s"}.` +
                        (r.failed.length ? `\n${r.failed.length} failed.` : ""));
                  await refresh();
                } catch (e) { alert(e instanceof Error ? e.message : "failed"); }
              }}
              style={{ textDecoration: "none" }}
            >
              ⛔ Stop all ({running})
            </button>
          )}
          {can(user?.role, "config:draft") && (
            <button
              type="button"
              className="btn ghost"
              onClick={async () => {
                const description = prompt(
                  "Describe a strategy in plain English. Example:\n\n" +
                  '"Buy when EUR/USD\'s 5-period SMA crosses above the 20-period SMA, ' +
                  'sell on the reverse. Cooldown 10 ticks."',
                );
                if (!description) return;
                try {
                  const r = await api.generateStrategy(description);
                  if (r.ok) {
                    alert(`✓ Generated strategy "${r.strategy_id}"\n\n` +
                          `Saved to: ${r.file_path}\n\n` +
                          `${r.note}\n\nRestart the backend to load it into the registry.`);
                  } else {
                    alert(`Generation failed:\n\n${(r.errors || []).join("\n")}`);
                  }
                } catch (e) { alert(e instanceof Error ? e.message : "failed"); }
              }}
              style={{ textDecoration: "none" }}
              title="Generate a custom strategy from a natural-language description (Groq)"
            >
              ✨ Generate strategy
            </button>
          )}
          {can(user?.role, "bot:create") && (
            <Link href="/bots/new" className="btn" style={{ textDecoration: "none" }}>+ New bot</Link>
          )}
        </div>
      </div>

      {err && <p className="error" style={{ marginBottom: 16 }}>{err}</p>}

      {bots.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
          <DashStat label="Total realized P&L" value={`$${totals.pnl >= 0 ? "+" : ""}${totals.pnl.toFixed(2)}`}
                    valueColor={totals.pnl >= 0 ? "#008265" : "#cc2626"} />
          <DashStat label="Open contracts" value={String(totals.open)} />
          <DashStat label="Win / loss" value={`${totals.won} / ${totals.lost}`} />
          <DashStat label="Win rate" value={totalSettled > 0 ? `${(overallWinRate * 100).toFixed(1)}%` : "—"} />
        </div>
      )}

      {bots.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "64px 24px" }}>
          <div style={{ width: 56, height: 56, borderRadius: 8, background: "#f5f7ff", border: "1px solid #c7d2fe", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 20px" }}>
            <svg width="28" height="28" fill="none" viewBox="0 0 28 28">
              <rect x="5" y="10" width="18" height="14" rx="3" stroke="#4f46e5" strokeWidth="1.5"/>
              <path d="M10 10V8a4 4 0 018 0v2" stroke="#4f46e5" strokeWidth="1.5"/>
              <circle cx="10.5" cy="17" r="1.5" fill="#4f46e5"/>
              <circle cx="17.5" cy="17" r="1.5" fill="#4f46e5"/>
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
                <th>P&L</th>
                <th>Win/loss</th>
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
                  <td style={{ fontVariantNumeric: "tabular-nums" }}>
                    {summaries[b.id]
                      ? <span style={{ color: summaries[b.id].realized_pnl >= 0 ? "#008265" : "#cc2626", fontWeight: 600 }}>
                          ${summaries[b.id].realized_pnl >= 0 ? "+" : ""}{summaries[b.id].realized_pnl.toFixed(2)}
                        </span>
                      : <span style={{ color: "#d6dadc" }}>—</span>}
                  </td>
                  <td style={{ fontSize: 12, color: "#555", fontVariantNumeric: "tabular-nums" }}>
                    {summaries[b.id]
                      ? `${summaries[b.id].won_count} / ${summaries[b.id].lost_count}` + (summaries[b.id].open_count > 0 ? ` (${summaries[b.id].open_count} open)` : "")
                      : <span style={{ color: "#d6dadc" }}>—</span>}
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

function DashStat({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div className="card" style={{ padding: "14px 16px" }}>
      <div style={{ fontSize: 11, color: "#686868", textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: valueColor ?? "#0e0e0e", fontVariantNumeric: "tabular-nums" }}>
        {value}
      </div>
    </div>
  );
}
