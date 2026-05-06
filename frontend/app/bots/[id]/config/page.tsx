"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import ConfigDiff from "@/components/ConfigDiff";
import Navigation from "@/components/Navigation";
import { api, getUser } from "@/lib/api";
import { can } from "@/lib/rbac";
import type { BotConfig, ConfigVersion, DiffEntry } from "@/lib/types";

const DEFAULT_CONFIG = (botId: string): BotConfig => ({
  bot_id: botId,
  version: 1,
  name: "new-config",
  description: "",
  strategy: {
    strategy_id: "trend_v1",
    params: { fast: 5, slow: 20, qty: 1000, min_cross_pct: 0.02, cooldown_ticks: 10 },
  },
  risk: {
    max_position_notional: 5000,
    max_total_exposure: 20000,
    max_daily_loss: 500,
    max_drawdown_pct: 10,
    max_open_orders: 5,
    kill_switch: false,
  },
  broker: {
    type: "deriv",
    environment: "demo",
    account_id: "",
    credential_ref: "secret://env/DERIV_API_TOKEN",
    symbol_namespace: "deriv",
  },
  symbols: ["V75/USD"],
});

export default function ConfigEditorPage() {
  return (
    <AuthGuard>
      <Navigation />
      <div className="container">
        <ConfigEditor />
      </div>
    </AuthGuard>
  );
}

