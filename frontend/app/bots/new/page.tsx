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
  const [allocation, setAllocation] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const amt = allocation ? parseFloat(allocation) : undefined;
      const bot = await api.createBot(name.trim(), amt);
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
        style={{ width: "100%", marginBottom: 16 }}
        placeholder="e.g. fx-trend-eur-usd"
      />

      <label>Initial Capital Allocation ($)</label>
      <p style={{ fontSize: 12, color: "#64748b", marginTop: -8, marginBottom: 8 }}>
        Optional. If set, this bot will treat this amount as its total "account size" for risk calculations. 
        Leave empty to use the full broker balance.
      </p>
      <input
        type="number"
        value={allocation}
        onChange={(e) => setAllocation(e.target.value)}
        step="0.01"
        min="0"
        style={{ width: "100%" }}
        placeholder="e.g. 100.00"
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
