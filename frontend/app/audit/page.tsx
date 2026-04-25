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
      <div className="section-header">
        <div>
          <h1 style={{ marginBottom: 4 }}>Audit log</h1>
          <p style={{ fontSize: 14, color: "#64748b", margin: 0 }}>
            Append-only record of all state-changing operations
          </p>
        </div>
      </div>

      {err && <p className="error" style={{ marginBottom: 16 }}>{err}</p>}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {events.length === 0 ? (
          <div style={{ padding: "56px 24px", textAlign: "center" }}>
            <p style={{ color: "#94a3b8", fontSize: 15 }}>No audit events yet.</p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Resource</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id}>
                  <td style={{ color: "#94a3b8", whiteSpace: "nowrap", fontSize: 13 }}>
                    {new Date(e.at_ms).toLocaleString()}
                  </td>
                  <td>
                    <span style={{ fontWeight: 500, color: "#0f172a" }}>{e.actor_email}</span>
                    <span style={{ fontSize: 12, color: "#94a3b8", marginLeft: 6 }}>({e.actor_role})</span>
                  </td>
                  <td>
                    <code style={{ fontSize: 13 }}>{e.action}</code>
                  </td>
                  <td style={{ fontSize: 13 }}>
                    <span style={{ color: "#64748b" }}>{e.resource_type}</span>
                    <span style={{ color: "#94a3b8", margin: "0 3px" }}>:</span>
                    <code style={{ fontSize: 12 }}>{e.resource_id}</code>
                  </td>
                  <td>
                    <span className={`pill ${e.outcome === "ok" ? "applied" : "halted"}`}>{e.outcome}</span>
                    {e.reason && (
                      <div style={{ fontSize: 12, color: "#be123c", marginTop: 3 }}>{e.reason}</div>
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
