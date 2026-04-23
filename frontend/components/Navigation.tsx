"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearSession, getUser } from "@/lib/api";
import type { UserPublic } from "@/lib/types";

const LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/bots", label: "Bots" },
  { href: "/alerts", label: "Alerts" },
  { href: "/audit", label: "Audit" },
];

export default function Navigation() {
  const router = useRouter();
  const [user, setUser] = useState<UserPublic | null>(null);

  useEffect(() => { setUser(getUser()); }, []);

  function logout() {
    clearSession();
    router.push("/login");
  }

  if (!user) return null;

  return (
    <nav style={{
      display: "flex", gap: 16, padding: "12px 24px", borderBottom: "1px solid #e5e7eb",
      alignItems: "center", background: "#fff", position: "sticky", top: 0, zIndex: 10,
    }}>
      <strong style={{ marginRight: 24 }}>Trading Bot Platform</strong>
      {LINKS.map((l) => (
        <Link key={l.href} href={l.href} style={{ color: "#334155", textDecoration: "none" }}>
          {l.label}
        </Link>
      ))}
      <span style={{ flex: 1 }} />
      <span style={{ background: "#fef3c7", color: "#92400e", padding: "2px 8px", borderRadius: 6, fontSize: 12 }}>
        PAPER TRADING ONLY
      </span>
      <span style={{ fontSize: 13, color: "#475569" }}>
        {user.email} · <b>{user.role}</b>
      </span>
      <button onClick={logout} style={btnSecondary}>Logout</button>
    </nav>
  );
}

const btnSecondary: React.CSSProperties = {
  padding: "6px 12px", border: "1px solid #cbd5e1", background: "#fff",
  borderRadius: 6, cursor: "pointer", fontSize: 13,
};
