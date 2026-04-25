"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!email) return;
    setBusy(true);
    setErr(null);
    try {
      await api.forgotPassword(email);
      setSubmitted(true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f8fafc" }}>
      <div className="card" style={{ width: 360 }}>
        <h1 style={{ marginTop: 0, fontSize: 22 }}>Reset password</h1>

        {submitted ? (
          <>
            <p style={{ fontSize: 14, color: "#475569" }}>
              If that email address has an account, a reset link has been sent (check the server
              console in development — email delivery is via console logger).
            </p>
            <Link href="/login" style={{ fontSize: 14, color: "#1d4ed8" }}>Back to login</Link>
          </>
        ) : (
          <form onSubmit={submit}>
            <label style={{ fontSize: 14 }}>Email address</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              style={{ width: "100%", marginTop: 4, marginBottom: 16 }}
            />
            {err && <p className="error" style={{ marginBottom: 12 }}>{err}</p>}
            <button className="btn" type="submit" disabled={busy} style={{ width: "100%" }}>
              {busy ? "Sending…" : "Send reset link"}
            </button>
            <p style={{ fontSize: 13, marginTop: 12, textAlign: "center" }}>
              <Link href="/login" style={{ color: "#64748b" }}>Back to login</Link>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
