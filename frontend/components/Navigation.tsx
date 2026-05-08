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
          <img src="/logo.png" alt="Brindle" width="28" height="28" style={{ borderRadius: 4 }} />
          <span style={{ fontWeight: 800, fontSize: 16, color: "#0e0e0e", letterSpacing: "-0.02em" }}>
            Brindle
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
                  color: active ? "#4f46e5" : "#686868",
                  textDecoration: "none",
                  borderBottom: active ? "2px solid #4f46e5" : "2px solid transparent",
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
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: "auto" }}>
          <style>{`
            .nav-user-chip:hover { background: #f4f5f6 !important; border-color: #d8dadb !important; }
            .nav-logout-btn:hover { background: #fef2f2 !important; border-color: #fecaca !important; color: #dc2626 !important; }
            .nav-logout-btn:hover svg { stroke: #dc2626; }
          `}</style>

          {/* Paper-only badge */}
          <div style={paperBadge}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#4f46e5", flexShrink: 0, boxShadow: "0 0 0 2px rgba(79,70,229,0.2)" }} />
            Paper only
          </div>


          {/* Divider */}
          <div style={{ width: 1, height: 20, background: "#e2e5e7", margin: "0 4px", flexShrink: 0 }} />

          {/* User chip */}
          <Link href="/profile" className="nav-user-chip" style={userChip}>
            <div style={avatar}>{user.email.slice(0, 2).toUpperCase()}</div>
            <div style={{ lineHeight: 1.3, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#0e0e0e", maxWidth: 130, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {user.email.split("@")[0]}
              </div>
              <div style={{ marginTop: 2 }}>
                <span style={rolePill}>{user.role}</span>
              </div>
            </div>
          </Link>

          {/* Log out */}
          <button onClick={logout} className="nav-logout-btn" title="Log out" style={logoutBtn}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#666" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, transition: "stroke 0.12s" }}>
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
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
  padding: "4px 10px 4px 8px",
  background: "#f5f7ff",
  color: "#4338ca",
  border: "1px solid #c7d2fe",
  borderRadius: 999,
  fontSize: 10,
  fontWeight: 800,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  flexShrink: 0,
};

const userChip: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 9,
  padding: "5px 10px 5px 6px",
  borderRadius: 8,
  border: "1px solid transparent",
  background: "transparent",
  textDecoration: "none",
  transition: "background 0.12s, border-color 0.12s",
  cursor: "pointer",
};

const avatar: React.CSSProperties = {
  width: 32,
  height: 32,
  borderRadius: "50%",
  background: "linear-gradient(135deg, #818cf8 0%, #4f46e5 100%)",
  color: "#fff",
  fontSize: 12,
  fontWeight: 800,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  flexShrink: 0,
  boxShadow: "0 1px 4px rgba(79,70,229,0.35)",
};

const rolePill: React.CSSProperties = {
  display: "inline-block",
  fontSize: 9,
  fontWeight: 700,
  letterSpacing: "0.07em",
  textTransform: "uppercase",
  color: "#5b6e7c",
  background: "#edf0f2",
  borderRadius: 3,
  padding: "1px 5px",
};

const logoutBtn: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  padding: "6px 12px",
  background: "transparent",
  border: "1px solid #e2e5e7",
  borderRadius: 6,
  fontSize: 13,
  fontWeight: 600,
  color: "#555",
  cursor: "pointer",
  transition: "background 0.12s, border-color 0.12s, color 0.12s",
  whiteSpace: "nowrap",
};