function ConfigEditor() {
  const { id } = useParams<{ id: string }>();
  const user = getUser();
  const [cfg, setCfg] = useState<BotConfig>(() => DEFAULT_CONFIG(id));
  const [adapters, setAdapters] = useState<string[]>([]);
  const [strategies, setStrategies] = useState<string[]>([]);
  const [paramSchema, setParamSchema] = useState<Record<string, unknown> | null>(null);
  const [active, setActive] = useState<ConfigVersion | null>(null);
  const [draft, setDraft] = useState<ConfigVersion | null>(null);
  const [diff, setDiff] = useState<DiffEntry[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const [a, s, ac] = await Promise.all([api.listAdapters(id), api.listStrategies(id), api.activeConfig(id)]);
        setAdapters(a);
        setStrategies(s);
        setActive(ac);
        if (ac) setCfg({ ...ac.config, bot_id: id });
      } catch (e) {
        setErr(e instanceof Error ? e.message : "failed");
      }
    })();
  }, [id]);

  // Load the param schema whenever the selected strategy changes, so the UI
  // can show allowed keys and offer a "restore defaults" affordance.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await api.strategyParamSchema(id, cfg.strategy.strategy_id);
        if (!cancelled) setParamSchema(s);
      } catch {
        if (!cancelled) setParamSchema(null);
      }
    })();
    return () => { cancelled = true; };
  }, [id, cfg.strategy.strategy_id]);

  async function onStrategyChange(strategyId: string) {
    // When the user picks a new strategy, replace params with that strategy's
    // defaults — otherwise stale keys from the previous strategy will fail
    // validation.
    let defaults: Record<string, unknown> = {};
    try { defaults = await api.strategyParamSchema(id, strategyId); } catch { /* leave empty */ }
    setCfg({ ...cfg, strategy: { strategy_id: strategyId, params: defaults } });
  }

  const risky = useMemo(
    () => diff.some((c) => c.path.startsWith("broker.") || c.path.startsWith("risk.") || c.path === "strategy.strategy_id"),
    [diff]
  );

  function flash(setter: (v: string | null) => void, text: string) {
    setter(text);
    setTimeout(() => setter(null), 3000);
  }

  async function saveDraft() {
    setErr(null);
    try {
      const d = await api.createDraft(id, { ...cfg, bot_id: id });
      setDraft(d);
      flash(setMsg, `Draft #${d.version} saved`);
    } catch (e) { setErr(e instanceof Error ? e.message : "failed"); }
  }

  async function validate() {
    if (!draft) return;
    setErr(null);
    try {
      const d = await api.validateConfig(id, draft.version);
      setDraft(d);
      const res = await api.diffConfig(id, draft.version);
      setDiff(res.changes);
      if (d.validation_errors.length) setErr("Validation failed: " + d.validation_errors.join("; "));
      else flash(setMsg, "Validated — ready to apply");
    } catch (e) { setErr(e instanceof Error ? e.message : "failed"); }
  }

  async function apply() {
    if (!draft) return;
    setErr(null);
    try {
      const d = await api.applyConfig(id, draft.version, risky ? confirmText : undefined);
      setDraft(d);
      setActive(d);
      setDiff([]);
      flash(setMsg, `Applied v${d.version}`);
    } catch (e) { setErr(e instanceof Error ? e.message : "failed"); }
  }

  async function requestApproval() {
    if (!draft) return;
    try {
      const d = await api.requestApproval(id, draft.version);
      setDraft(d);
      flash(setMsg, "Approval requested");
    } catch (e) { setErr(e instanceof Error ? e.message : "failed"); }
  }

  return (
    <>
      <h1>Configuration</h1>
      <p style={{ color: "#64748b", fontSize: 14 }}>
        Workflow: <b>Draft → Validate → (Approve) → Apply</b>. Active config is immutable; every change creates a new version.
      </p>
      {active && (
        <p style={{ fontSize: 13 }}>
          Active: <b>v{active.version}</b> · applied {active.applied_at_ms && new Date(active.applied_at_ms).toLocaleString()}
        </p>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <section className="card">
          <h2 style={{ marginTop: 0 }}>Strategy</h2>
          <label>Strategy</label>
          {strategies.length > 0 ? (
            <select value={cfg.strategy.strategy_id}
              onChange={(e) => onStrategyChange(e.target.value)}
              style={{ width: "100%" }}>
              {strategies.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          ) : (
            <input value={cfg.strategy.strategy_id}
              onChange={(e) => onStrategyChange(e.target.value)}
              style={{ width: "100%" }} />
          )}
          <label>Parameters (JSON)</label>
          <textarea
            value={JSON.stringify(cfg.strategy.params, null, 2)}
            onChange={(e) => {
              try { setCfg({ ...cfg, strategy: { ...cfg.strategy, params: JSON.parse(e.target.value) } }); }
              catch { /* ignore until valid */ }
            }}
            rows={5} style={{ width: "100%", fontFamily: "ui-monospace, Menlo, monospace" }}
          />
          {paramSchema && (
            <p style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>
              Allowed keys: <code>{Object.keys(paramSchema).join(", ")}</code>. Use <button
                type="button"
                style={{ background: "none", border: "none", color: "#3b82f6", cursor: "pointer", padding: 0, fontSize: 12 }}
                onClick={() => setCfg({ ...cfg, strategy: { ...cfg.strategy, params: { ...paramSchema } } })}
              >restore defaults</button> to reset.
            </p>
          )}
          <label>Symbols</label>
          <SymbolPicker
            selected={cfg.symbols}
            onChange={(syms) => setCfg({ ...cfg, symbols: syms })}
            namespace={cfg.broker.symbol_namespace}
          />
        </section>

        <section className="card">
          <h2 style={{ marginTop: 0 }}>Risk limits</h2>
          <div className="form-row">
            <div>
              <label>Max position notional (USD)</label>
              <input type="number" min={1} value={cfg.risk.max_position_notional}
                onChange={(e) => setCfg({ ...cfg, risk: { ...cfg.risk, max_position_notional: Number(e.target.value) } })}
                style={{ width: "100%" }} />
            </div>
            <div>
              <label>Max total exposure (USD)</label>
              <input type="number" min={1} value={cfg.risk.max_total_exposure}
                onChange={(e) => setCfg({ ...cfg, risk: { ...cfg.risk, max_total_exposure: Number(e.target.value) } })}
                style={{ width: "100%" }} />
            </div>
            <div>
              <label>Max daily loss (USD)</label>
              <input type="number" min={1} value={cfg.risk.max_daily_loss}
                onChange={(e) => setCfg({ ...cfg, risk: { ...cfg.risk, max_daily_loss: Number(e.target.value) } })}
                style={{ width: "100%" }} />
            </div>
            <div>
              <label>Max drawdown (%)</label>
              <input type="number" min={0.1} max={100} step="0.1" value={cfg.risk.max_drawdown_pct}
                onChange={(e) => setCfg({ ...cfg, risk: { ...cfg.risk, max_drawdown_pct: Number(e.target.value) } })}
                style={{ width: "100%" }} />
            </div>
            <div>
              <label>Max open orders</label>
              <input type="number" min={1} value={cfg.risk.max_open_orders}
                onChange={(e) => setCfg({ ...cfg, risk: { ...cfg.risk, max_open_orders: Number(e.target.value) } })}
                style={{ width: "100%" }} />
            </div>
            <div>
              <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 18 }}>
                <input type="checkbox" checked={cfg.risk.kill_switch}
                  onChange={(e) => setCfg({ ...cfg, risk: { ...cfg.risk, kill_switch: e.target.checked } })} />
                Kill switch engaged
              </label>
            </div>
          </div>
        </section>

        <section className="card" style={{ gridColumn: "1 / 3" }}>
          <h2 style={{ marginTop: 0 }}>Broker / adapter</h2>
          <div className="form-row">
            <div>
              <label>Adapter</label>
              <select value={cfg.broker.type}
                onChange={(e) => {
                  const type = e.target.value;
                  const environment = type === "paper" ? "paper" : "demo";
                  const symbol_namespace = type === "paper" ? "paper" : "deriv";
                  const credential_ref = type === "paper" ? "secret://paper/none" : cfg.broker.credential_ref;
                  setCfg({
                    ...cfg,
                    broker: {
                      ...cfg.broker,
                      type,
                      environment,
                      symbol_namespace,
                      credential_ref
                    }
                  });
                }}
                style={{ width: "100%" }}>
                {adapters.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
            <div>
              <label>Environment</label>
              <select value={cfg.broker.environment}
                onChange={(e) => setCfg({ ...cfg, broker: { ...cfg.broker, environment: e.target.value } })}
                style={{ width: "100%" }}>
                {cfg.broker.type === "paper" ? (
                  <option value="paper">paper</option>
                ) : (
                  <>
                    <option value="demo">demo</option>
                    <option value="live" disabled>live (restricted)</option>
                  </>
                )}
              </select>
            </div>
            <div>
              <label>Account ID</label>
              <input value={cfg.broker.account_id}
                onChange={(e) => setCfg({ ...cfg, broker: { ...cfg.broker, account_id: e.target.value } })}
                style={{ width: "100%" }} />
            </div>
            <div>
              <label>Credential reference</label>
              <input value={cfg.broker.credential_ref}
                onChange={(e) => setCfg({ ...cfg, broker: { ...cfg.broker, credential_ref: e.target.value } })}
                placeholder="secret://..." style={{ width: "100%" }}
                readOnly={cfg.broker.type === "paper"} />
              <p style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>
                {cfg.broker.type === "paper" 
                  ? "Not required for paper trading." 
                  : "Inline secrets are rejected. Store secrets in backend secrets store."}
              </p>
            </div>
            <div>
              <label>Symbol namespace</label>
              <select value={cfg.broker.symbol_namespace}
                onChange={(e) => setCfg({ ...cfg, broker: { ...cfg.broker, symbol_namespace: e.target.value } })}
                style={{ width: "100%" }}>
                <option value="paper">paper</option>
                <option value="deriv">deriv</option>
              </select>
            </div>
          </div>
        </section>
      </div>

      <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
        {can(user?.role, "config:draft") && (
          <button className="btn" onClick={saveDraft}>1. Save draft</button>
        )}
        <button className="btn secondary" onClick={validate} disabled={!draft}>2. Validate</button>
        {can(user?.role, "config:draft") && (
          <button className="btn secondary" onClick={requestApproval} disabled={!draft || draft.status !== "validated"}>
            Request approval
          </button>
        )}
        {can(user?.role, "config:apply") && (
          <button className="btn" onClick={apply} disabled={!draft || draft.validation_errors.length > 0}>
            3. Apply
          </button>
        )}
      </div>

      {err && <p className="error" style={{ marginTop: 12 }}>{err}</p>}
      {msg && <p style={{ color: "#065f46", marginTop: 12 }}>{msg}</p>}

      {draft && (
        <div className="card" style={{ marginTop: 20 }}>
          <h2 style={{ marginTop: 0 }}>
            Draft #{draft.version} <span className={`pill ${draft.status}`} style={{ marginLeft: 8 }}>{draft.status}</span>
          </h2>
          {draft.validation_errors.length > 0 && (
            <div className="error">
              <b>Errors:</b>
              <ul>{draft.validation_errors.map((x, i) => <li key={i}>{x}</li>)}</ul>
            </div>
          )}
          {draft.validation_warnings.length > 0 && (
            <div style={{ color: "#92400e" }}>
              <b>Warnings:</b>
              <ul>{draft.validation_warnings.map((x, i) => <li key={i}>{x}</li>)}</ul>
            </div>
          )}
          <h3>Diff vs active</h3>
          <ConfigDiff changes={diff} />
          {risky && (
            <div style={{ marginTop: 12, padding: 12, background: "#fee2e2", borderRadius: 8 }}>
              <b>This change affects risk / broker / strategy.</b> Reviewer approval is recommended.
              If you proceed without approval, type <code>APPLY RISK CHANGE</code> to confirm:
              <input
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                style={{ marginTop: 8, width: "100%" }}
                placeholder="APPLY RISK CHANGE"
              />
            </div>
          )}
        </div>
      )}
    </>
  );
}

const PAPER_SYMBOLS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "USD/CHF", "NZD/USD", "EUR/GBP"];
const DERIV_SYMBOLS = [
  "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "USD/CHF",
  "V10/USD", "V25/USD", "V50/USD", "V75/USD", "V100/USD",
  "BOOM1000/USD", "BOOM500/USD", "CRASH1000/USD", "CRASH500/USD",
];

