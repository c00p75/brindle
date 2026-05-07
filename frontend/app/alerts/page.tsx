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

      {alerts.length > 0 && <AlertInsightsCard />}

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

function AlertInsightsCard() {
  const [data, setData] = useState<Awaited<ReturnType<typeof api.alertInsights>> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function go() {
    setErr(null);
    setLoading(true);
    try { setData(await api.alertInsights(50)); }
    catch (e) { setErr(e instanceof Error ? e.message : "failed"); }
    finally { setLoading(false); }
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>✨ AI Alert Insights</h2>
        <button className="btn ghost" disabled={loading} onClick={go} style={{ fontSize: 12 }}>
          {loading ? "Analysing…" : data ? "Refresh" : "Analyse"}
        </button>
      </div>
      {err && <p style={{ color: "#cc2626", fontSize: 13 }}>{err}</p>}
      {!data && !err && !loading && (
        <p style={{ color: "#aaaaaa", fontSize: 13, margin: 0 }}>
          Click <b>Analyse</b> to cluster recent alerts, identify likely root causes, and surface
          suggested actions. Uses Groq (no PII sent — only severity/source/message text).
        </p>
      )}
      {data && (
        <>
          {data.summary && (
            <p style={{ fontSize: 13, color: "#555", marginBottom: 12 }}>
              <b>Summary:</b> {data.summary} <span style={{ color: "#aaaaaa" }}>({data.input_count} alerts analysed)</span>
            </p>
          )}
          {data.groups.length === 0 ? (
            <p style={{ color: "#aaaaaa", fontSize: 13, margin: 0 }}>No groups produced.</p>
          ) : (
            <div style={{ display: "grid", gap: 10 }}>
              {data.groups.map((g, i) => (
                <div key={i} style={{ border: "1px solid #e8eaeb", borderRadius: 6, padding: "10px 12px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                    <span style={{ fontWeight: 700 }}>{g.pattern}</span>
                    <span className={`pill ${g.severity}`}>{g.severity} × {g.count}</span>
                  </div>
                  <div style={{ fontSize: 12, color: "#686868", marginBottom: 4 }}>
                    <b>Likely cause:</b> {g.likely_cause}
                  </div>
                  <div style={{ fontSize: 12, color: "#0e0e0e" }}>
                    <b>Suggested action:</b> {g.suggested_action}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
