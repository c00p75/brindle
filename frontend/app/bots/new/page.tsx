"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import Navigation from "@/components/Navigation";
import { api } from "@/lib/api";

export default function NewBotPage() {
  return (
    <AuthGuard>
      <Navigation />
      <div className="container">
        <NewBot />
      </div>
    </AuthGuard>
  );
}

function NewBot() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const bot = await api.createBot(name.trim());
      router.push(`/bots/${bot.id}/config`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card" style={{ maxWidth: 520 }}>
      <h1 style={{ marginTop: 0 }}>Create bot</h1>
      <p style={{ color: "#475569", fontSize: 14 }}>
        Step 1: name your bot. Step 2: configure strategy, risk, and broker.
      </p>
      <label>Name</label>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
        maxLength={80}
        style={{ width: "100%" }}
        placeholder="e.g. fx-trend-eur-usd"
      />
      {err && <p className="error">{err}</p>}
      <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
        <button className="btn" type="submit" disabled={busy || !name.trim()}>
          {busy ? "Creating…" : "Create & configure"}
        </button>
        <button type="button" className="btn secondary" onClick={() => router.back()}>Cancel</button>
      </div>
    </form>
  );
}
