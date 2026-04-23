"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Navigation from "@/components/Navigation";
import { api } from "@/lib/api";
import type { AuditEvent } from "@/lib/types";

export default function AuditPage() {
  return (
    <AuthGuard>
      <Navigation />
      <div className="container">
        <Audit />
      </div>
    </AuthGuard>
  );
}

function Audit() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.listAudit().then(setEvents).catch((e) => setErr(e instanceof Error ? e.message : "failed"));
  }, []);

  return (
    <>
      <h1>Audit log</h1>
      {err && <p className="error">{err}</p>}
      <div className="card">
        {events.length === 0 ? (
          <p>No audit events yet.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ textAlign: "left", background: "#f8fafc" }}>
                <th style={th}>When</th><th style={th}>Actor</th><th style={th}>Action</th>
                <th style={th}>Resource</th><th style={th}>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} style={{ borderTop: "1px solid #e2e8f0" }}>
                  <td style={td}>{new Date(e.at_ms).toLocaleString()}</td>
                  <td style={td}>{e.actor_email} <span style={{ color: "#64748b" }}>({e.actor_role})</span></td>
                  <td style={td}><code>{e.action}</code></td>
                  <td style={td}>{e.resource_type}:<code>{e.resource_id}</code></td>
                  <td style={td}>
                    <span className={`pill ${e.outcome === "ok" ? "applied" : "halted"}`}>{e.outcome}</span>
                    {e.reason && <div style={{ fontSize: 12, color: "#b91c1c" }}>{e.reason}</div>}
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
