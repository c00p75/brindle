"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, setSession } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("admin12345");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.login(email, password);
      setSession(r.access_token, r.user);
      router.push("/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{
      display: "flex", minHeight: "100vh", alignItems: "center", justifyContent: "center",
    }}>
      <form onSubmit={submit} className="card" style={{ width: 360 }}>
        <h1 style={{ marginTop: 0 }}>Sign in</h1>
        <p style={{ fontSize: 13, color: "#475569", marginTop: -4 }}>
          Paper trading only — live trading is disabled platform-wide.
        </p>

        <label>Email</label>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} style={{ width: "100%" }} required />

        <label>Password</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} style={{ width: "100%" }} required />

        {error && <p className="error">{error}</p>}

        <button type="submit" className="btn" disabled={busy} style={{ marginTop: 16, width: "100%" }}>
          {busy ? "Signing in…" : "Sign in"}
        </button>

        <details style={{ marginTop: 16, fontSize: 12, color: "#64748b" }}>
          <summary>Dev users</summary>
          <ul>
            <li>admin@example.com / admin12345</li>
            <li>operator@example.com / operator12345</li>
            <li>reviewer@example.com / reviewer12345</li>
            <li>viewer@example.com / viewer12345</li>
          </ul>
        </details>
      </form>
    </div>
  );
}
