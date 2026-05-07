"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Navigation from "@/components/Navigation";
import { api } from "@/lib/api";
import type { Alert, Bot } from "@/lib/types";

export default function DashboardPage() {
  return (
    <AuthGuard>
      <Navigation />
      <div className="container">
        <Dashboard />
      </div>
    </AuthGuard>
  );
}

function Dashboard() {
  const [bots, setBots] = useState<Bot[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [balance, setBalance] = useState<{ available: number; currency: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [b, a] = await Promise.all([api.listBots(), api.listAlerts()]);
        setBots(b);
        setAlerts(a);
        
        // Use the first bot with a config to fetch the master broker balance
        const refBot = b.find(bot => bot.active_config_version != null);
        if (refBot) {
          const bal = await api.brokerBalance(refBot.id);
          if (bal.available != null) {
            setBalance({ available: bal.available, currency: bal.currency || "USD" });
          }
        }
      } catch (e) {
        setErr(e instanceof Error ? e.message : "failed to load");
      }
    })();
  }, []);

  const running      = bots.filter((b) => b.state === "running");
  const halted       = bots.filter((b) => b.state === "halted" || b.state === "error");
  const activeAlerts = alerts.filter((a) => a.status === "active");
  const critAlerts   = activeAlerts.filter((a) => a.severity === "critical");

  const masterBalStr = balance 
    ? `${balance.currency === "USD" ? "$" : ""}${balance.available.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : "—";

  return (
    <>
      {/* Page header */}
      <div className="section-header">
        <div>
          <h1 style={{ marginBottom: 2 }}>Overview</h1>
          <p style={{ fontSize: 13, color: "#aaaaaa" }}>
            Paper-trading platform · all live execution disabled
          </p>
        </div>
        <Link href="/bots/new" className="btn" style={{ textDecoration: "none" }}>
          + New bot
        </Link>
      </div>

      {err && <p className="error" style={{ marginBottom: 20 }}>{err}</p>}

      {/* Stats row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 24 }}>
        <div className="card" style={{ borderLeft: "4px solid #4f46e5" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#aaaaaa", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 10 }}>
            Master Balance
          </div>
          <div className="stat-number" style={{ color: "#4f46e5", fontSize: 24 }}>{masterBalStr}</div>
          <div style={{ fontSize: 10, color: "#aaaaaa", marginTop: 4 }}>connected broker account</div>
        </div>
        <StatCard label="Total bots" value={bots.length} />
        <StatCard label="Running" value={running.length} color={running.length > 0 ? "#008265" : undefined} />
        <StatCard label="Halted / Error" value={halted.length} color={halted.length > 0 ? "#cc2626" : undefined} />
        <StatCard
          label="Active alerts"
          value={activeAlerts.length}
          color={critAlerts.length > 0 ? "#cc2626" : activeAlerts.length > 0 ? "#b37600" : undefined}
          sub={critAlerts.length > 0 ? `${critAlerts.length} critical` : undefined}
        />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
        {/* Bots table */}
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px 14px", borderBottom: "1px solid #e8eaeb" }}>
            <h2>Bots</h2>
            <Link href="/bots" style={{ fontSize: 13, color: "#4f46e5", fontWeight: 700 }}>View all</Link>
          </div>
          {bots.length === 0 ? (
            <div style={{ padding: "48px 24px", textAlign: "center" }}>
              <p style={{ color: "#aaaaaa", marginBottom: 16 }}>No bots configured yet.</p>
              <Link href="/bots/new" className="btn" style={{ textDecoration: "none" }}>+ New bot</Link>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Config</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {bots.slice(0, 6).map((b) => (
                  <tr key={b.id}>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{
                          width: 7, height: 7, borderRadius: "50%", flexShrink: 0,
                          background: b.state === "running" ? "#008265" : b.state === "error" || b.state === "halted" ? "#cc2626" : "#d6dadc",
                          boxShadow: b.state === "running" ? "0 0 0 3px rgba(0,130,101,0.15)" : "none",
                          display: "inline-block",
                        }} />
                        <Link href={`/bots/${b.id}`} style={{ fontWeight: 700, color: "#0e0e0e" }}>
                          {b.name}
                        </Link>
                      </div>
                    </td>
                    <td><span className={`pill ${b.state}`}>{b.state}</span></td>
                    <td>
                      {b.active_config_version
                        ? <span style={{ fontSize: 13, color: "#686868" }}>v{b.active_config_version}</span>
                        : <span style={{ color: "#d6dadc" }}>—</span>}
                    </td>
                    <td style={{ color: "#aaaaaa", fontSize: 12 }}>
                      {new Date(b.updated_at_ms).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Right column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Safety */}
          <div className="card">
            <h2 style={{ marginBottom: 14 }}>Safety</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <SafetyRow label="Paper trading" ok note="enforced at boot" />
              <SafetyRow label="Live execution" ok={false} note="disabled" />
              <SafetyRow label="Risk gates" ok note="pre-order, every trade" />
              <SafetyRow label="Audit trail" ok note="append-only" />
              <SafetyRow label="Config workflow" ok note="draft → validate → apply" />
            </div>
          </div>

          {/* Alerts */}
          {activeAlerts.length > 0 ? (
            <div className="card" style={{ borderLeft: "3px solid #4f46e5" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <h2 style={{ color: "#cc2626" }}>
                  {activeAlerts.length} active alert{activeAlerts.length !== 1 ? "s" : ""}
                </h2>
                <Link href="/alerts" style={{ fontSize: 12, color: "#4f46e5", fontWeight: 700 }}>View all</Link>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {activeAlerts.slice(0, 3).map((a) => (
                  <div key={a.id} style={{ display: "flex", gap: 10, fontSize: 13 }}>
                    <span className={`pill ${a.severity}`}>{a.severity}</span>
                    <span style={{ color: "#555555", lineHeight: 1.4, flex: 1 }}>{a.message}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="card" style={{ borderLeft: "3px solid #4bb4b3" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ width: 36, height: 36, borderRadius: "50%", background: "#edfaf7", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <svg width="18" height="18" fill="none" viewBox="0 0 18 18">
                    <path d="M3.5 9.5l3.5 3.5 7-8" stroke="#008265" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>
                <div>
                  <div style={{ fontWeight: 700, color: "#008265", fontSize: 14 }}>All systems normal</div>
                  <div style={{ fontSize: 12, color: "#aaaaaa" }}>No active alerts</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function StatCard({ label, value, color, sub }: {
  label: string;
  value: number;
  color?: string;
  sub?: string;
}) {
  return (
    <div className="card">
      <div style={{ fontSize: 11, fontWeight: 700, color: "#aaaaaa", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 10 }}>
        {label}
      </div>
      <div className="stat-number" style={{ color: color ?? "#0e0e0e" }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: color ?? "#aaaaaa", marginTop: 4, fontWeight: 700 }}>{sub}</div>}
    </div>
  );
}

function SafetyRow({ label, ok, note }: { label: string; ok: boolean; note: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
      <span style={{ fontSize: 13, color: "#555555" }}>{label}</span>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <div style={{
          width: 16, height: 16, borderRadius: "50%",
          background: ok ? "#edfaf7" : "#fff0f0",
          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
        }}>
          {ok
            ? <svg width="10" height="10" fill="none" viewBox="0 0 10 10"><path d="M2 5l2 2 4-4" stroke="#008265" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            : <svg width="10" height="10" fill="none" viewBox="0 0 10 10"><path d="M3 3l4 4M7 3L3 7" stroke="#cc2626" strokeWidth="1.5" strokeLinecap="round"/></svg>
          }
        </div>
        <span style={{ fontSize: 12, color: ok ? "#008265" : "#cc2626", fontWeight: 600 }}>{note}</span>
      </div>
    </div>
  );
}
