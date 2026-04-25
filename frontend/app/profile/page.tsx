"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Navigation from "@/components/Navigation";
import { api, getUser, setSession, getToken } from "@/lib/api";
import type { TOTPSetupResponse, UserPublic } from "@/lib/types";

export default function ProfilePage() {
  return (
    <AuthGuard>
      <Navigation />
      <div className="container">
        <Profile />
      </div>
    </AuthGuard>
  );
}

function Profile() {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [setup, setSetup] = useState<TOTPSetupResponse | null>(null);
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setUser(getUser());
  }, []);

  function flash(text: string, isErr = false) {
    if (isErr) { setErr(text); setMsg(null); }
    else { setMsg(text); setErr(null); }
    setTimeout(() => { setErr(null); setMsg(null); }, 4000);
  }

  async function startSetup() {
    setBusy(true);
    setErr(null);
    try {
      const res = await api.totpSetup();
      setSetup(res);
      setCode("");
    } catch (e) {
      flash(e instanceof Error ? e.message : "failed", true);
    } finally {
      setBusy(false);
    }
  }

  async function verifyAndEnable() {
    if (!code || code.length !== 6) { flash("Enter the 6-digit code from your authenticator app", true); return; }
    setBusy(true);
    try {
      await api.totpVerify(code);
      const refreshed = await api.me();
      const token = getToken()!;
      setSession(token, refreshed);
      setUser(refreshed);
      setSetup(null);
      setCode("");
      flash("TOTP enabled. You'll need your authenticator app on next login.");
    } catch (e) {
      flash(e instanceof Error ? e.message : "verification failed", true);
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    if (!confirm("Disable TOTP? Your account will use password-only authentication.")) return;
    setBusy(true);
    try {
      await api.totpDisable();
      const refreshed = await api.me();
      const token = getToken()!;
      setSession(token, refreshed);
      setUser(refreshed);
      setSetup(null);
      flash("TOTP disabled.");
    } catch (e) {
      flash(e instanceof Error ? e.message : "failed", true);
    } finally {
      setBusy(false);
    }
  }

  if (!user) return <p>Loading…</p>;

  return (
    <>
      <h1>Profile</h1>

      <div className="card" style={{ maxWidth: 540 }}>
        <h2 style={{ marginTop: 0 }}>Account</h2>
        <p style={{ fontSize: 14, margin: "4px 0" }}><b>Email:</b> {user.email}</p>
        <p style={{ fontSize: 14, margin: "4px 0" }}><b>Role:</b> {user.role}</p>
        <p style={{ fontSize: 14, margin: "4px 0" }}>
          <b>Status:</b> {user.is_active ? "Active" : "Inactive"}
        </p>
      </div>

      <div className="card" style={{ maxWidth: 540, marginTop: 20 }}>
        <h2 style={{ marginTop: 0 }}>Two-factor authentication (TOTP)</h2>

        <p style={{ fontSize: 14, marginTop: 0 }}>
          Status:{" "}
          <span style={{
            fontWeight: 700,
            color: user.totp_enabled ? "#15803d" : "#64748b",
          }}>
            {user.totp_enabled ? "Enabled" : "Disabled"}
          </span>
        </p>

        {!user.totp_enabled && !setup && (
          <button className="btn" onClick={startSetup} disabled={busy}>
            Enable TOTP
          </button>
        )}

        {user.totp_enabled && !setup && (
          <button
            className="btn danger"
            onClick={disable}
            disabled={busy}
            style={{ fontSize: 13 }}
          >
            Disable TOTP
          </button>
        )}

        {setup && (
          <div style={{ marginTop: 16 }}>
            <p style={{ fontSize: 14, marginBottom: 12 }}>
              Scan this link in your authenticator app (Google Authenticator, Authy, 1Password, etc.),
              or enter the secret manually.
            </p>

            <div style={{ padding: 12, background: "#f1f5f9", borderRadius: 8, marginBottom: 12 }}>
              <p style={{ fontSize: 12, color: "#475569", margin: "0 0 6px" }}>Manual secret key:</p>
              <code style={{ fontSize: 14, letterSpacing: 2, userSelect: "all" }}>{setup.secret}</code>
            </div>

            <div style={{ padding: 12, background: "#f1f5f9", borderRadius: 8, marginBottom: 16 }}>
              <p style={{ fontSize: 12, color: "#475569", margin: "0 0 6px" }}>
                Or open the provisioning URI in your authenticator:
              </p>
              <a
                href={setup.provisioning_uri}
                style={{ fontSize: 12, wordBreak: "break-all", color: "#1d4ed8" }}
              >
                {setup.provisioning_uri}
              </a>
            </div>

            <label style={{ fontSize: 14 }}>Enter the 6-digit code from your app to confirm:</label>
            <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
              <input
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="000000"
                style={{ width: 120, letterSpacing: 4, textAlign: "center", fontSize: 18 }}
                maxLength={6}
                onKeyDown={(e) => e.key === "Enter" && verifyAndEnable()}
              />
              <button className="btn" onClick={verifyAndEnable} disabled={busy || code.length !== 6}>
                Verify &amp; enable
              </button>
              <button
                className="btn secondary"
                onClick={() => { setSetup(null); setCode(""); }}
                disabled={busy}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {err && <p className="error" style={{ marginTop: 12 }}>{err}</p>}
        {msg && <p style={{ color: "#065f46", marginTop: 12 }}>{msg}</p>}
      </div>
    </>
  );
}
