"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearSession, getUser } from "@/lib/api";
import type { UserPublic } from "@/lib/types";

const LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/bots", label: "Bots" },
  { href: "/research", label: "Research" },
  { href: "/alerts", label: "Alerts" },
  { href: "/audit", label: "Audit" },
];

export default function Navigation() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserPublic | null>(null);

  useEffect(() => { setUser(getUser()); }, []);

  function logout() {
    clearSession();
    router.push("/login");
  }

  if (!user) return null;

  return (
    <nav style={navWrap}>
      <div style={navInner}>
        {/* Logo */}
        <Link href="/dashboard" style={logoLink}>
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <rect width="28" height="28" rx="4" fill="#ff444f"/>
            <path d="M6 20 L11 12 L15 16 L20 8" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <span style={{ fontWeight: 800, fontSize: 16, color: "#0e0e0e", letterSpacing: "-0.02em" }}>
            TradingBot
          </span>
        </Link>

        {/* Primary nav */}
        <div style={{ display: "flex", alignItems: "stretch", height: "100%", gap: 0 }}>
          {LINKS.map((l) => {
            const active = pathname === l.href || (l.href !== "/dashboard" && pathname.startsWith(l.href));
            return (
              <Link
                key={l.href}
                href={l.href}
                style={{
                  display: "flex",
                  alignItems: "center",
                  padding: "0 16px",
                  fontSize: 14,
                  fontWeight: 600,
                  color: active ? "#ff444f" : "#686868",
                  textDecoration: "none",
                  borderBottom: active ? "2px solid #ff444f" : "2px solid transparent",
                  transition: "color 0.15s, border-color 0.15s",
                  whiteSpace: "nowrap",
                }}
              >
                {l.label}
              </Link>
            );
          })}
        </div>

        {/* Right side */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginLeft: "auto" }}>
          {/* Paper-only badge */}
          <div style={paperBadge}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#ff444f", flexShrink: 0 }} />
            Paper only
          </div>

          {/* User menu */}
          <Link href="/profile" style={userChip}>
            <div style={avatar}>{user.email.slice(0, 2).toUpperCase()}</div>
            <div style={{ lineHeight: 1.3 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#0e0e0e" }}>
                {user.email.split("@")[0]}
              </div>
              <div style={{ fontSize: 11, color: "#aaaaaa", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                {user.role}
              </div>
            </div>
          </Link>

          <button onClick={logout} className="btn ghost" style={{ padding: "7px 14px", fontSize: 13 }}>
            Log out
          </button>
        </div>
      </div>
    </nav>
  );
}

const navWrap: React.CSSProperties = {
  background: "#fff",
  borderBottom: "1px solid #e8eaeb",
  position: "sticky",
  top: 0,
  zIndex: 50,
  height: 56,
};

const navInner: React.CSSProperties = {
  maxWidth: 1280,
  margin: "0 auto",
  padding: "0 32px",
  height: "100%",
  display: "flex",
  alignItems: "stretch",
  gap: 0,
};

const logoLink: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  textDecoration: "none",
  marginRight: 24,
  flexShrink: 0,
};

const paperBadge: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  padding: "4px 10px",
  background: "#fff5f5",
  color: "#cc2626",
  border: "1px solid #ffd0d0",
  borderRadius: 3,
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: "0.05em",
  textTransform: "uppercase",
};

const userChip: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  padding: "6px 12px",
  borderRadius: 4,
  border: "1px solid #e8eaeb",
  background: "#fafafa",
  textDecoration: "none",
  transition: "border-color 0.15s",
};

const avatar: React.CSSProperties = {
  width: 28,
  height: 28,
  borderRadius: "50%",
  background: "#ff444f",
  color: "#fff",
  fontSize: 11,
  fontWeight: 800,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  flexShrink: 0,
};