function SymbolPicker({ selected, onChange, namespace }: {
  selected: string[];
  onChange: (s: string[]) => void;
  namespace: string;
}) {
  const [custom, setCustom] = useState("");
  const presets = namespace === "paper" ? PAPER_SYMBOLS : namespace === "deriv" ? DERIV_SYMBOLS : [];

  function toggle(sym: string) {
    if (selected.includes(sym)) onChange(selected.filter((s) => s !== sym));
    else onChange([...selected, sym]);
  }

  function addCustom() {
    const sym = custom.trim().toUpperCase();
    if (sym && !selected.includes(sym)) onChange([...selected, sym]);
    setCustom("");
  }

  return (
    <div>
      {presets.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
          {presets.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => toggle(s)}
              style={{
                padding: "3px 10px", borderRadius: 12, fontSize: 12, cursor: "pointer",
                border: selected.includes(s) ? "2px solid #3b82f6" : "1px solid #cbd5e1",
                background: selected.includes(s) ? "#eff6ff" : "#fff",
                color: selected.includes(s) ? "#1d4ed8" : "#334155",
                fontWeight: selected.includes(s) ? 600 : 400,
              }}
            >
              {s}
            </button>
          ))}
        </div>
      )}
      <div style={{ display: "flex", gap: 6 }}>
        <input
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addCustom())}
          placeholder="Add symbol (e.g. EUR/USD)"
          style={{ flex: 1 }}
        />
        <button type="button" className="btn secondary" style={{ fontSize: 12 }} onClick={addCustom}>Add</button>
      </div>
      {selected.filter((s) => !presets.includes(s)).length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
          {selected.filter((s) => !presets.includes(s)).map((s) => (
            <span key={s} style={{
              display: "inline-flex", alignItems: "center", gap: 4,
              padding: "3px 8px", borderRadius: 12, fontSize: 12,
              background: "#eff6ff", border: "2px solid #3b82f6", color: "#1d4ed8",
            }}>
              {s}
              <button type="button" onClick={() => onChange(selected.filter((x) => x !== s))}
                style={{ background: "none", border: "none", cursor: "pointer", padding: 0, lineHeight: 1, color: "#3b82f6" }}>×</button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
