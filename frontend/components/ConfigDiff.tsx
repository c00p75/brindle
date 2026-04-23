"use client";

import type { DiffEntry } from "@/lib/types";

const RISKY_PREFIX = ["broker.", "risk.", "strategy.strategy_id"];

function isRisky(path: string): boolean {
  return RISKY_PREFIX.some((p) => path.startsWith(p) || path === p.replace(/\.$/, ""));
}

export default function ConfigDiff({ changes }: { changes: DiffEntry[] }) {
  if (changes.length === 0) return <p style={{ color: "#64748b" }}>No changes.</p>;
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
      <thead>
        <tr style={{ textAlign: "left", background: "#f8fafc" }}>
          <th style={th}>Path</th>
          <th style={th}>Before</th>
          <th style={th}>After</th>
        </tr>
      </thead>
      <tbody>
        {changes.map((c) => (
          <tr key={c.path} style={{ borderTop: "1px solid #e2e8f0" }}>
            <td style={td}>
              <code>{c.path}</code>
              {isRisky(c.path) && (
                <span style={{ marginLeft: 8, color: "#b91c1c", fontSize: 11 }}>(risky)</span>
              )}
            </td>
            <td style={{ ...td, color: "#b91c1c" }}>{format(c.before)}</td>
            <td style={{ ...td, color: "#065f46" }}>{format(c.after)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function format(v: unknown) {
  if (v === undefined) return <em style={{ color: "#94a3b8" }}>—</em>;
  if (v === null) return <em style={{ color: "#94a3b8" }}>null</em>;
  if (typeof v === "object") return <code>{JSON.stringify(v)}</code>;
  return String(v);
}

const th: React.CSSProperties = { padding: "8px 10px", fontWeight: 600 };
const td: React.CSSProperties = { padding: "8px 10px", verticalAlign: "top" };
