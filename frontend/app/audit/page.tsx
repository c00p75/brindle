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
          <h1 style={{ marginBottom: 2 }}>Audit log</h1>
          <p style={{ fontSize: 13, color: "#aaaaaa" }}>
            {events.length} events · append-only, immutable record
          </p>
        </div>
      </div>

      {err && <p className="error" style={{ marginBottom: 16 }}>{err}</p>}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {events.length === 0 ? (
          <div style={{ padding: "64px 24px", textAlign: "center" }}>
            <p style={{ color: "#aaaaaa", fontSize: 14 }}>No audit events yet.</p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Resource</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id}>
                  <td style={{ color: "#aaaaaa", fontSize: 12, whiteSpace: "nowrap" }}>
                    {new Date(e.at_ms).toLocaleString()}
                  </td>
                  <td>
                    <span style={{ fontWeight: 700, color: "#0e0e0e" }}>{e.actor_email}</span>
                    <span style={{ fontSize: 11, background: "#f2f3f4", color: "#686868", padding: "1px 5px", borderRadius: 2, marginLeft: 6, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                      {e.actor_role}
                    </span>
                  </td>
                  <td><code style={{ fontSize: 12 }}>{e.action}</code></td>
                  <td style={{ fontSize: 12, color: "#686868" }}>
                    <span style={{ color: "#aaaaaa" }}>{e.resource_type}</span>
                    <span style={{ margin: "0 3px", color: "#d6dadc" }}>·</span>
                    <code style={{ fontSize: 11 }}>{e.resource_id}</code>
                  </td>
                  <td>
                    <span className={`pill ${e.outcome === "ok" ? "applied" : "halted"}`}>{e.outcome}</span>
                    {e.reason && <div style={{ fontSize: 11, color: "#cc2626", marginTop: 3 }}>{e.reason}</div>}
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
