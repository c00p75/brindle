"use client";

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

  const running = bots.filter((b) => b.state === "running").length;
  const halted = bots.filter((b) => b.state === "halted" || b.state === "error").length;
  const activeAlerts = alerts.filter((a) => a.status === "active").length;

  return (
    <>
      <h1>Dashboard</h1>
      {err && <p className="error">{err}</p>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 24 }}>
        <Metric label="Total bots" value={bots.length} />
        <Metric label="Running" value={running} tone="good" />
        <Metric label="Halted / Error" value={halted} tone={halted ? "bad" : undefined} />
        <Metric label="Active alerts" value={activeAlerts} tone={activeAlerts ? "bad" : undefined} />
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Safety posture</h2>
        <ul>
          <li>Paper trading: <b>enforced</b></li>
          <li>Live trading: <b>disabled</b></li>
          <li>Config workflow: draft → validate → apply → audit</li>
        </ul>
      </div>
    </>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone?: "good" | "bad" }) {
  const color = tone === "good" ? "#166534" : tone === "bad" ? "#991b1b" : "#0f172a";
  return (
    <div className="card">
      <div style={{ fontSize: 13, color: "#64748b" }}>{label}</div>
      <div style={{ fontSize: 32, fontWeight: 700, color }}>{value}</div>
    </div>
  );
}
