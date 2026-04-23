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

  return (
    <>
      <h1>Alerts & incidents</h1>
      {err && <p className="error">{err}</p>}
      <div className="card">
        {alerts.length === 0 ? (
          <p>No alerts. System is quiet.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ textAlign: "left", background: "#f8fafc" }}>
                <th style={th}>When</th><th style={th}>Severity</th><th style={th}>Source</th>
                <th style={th}>Message</th><th style={th}>Status</th><th style={th}></th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id} style={{ borderTop: "1px solid #e2e8f0" }}>
                  <td style={td}>{new Date(a.created_at_ms).toLocaleString()}</td>
                  <td style={td}><span className={`pill ${a.severity}`}>{a.severity}</span></td>
                  <td style={td}>{a.source}</td>
                  <td style={td}>{a.message}</td>
                  <td style={td}><span className={`pill ${a.status}`}>{a.status}</span></td>
                  <td style={td}>
                    {a.status === "active" && can(user?.role, "alert:ack") && (
                      <button className="btn secondary" onClick={() => ack(a.id)}>Acknowledge</button>
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

const th: React.CSSProperties = { padding: "10px 12px", fontWeight: 600, fontSize: 13 };
const td: React.CSSProperties = { padding: "10px 12px", verticalAlign: "top" };
