"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, setSession } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [needTotp, setNeedTotp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.login(email, password, needTotp ? totp : undefined);
      setSession(r.access_token, r.user);
      router.push("/dashboard");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "login failed";
      if (msg.includes("totp_code required")) {
        setNeedTotp(true);
      } else {
        setError(msg);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#f0f4f8" }}>
      {/* Left panel */}
      <div style={{
        flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        background: "linear-gradient(135deg, #0d9488 0%, #0f766e 100%)",
        padding: 48, minHeight: "100vh",
      }}>
        <div style={{ color: "#fff", maxWidth: 360 }}>
          <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: "-0.03em", marginBottom: 16 }}>
            Trading Bot Platform
          </div>
          <p style={{ fontSize: 16, opacity: 0.85, lineHeight: 1.6 }}>
            Paper-trading-first infrastructure with full governance, audit trail, and risk controls.
          </p>
        </div>
      </div>

      {/* Form */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
        <div style={{ width: "100%", maxWidth: 380 }}>
          {/* Logo */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 36 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: "linear-gradient(135deg, #0d9488, #0f766e)",
              display: "flex", alignItems: "center", justifyContent: "center",
              boxShadow: "0 4px 12px rgba(13,148,136,0.3)",
            }}>
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M2 14 L7 8 L10.5 11.5 L15 5" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <span style={{ fontWeight: 700, fontSize: 17, color: "#0f172a", letterSpacing: "-0.01em" }}>Trading Bot</span>
          </div>

          <h1 style={{ fontSize: 26, marginBottom: 6 }}>Welcome back</h1>
          <p style={{ fontSize: 14, color: "#64748b", marginBottom: 28 }}>
            Sign in to your account
          </p>

          <form onSubmit={submit}>
            <label>Email address</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoFocus
            />

            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />

            {needTotp && (
              <>
                <label>Authenticator code</label>
                <input
                  type="text"
                  inputMode="numeric"
                  value={totp}
                  onChange={(e) => setTotp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="000000"
                  style={{ letterSpacing: 4, textAlign: "center", fontSize: 18 }}
                  maxLength={6}
                  autoFocus
                />
              </>
            )}

            {error && <p className="error" style={{ marginTop: 12 }}>{error}</p>}

            <button type="submit" className="btn" disabled={busy} style={{ marginTop: 20, width: "100%" }}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p style={{ fontSize: 13, textAlign: "center", marginTop: 16, color: "#94a3b8" }}>
            <Link href="/forgot-password" style={{ color: "#64748b" }}>Forgot password?</Link>
          </p>

          <div style={{ marginTop: 36, paddingTop: 20, borderTop: "1px solid #e8edf3", display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#0d9488" }} />
            <span style={{ fontSize: 12, color: "#64748b", fontWeight: 500 }}>Paper trading only · live trading disabled</span>
          </div>
        </div>
      </div>
    </div>
  );
}
