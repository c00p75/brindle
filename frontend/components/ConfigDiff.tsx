"use client";

import type { DiffEntry } from "@/lib/types";

const RISKY_PREFIX = ["broker.", "risk.", "strategy.strategy_id"];

function isRisky(path: string): boolean {
  return RISKY_PREFIX.some((p) => path.startsWith(p) || path === p.replace(/\.$/, ""));
}

export default function ConfigDiff({ changes }: { changes: DiffEntry[] }) {
  if (changes.length === 0) {
    return (
      <p style={{ color: "#94a3b8", fontSize: 14, padding: "8px 0" }}>No changes vs active config.</p>
    );
  }
  return (
    <div style={{ borderRadius: 8, overflow: "hidden", border: "1px solid #e8edf3" }}>
      <table style={{ fontSize: 13 }}>
        <thead>
          <tr>
            <th style={{ width: "30%" }}>Field</th>
            <th>Before</th>
            <th>After</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((c) => (
            <tr key={c.path}>
              <td>
                <code style={{ fontSize: 12 }}>{c.path}</code>
                {isRisky(c.path) && (
                  <span style={{
                    marginLeft: 8, fontSize: 10, fontWeight: 700, letterSpacing: "0.05em",
                    background: "#fff1f2", color: "#be123c", padding: "2px 6px", borderRadius: 4,
                    textTransform: "uppercase",
                  }}>
                    risky
                  </span>
                )}
              </td>
              <td style={{ color: "#be123c" }}>{format(c.before)}</td>
              <td style={{ color: "#15803d" }}>{format(c.after)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function format(v: unknown) {
  if (v === undefined) return <em style={{ color: "#94a3b8" }}>—</em>;
  if (v === null) return <em style={{ color: "#94a3b8" }}>null</em>;
  if (typeof v === "object") return <code style={{ fontSize: 11 }}>{JSON.stringify(v)}</code>;
  if (typeof v === "boolean") return <code style={{ fontSize: 12 }}>{String(v)}</code>;
  return <span style={{ fontWeight: 500 }}>{String(v)}</span>;
}
