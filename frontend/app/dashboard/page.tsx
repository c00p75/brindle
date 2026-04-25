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
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [b, a] = await Promise.all([api.listBots(), api.listAlerts()]);
        setBots(b);
        setAlerts(a);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "failed to load");
      }
    })();
  }, []);

  const running = bots.filter((b) => b.state === "running");
  const halted  = bots.filter((b) => b.state === "halted" || b.state === "error");
  const paused  = bots.filter((b) => b.state === "paused");
  const activeAlerts = alerts.filter((a) => a.status === "active");
  const critAlerts   = activeAlerts.filter((a) => a.severity === "critical");

  return (
    <>
      <div className="section-header">
        <div>
          <h1 style={{ marginBottom: 4 }}>Dashboard</h1>
          <p style={{ fontSize: 14, color: "#64748b", margin: 0 }}>
            Paper-trading platform overview · all live trading disabled
          </p>
        </div>
        <Link href="/bots" className="btn" style={{ textDecoration: "none" }}>
          View all bots
        </Link>
      </div>

      {err && <p className="error" style={{ marginBottom: 20 }}>{err}</p>}

      {/* Metric tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 24 }}>
        <MetricCard
          label="Total bots"
          value={bots.length}
          icon={BotIcon}
          iconBg="#f0fdfa"
          iconColor="#0d9488"
        />
        <MetricCard
          label="Running"
          value={running.length}
          icon={PlayIcon}
          iconBg="#f0fdf4"
          iconColor="#15803d"
          valueColor={running.length > 0 ? "#15803d" : undefined}
        />
        <MetricCard
          label="Halted / Error"
          value={halted.length}
          icon={StopIcon}
          iconBg={halted.length > 0 ? "#fff1f2" : "#f8fafc"}
          iconColor={halted.length > 0 ? "#be123c" : "#94a3b8"}
          valueColor={halted.length > 0 ? "#be123c" : undefined}
        />
        <MetricCard
          label="Active alerts"
          value={activeAlerts.length}
          icon={BellIcon}
          iconBg={activeAlerts.length > 0 ? "#fffbeb" : "#f8fafc"}
          iconColor={activeAlerts.length > 0 ? "#b45309" : "#94a3b8"}
          valueColor={critAlerts.length > 0 ? "#be123c" : activeAlerts.length > 0 ? "#b45309" : undefined}
          sub={critAlerts.length > 0 ? `${critAlerts.length} critical` : undefined}
          subColor="#be123c"
        />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Bots quick view */}
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <h2>Bots</h2>
            <Link href="/bots" style={{ fontSize: 13, color: "#0d9488", fontWeight: 500 }}>
              Manage →
            </Link>
          </div>
          {bots.length === 0 ? (
            <div style={{ padding: "32px 0", textAlign: "center" }}>
              <p style={{ color: "#94a3b8", fontSize: 14, marginBottom: 12 }}>No bots yet</p>
              <Link href="/bots/new" className="btn" style={{ textDecoration: "none" }}>
                + New bot
              </Link>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {bots.slice(0, 5).map((b) => (
                <Link
                  key={b.id}
                  href={`/bots/${b.id}`}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "10px 12px", borderRadius: 10, background: "#f8fafc",
                    textDecoration: "none", transition: "background 0.15s",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{
                      width: 8, height: 8, borderRadius: "50%",
                      background: b.state === "running" ? "#0d9488" : b.state === "error" || b.state === "halted" ? "#be123c" : "#94a3b8",
                      boxShadow: b.state === "running" ? "0 0 0 3px rgba(13,148,136,0.2)" : "none",
                    }} />
                    <span style={{ fontSize: 14, fontWeight: 500, color: "#0f172a" }}>{b.name}</span>
                  </div>
                  <span className={`pill ${b.state}`}>{b.state}</span>
                </Link>
              ))}
              {bots.length > 5 && (
                <p style={{ fontSize: 13, color: "#64748b", textAlign: "center", paddingTop: 4 }}>
                  +{bots.length - 5} more
                </p>
              )}
            </div>
          )}
        </div>

        {/* Safety posture + alerts */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card">
            <h2 style={{ marginBottom: 14 }}>Safety posture</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <SafetyRow label="Paper trading" status="enforced" ok />
              <SafetyRow label="Live trading" status="disabled" ok />
              <SafetyRow label="Kill-switch available" status="per-bot config" ok />
              <SafetyRow label="Config workflow" status="draft → validate → apply → audit" ok />
            </div>
          </div>

          {activeAlerts.length > 0 && (
            <div className="card" style={{ borderLeft: "4px solid #f59e0b" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <h2 style={{ color: "#92400e" }}>Active alerts</h2>
                <Link href="/alerts" style={{ fontSize: 13, color: "#0d9488", fontWeight: 500 }}>
                  View all →
                </Link>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {activeAlerts.slice(0, 3).map((a) => (
                  <div key={a.id} style={{ display: "flex", alignItems: "flex-start", gap: 10, fontSize: 13 }}>
                    <span className={`pill ${a.severity}`}>{a.severity}</span>
                    <span style={{ color: "#475569", lineHeight: 1.4 }}>{a.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeAlerts.length === 0 && (
            <div className="card" style={{ borderLeft: "4px solid #0d9488" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 32, height: 32, borderRadius: "50%", background: "#f0fdfa", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <svg width="16" height="16" fill="none" viewBox="0 0 16 16"><path d="M3 8l3 3 7-7" stroke="#0d9488" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </div>
                <div>
                  <p style={{ fontSize: 14, fontWeight: 600, color: "#0f766e" }}>All clear</p>
                  <p style={{ fontSize: 13, color: "#64748b" }}>No active alerts</p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function MetricCard({
  label, value, icon: Icon, iconBg, iconColor, valueColor, sub, subColor,
}: {
  label: string;
  value: number;
  icon: React.FC<{ color: string }>;
  iconBg: string;
  iconColor: string;
  valueColor?: string;
  sub?: string;
  subColor?: string;
}) {
  return (
    <div className="card">
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 12 }}>
        <span style={{ fontSize: 13, fontWeight: 500, color: "#64748b" }}>{label}</span>
        <div style={{ width: 34, height: 34, borderRadius: 10, background: iconBg, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon color={iconColor} />
        </div>
      </div>
      <div style={{ fontSize: 34, fontWeight: 700, color: valueColor ?? "#0f172a", lineHeight: 1, letterSpacing: "-0.02em" }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 12, color: subColor ?? "#64748b", marginTop: 4, fontWeight: 500 }}>{sub}</div>}
    </div>
  );
}

function SafetyRow({ label, status, ok }: { label: string; status: string; ok: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 14 }}>
      <span style={{ color: "#475569" }}>{label}</span>
      <span style={{ display: "flex", alignItems: "center", gap: 5, fontWeight: 500, color: ok ? "#0f766e" : "#be123c" }}>
        <svg width="12" height="12" fill="none" viewBox="0 0 12 12">
          <circle cx="6" cy="6" r="5" fill={ok ? "#ccfbf1" : "#fee2e2"}/>
          {ok
            ? <path d="M3.5 6l1.8 1.8L8.5 4.2" stroke="#0f766e" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            : <path d="M4 4l4 4M8 4l-4 4" stroke="#be123c" strokeWidth="1.5" strokeLinecap="round"/>
          }
        </svg>
        {status}
      </span>
    </div>
  );
}

function BotIcon({ color }: { color: string }) {
  return (
    <svg width="16" height="16" fill="none" viewBox="0 0 16 16">
      <rect x="3" y="6" width="10" height="8" rx="2" stroke={color} strokeWidth="1.5"/>
      <path d="M6 6V4a2 2 0 114 0v2" stroke={color} strokeWidth="1.5"/>
      <circle cx="6" cy="10" r="1" fill={color}/>
      <circle cx="10" cy="10" r="1" fill={color}/>
    </svg>
  );
}

function PlayIcon({ color }: { color: string }) {
  return (
    <svg width="16" height="16" fill="none" viewBox="0 0 16 16">
      <circle cx="8" cy="8" r="6" stroke={color} strokeWidth="1.5"/>
      <path d="M6.5 5.5l4 2.5-4 2.5V5.5z" fill={color}/>
    </svg>
  );
}

function StopIcon({ color }: { color: string }) {
  return (
    <svg width="16" height="16" fill="none" viewBox="0 0 16 16">
      <circle cx="8" cy="8" r="6" stroke={color} strokeWidth="1.5"/>
      <rect x="5.5" y="5.5" width="5" height="5" rx="1" fill={color}/>
    </svg>
  );
}

function BellIcon({ color }: { color: string }) {
  return (
    <svg width="16" height="16" fill="none" viewBox="0 0 16 16">
      <path d="M8 2a5 5 0 00-5 5v2l-1 2h12l-1-2V7a5 5 0 00-5-5z" stroke={color} strokeWidth="1.5" strokeLinejoin="round"/>
      <path d="M6.5 13a1.5 1.5 0 003 0" stroke={color} strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  );
}
