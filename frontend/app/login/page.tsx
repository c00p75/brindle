"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, setSession } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp]         = useState("");
  const [needTotp, setNeedTotp] = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [busy, setBusy]         = useState(false);

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
      if (msg.includes("totp_code required")) setNeedTotp(true);
      else setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", background: "#f2f3f4" }}>
      {/* Left branding panel */}
      <div style={{
        width: 420, flexShrink: 0,
        background: "#0e0e0e",
        display: "flex", flexDirection: "column",
        justifyContent: "center", padding: "60px 56px",
      }}>
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 48 }}>
          <img src="/logo.png" alt="Brindle" width="36" height="36" style={{ borderRadius: 6 }} />
          <span style={{ fontWeight: 800, fontSize: 20, color: "#fff", letterSpacing: "-0.02em" }}>Brindle</span>
        </div>

        <h2 style={{ color: "#fff", fontSize: 24, fontWeight: 800, letterSpacing: "-0.02em", marginBottom: 16 }}>
          Paper trading.<br/>Real discipline.
        </h2>
        <p style={{ color: "#686868", fontSize: 14, lineHeight: 1.7, marginBottom: 40 }}>
          Full governance, risk controls, and audit trail — without touching real capital.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {["Risk gates on every order", "Draft → validate → apply config workflow", "Append-only audit trail", "TOTP two-factor auth"].map((f) => (
            <div key={f} style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 20, height: 20, borderRadius: "50%", background: "#1a1a1a", border: "1px solid #333", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <svg width="10" height="10" fill="none" viewBox="0 0 10 10">
                  <path d="M2 5.5l2 2 4-4" stroke="#4f46e5" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <span style={{ fontSize: 13, color: "#888" }}>{f}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Right form panel */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 32 }}>
        <div style={{ width: "100%", maxWidth: 380 }}>
          <h1 style={{ fontSize: 24, marginBottom: 6 }}>
            {needTotp ? "Two-factor verification" : "Welcome back"}
          </h1>
          <p style={{ color: "#aaaaaa", marginBottom: 28, fontSize: 13 }}>
            {needTotp
              ? "Enter the 6-digit code from your authenticator app"
              : "Sign in to your account"}
          </p>

          <form onSubmit={submit}>
            {!needTotp ? (
              <>
                <label>Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  autoFocus
                  style={{ width: "100%", marginBottom: 4 }}
                />
                <label>Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  style={{ width: "100%" }}
                />
              </>
            ) : (
              <input
                type="text"
                inputMode="numeric"
                value={totp}
                onChange={(e) => setTotp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="000000"
                maxLength={6}
                autoFocus
                style={{ width: "100%", letterSpacing: 6, textAlign: "center", fontSize: 24, fontWeight: 700 }}
              />
            )}

            {error && <p className="error" style={{ marginTop: 12, marginBottom: 0 }}>{error}</p>}

            <button type="submit" className="btn" disabled={busy}
              style={{ marginTop: 20, width: "100%", padding: "12px 20px", fontSize: 15 }}>
              {busy ? "Signing in…" : needTotp ? "Verify" : "Log in"}
            </button>

            {needTotp && (
              <button type="button" className="btn ghost"
                style={{ marginTop: 10, width: "100%", fontSize: 13 }}
                onClick={() => { setNeedTotp(false); setTotp(""); }}>
                ← Back
              </button>
            )}
          </form>

          {!needTotp && (
            <p style={{ fontSize: 13, textAlign: "center", marginTop: 20, color: "#aaaaaa" }}>
              <Link href="/forgot-password">Forgot password?</Link>
            </p>
          )}

          <div style={{ marginTop: 40, padding: "14px 16px", background: "#fff", border: "1px solid #e8eaeb", borderRadius: 4 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#4f46e5", flexShrink: 0 }} />
              <span style={{ fontSize: 11, color: "#aaaaaa", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                Paper trading only · live execution disabled platform-wide
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
