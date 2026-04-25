"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Navigation from "@/components/Navigation";
import { api, getUser } from "@/lib/api";
import { can } from "@/lib/rbac";
import type { Alert } from "@/lib/types";

export default function AlertsPage() {
  return (
    <AuthGuard>
      <Navigation />
      <div className="container">
        <Alerts />
      </div>
    </AuthGuard>
  );
}

function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const user = getUser();

  async function load() {
    try { setAlerts(await api.listAlerts()); }
    catch (e) { setErr(e instanceof Error ? e.message : "failed"); }
  }
  useEffect(() => { load(); }, []);

  async function ack(id: string) {
    try { await api.ackAlert(id); await load(); }
    catch (e) { alert(e instanceof Error ? e.message : "failed"); }
  }

  const active = alerts.filter((a) => a.status === "active").length;
  const critical = alerts.filter((a) => a.severity === "critical" && a.status === "active").length;

  return (
    <>
      <div className="section-header">
        <div>
          <h1 style={{ marginBottom: 4 }}>Alerts &amp; incidents</h1>
          <p style={{ fontSize: 14, color: "#64748b", margin: 0 }}>
            {alerts.length} total · {active} active{critical > 0 ? ` · ${critical} critical` : ""}
          </p>
        </div>
      </div>

      {err && <p className="error" style={{ marginBottom: 16 }}>{err}</p>}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {alerts.length === 0 ? (
          <div style={{ padding: "56px 24px", textAlign: "center" }}>
            <div style={{ width: 48, height: 48, borderRadius: 14, background: "#f0fdfa", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
              <svg width="24" height="24" fill="none" viewBox="0 0 24 24">
                <path d="M5 13l4 4L19 7" stroke="#0d9488" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <p style={{ color: "#64748b", fontSize: 15 }}>No alerts. System is quiet.</p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Severity</th>
                <th>Source</th>
                <th>Message</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id}>
                  <td style={{ color: "#94a3b8", whiteSpace: "nowrap", fontSize: 13 }}>
                    {new Date(a.created_at_ms).toLocaleString()}
                  </td>
                  <td><span className={`pill ${a.severity}`}>{a.severity}</span></td>
                  <td style={{ color: "#475569", fontWeight: 500 }}>{a.source}</td>
                  <td style={{ maxWidth: 400, color: "#334155" }}>{a.message}</td>
                  <td><span className={`pill ${a.status}`}>{a.status}</span></td>
                  <td>
                    {a.status === "active" && can(user?.role, "alert:ack") && (
                      <button
                        className="btn secondary"
                        style={{ fontSize: 13, padding: "6px 12px" }}
                        onClick={() => ack(a.id)}
                      >
                        Acknowledge
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
