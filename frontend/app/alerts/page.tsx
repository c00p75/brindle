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

  const active   = alerts.filter((a) => a.status === "active").length;
  const critical = alerts.filter((a) => a.severity === "critical" && a.status === "active").length;

  return (
    <>
      <div className="section-header">
        <div>
          <h1 style={{ marginBottom: 2 }}>Alerts &amp; incidents</h1>
          <p style={{ fontSize: 13, color: "#aaaaaa" }}>
            {alerts.length} total · {active} active{critical > 0 ? ` · ${critical} critical` : ""}
          </p>
        </div>
      </div>

      {err && <p className="error" style={{ marginBottom: 16 }}>{err}</p>}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {alerts.length === 0 ? (
          <div style={{ padding: "64px 24px", textAlign: "center" }}>
            <div style={{ width: 52, height: 52, borderRadius: "50%", background: "#edfaf7", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
              <svg width="26" height="26" fill="none" viewBox="0 0 26 26">
                <path d="M4 13.5l5 5L22 7" stroke="#008265" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <p style={{ color: "#686868", fontWeight: 600, fontSize: 15 }}>No alerts — system is quiet</p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Severity</th>
                <th>Source</th>
                <th>Message</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id} style={{ background: a.status === "active" && a.severity === "critical" ? "#fffafa" : undefined }}>
                  <td style={{ color: "#aaaaaa", fontSize: 12, whiteSpace: "nowrap" }}>
                    {new Date(a.created_at_ms).toLocaleString()}
                  </td>
                  <td><span className={`pill ${a.severity}`}>{a.severity}</span></td>
                  <td style={{ fontWeight: 600, color: "#333" }}>{a.source}</td>
                  <td style={{ maxWidth: 380, color: "#555" }}>{a.message}</td>
                  <td><span className={`pill ${a.status}`}>{a.status}</span></td>
                  <td>
                    {a.status === "active" && can(user?.role, "alert:ack") && (
                      <button className="btn ghost" style={{ fontSize: 12, padding: "5px 10px" }}
                        onClick={() => ack(a.id)}>
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
