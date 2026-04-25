"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api } from "@/lib/api";

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetPassword />
    </Suspense>
  );
}

function ResetPassword() {
  const params = useSearchParams();
  const [token] = useState(params.get("token") ?? "");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < 8) { setErr("Password must be at least 8 characters"); return; }
    if (password !== confirm) { setErr("Passwords do not match"); return; }
    if (!token) { setErr("Missing reset token — use the link from your email"); return; }
    setBusy(true);
    setErr(null);
    try {
      await api.resetPassword(token, password);
      setDone(true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "reset failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f8fafc" }}>
      <div className="card" style={{ width: 360 }}>
        <h1 style={{ marginTop: 0, fontSize: 22 }}>Set new password</h1>

        {done ? (
          <>
            <p style={{ fontSize: 14, color: "#475569" }}>Password updated. You can now log in with your new password.</p>
            <Link href="/login" className="btn" style={{ textDecoration: "none", display: "inline-block" }}>
              Go to login
            </Link>
          </>
        ) : (
          <form onSubmit={submit}>
            {!token && (
              <p className="error" style={{ marginBottom: 12 }}>
                No reset token found. Please use the link from your reset email.
              </p>
            )}
            <label style={{ fontSize: 14 }}>New password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              required
              style={{ width: "100%", marginTop: 4, marginBottom: 12 }}
            />
            <label style={{ fontSize: 14 }}>Confirm password</label>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Repeat new password"
              required
              style={{ width: "100%", marginTop: 4, marginBottom: 16 }}
            />
            {err && <p className="error" style={{ marginBottom: 12 }}>{err}</p>}
            <button className="btn" type="submit" disabled={busy || !token} style={{ width: "100%" }}>
              {busy ? "Saving…" : "Set new password"}
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
