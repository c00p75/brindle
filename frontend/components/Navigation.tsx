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

  const initials = user.email.slice(0, 2).toUpperCase();

  return (
    <nav style={navStyle}>
      <div style={innerStyle}>
        {/* Logo */}
        <Link href="/dashboard" style={logoStyle}>
          <div style={logoIconStyle}>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2 12 L6 7 L9 10 L13 4" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <span style={{ fontWeight: 700, fontSize: 15, color: "#0f172a", letterSpacing: "-0.01em" }}>
            Trading Bot
          </span>
        </Link>

        {/* Nav links */}
        <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
          {LINKS.map((l) => {
            const active = pathname === l.href || (l.href !== "/dashboard" && pathname.startsWith(l.href));
            return (
              <Link
                key={l.href}
                href={l.href}
                style={{
                  padding: "6px 12px",
                  borderRadius: 8,
                  fontSize: 14,
                  fontWeight: active ? 600 : 500,
                  color: active ? "#0d9488" : "#64748b",
                  background: active ? "#f0fdfa" : "transparent",
                  textDecoration: "none",
                  transition: "color 0.15s, background 0.15s",
                  letterSpacing: "0.005em",
                }}
              >
                {l.label}
              </Link>
            );
          })}
        </div>

        {/* Right side */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={paperBadgeStyle}>
            <svg width="8" height="8" viewBox="0 0 8 8" fill="none" style={{ flexShrink: 0 }}>
              <circle cx="4" cy="4" r="3" fill="#0d9488"/>
            </svg>
            Paper only
          </span>

          <Link
            href="/profile"
            title="Profile"
            style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "5px 10px 5px 5px",
              borderRadius: 999,
              border: "1.5px solid #e2e8f0",
              background: "#fff",
              textDecoration: "none",
              transition: "border-color 0.15s",
            }}
          >
            <div style={avatarStyle}>{initials}</div>
            <span style={{ fontSize: 13, color: "#334155", fontWeight: 500 }}>
              {user.email.split("@")[0]}
            </span>
            <span style={{ fontSize: 11, color: "#94a3b8", background: "#f1f5f9", padding: "2px 6px", borderRadius: 4, fontWeight: 600 }}>
              {user.role}
            </span>
          </Link>

          <button onClick={logout} style={logoutBtnStyle}>
            Sign out
          </button>
        </div>
      </div>
    </nav>
  );
}

const navStyle: React.CSSProperties = {
  background: "#fff",
  borderBottom: "1px solid #e8edf3",
  position: "sticky",
  top: 0,
  zIndex: 50,
};

const innerStyle: React.CSSProperties = {
  maxWidth: 1280,
  margin: "0 auto",
  padding: "0 28px",
  height: 60,
  display: "flex",
  alignItems: "center",
  gap: 8,
};

const logoStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  textDecoration: "none",
  marginRight: 16,
  flexShrink: 0,
};

const logoIconStyle: React.CSSProperties = {
  width: 30,
  height: 30,
  borderRadius: 8,
  background: "linear-gradient(135deg, #0d9488, #0f766e)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  boxShadow: "0 2px 6px rgba(13, 148, 136, 0.35)",
};

const paperBadgeStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 5,
  padding: "4px 10px",
  background: "#f0fdfa",
  color: "#0f766e",
  border: "1px solid #ccfbf1",
  borderRadius: 999,
  fontSize: 12,
  fontWeight: 600,
  letterSpacing: "0.02em",
  whiteSpace: "nowrap",
};

const avatarStyle: React.CSSProperties = {
  width: 28,
  height: 28,
  borderRadius: "50%",
  background: "linear-gradient(135deg, #0d9488, #0f766e)",
  color: "#fff",
  fontSize: 11,
  fontWeight: 700,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  flexShrink: 0,
};

const logoutBtnStyle: React.CSSProperties = {
  padding: "6px 14px",
  border: "1.5px solid #e2e8f0",
  background: "#fff",
  borderRadius: 8,
  cursor: "pointer",
  fontSize: 13,
  fontWeight: 500,
  color: "#64748b",
  transition: "border-color 0.15s, color 0.15s",
};
