"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import ConfigDiff from "@/components/ConfigDiff";
import Navigation from "@/components/Navigation";
import { api, getUser } from "@/lib/api";
import { can } from "@/lib/rbac";
import type { Bot, BotConfig, ConfigVersion, DiffEntry } from "@/lib/types";

const DEFAULT_CONFIG = (botId: string, allocation: number): BotConfig => {
  const alloc = allocation || 100;
  return {
    bot_id: botId,
    version: 1,
    name: "new-config",
    description: "",
    strategy: {
      strategy_id: "trend_v1",
      params: { fast: 5, slow: 20, min_cross_pct: 0.02, cooldown_ticks: 10 },
    },
    risk: {
      max_position_notional: alloc,
      max_total_exposure: alloc * 5,
      max_daily_loss: Math.max(20, alloc * 0.3),
      max_drawdown_pct: 25,
      max_open_orders: 5,
      max_consecutive_losses: 0,
      risk_per_trade_pct: 10,
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
  };
};

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
  const [bot, setBot] = useState<Bot | null>(null);
  const [cfg, setCfg] = useState<BotConfig>(() => DEFAULT_CONFIG(id, 100));
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
        const [a, s, ac, b] = await Promise.all([
          api.listAdapters(id),
          api.listStrategies(id),
          api.activeConfig(id),
          api.getBot(id)
        ]);
        setAdapters(a);
        setStrategies(s);
        setActive(ac);
        setBot(b);
        if (ac) {
          setCfg({ ...ac.config, bot_id: id });
        } else if (b) {
          setCfg(DEFAULT_CONFIG(id, b.allocation ?? 100));
        }
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
          <label>Strategy <FieldHelp text="The trading algorithm this bot will run. Each strategy has a different approach — trend-following, mean reversion, breakout, etc. Changing this resets the parameters to the new strategy's defaults." /></label>
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
          <label>Parameters (JSON) <FieldHelp text="Fine-tuning knobs for the strategy — things like how many bars to look back, how aggressively to size trades, or how long to wait between trades. Use 'restore defaults' if you're unsure what to set." /></label>
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
          <label>Symbols <FieldHelp text="The markets this bot will trade. V75/USD is Deriv's Volatility 75 index — it moves 24/7. EUR/USD is the euro-dollar forex pair. You can pick multiple, and the bot will trade each one." /></label>
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
              <label>Max position notional (USD) <FieldHelp text="The most money that can be tied up in a single trade at once. If a trade would cost $150 but this is set to $100, the trade is blocked. Set it at least as large as your typical trade size." /></label>
              <input type="number" min={1} value={cfg.risk.max_position_notional}
                onChange={(e) => setCfg({ ...cfg, risk: { ...cfg.risk, max_position_notional: Number(e.target.value) } })}
                style={{ width: "100%" }} />
              {bot && <p style={{ fontSize: 10, margin: "4px 0 0 0", opacity: 0.6 }}>Recommended: ≥ ${bot.allocation ?? 100}</p>}
            </div>
            <div>
              <label>Max total exposure (USD) <FieldHelp text="The maximum total value of all open trades combined. If you have 3 trades open at $50 each, that's $150 total. Must be at least as large as max position notional." /></label>
              <input type="number" min={1} value={cfg.risk.max_total_exposure}
                onChange={(e) => setCfg({ ...cfg, risk: { ...cfg.risk, max_total_exposure: Number(e.target.value) } })}
                style={{ width: "100%" }} />
              {bot && <p style={{ fontSize: 10, margin: "4px 0 0 0", opacity: 0.6 }}>Recommended: ≥ ${(bot.allocation ?? 100) * 2}</p>}
            </div>
            <div>
              <label>Max daily loss (USD) <FieldHelp text="If the bot loses this much in a single day, it stops automatically. A safety net to prevent a bad day from wiping out too much. Example: set to $30 on a $100 account to limit daily losses to 30%." /></label>
              <input type="number" min={1} value={cfg.risk.max_daily_loss}
                onChange={(e) => setCfg({ ...cfg, risk: { ...cfg.risk, max_daily_loss: Number(e.target.value) } })}
                style={{ width: "100%" }} />
              {bot && <p style={{ fontSize: 10, margin: "4px 0 0 0", opacity: 0.6 }}>Recommended: ≥ ${Math.round((bot.allocation ?? 100) * 0.3)}</p>}
            </div>
            <div>
              <label>Max drawdown (%) <FieldHelp text="If the bot's balance drops this far below its starting point, it pauses. Example: 25% on a $100 balance means it stops if balance falls to $75. Set to 100 to let it trade until the allocation is fully depleted." /></label>
              <input type="number" min={0.1} max={100} step="0.1" value={cfg.risk.max_drawdown_pct}
                onChange={(e) => setCfg({ ...cfg, risk: { ...cfg.risk, max_drawdown_pct: Number(e.target.value) } })}
                style={{ width: "100%" }} />
            </div>
            <div>
              <label>Max open orders <FieldHelp text="How many trades can be active at the same time. Most strategies work well with 1–5. Higher values mean more simultaneous exposure. The bot won't open a new trade if this limit is already reached." /></label>
              <input type="number" min={1} value={cfg.risk.max_open_orders}
                onChange={(e) => setCfg({ ...cfg, risk: { ...cfg.risk, max_open_orders: Number(e.target.value) } })}
                style={{ width: "100%" }} />
            </div>
            <div>
              <label>Max consecutive losses <FieldHelp text="If the bot loses this many trades in a row, it pauses automatically. Catches strategies that are clearly misfiring before more damage is done. Set to 0 to disable this check." /></label>
              <input type="number" min={0} value={cfg.risk.max_consecutive_losses}
                onChange={(e) => setCfg({ ...cfg, risk: { ...cfg.risk, max_consecutive_losses: Number(e.target.value) } })}
                style={{ width: "100%" }} />
            </div>
            <div>
              <label>Risk per trade (%) <FieldHelp text="Size each trade as a percentage of your current balance instead of a fixed amount. Example: 10% on a $100 balance = $10 per trade. As your balance grows or shrinks, so does the trade size. Leave blank to use the fixed qty from the strategy parameters." /></label>
              <input type="number" min={0} max={100} step="0.1" value={cfg.risk.risk_per_trade_pct || ""}
                onChange={(e) => setCfg({ ...cfg, risk: { ...cfg.risk, risk_per_trade_pct: e.target.value ? Number(e.target.value) : null } })}
                style={{ width: "100%" }} placeholder="Fixed qty if empty" />
            </div>
            <div>
              <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 18 }}>
                <input type="checkbox" checked={cfg.risk.kill_switch}
                  onChange={(e) => setCfg({ ...cfg, risk: { ...cfg.risk, kill_switch: e.target.checked } })} />
                Kill switch engaged
                <FieldHelp text="Emergency stop. When checked, the bot will not place any new trades regardless of market signals. Use this if something looks wrong and you need to halt immediately without stopping the bot entirely." />
              </label>
            </div>
          </div>
        </section>

        <section className="card" style={{ gridColumn: "1 / 3" }}>
          <h2 style={{ marginTop: 0 }}>Broker / adapter</h2>
          <div className="form-row">
            <div>
              <label>Adapter <FieldHelp text="Which broker connection to use. 'deriv' connects to your real Deriv account (demo or live). 'paper' is a fully local simulation with no broker connection — good for testing strategies without any real money or API key." /></label>
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
              <label>Environment <FieldHelp text="'demo' uses your Deriv demo account — pretend money, real market data, great for testing. 'live' uses your real-money account and is currently restricted on this platform." /></label>
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
              <label>Account ID <FieldHelp text="Your Deriv account number — looks like DOT91022417 or CR123456. Find it in your Deriv dashboard under account settings. Leave blank when using the paper adapter." /></label>
              <input value={cfg.broker.account_id}
                onChange={(e) => setCfg({ ...cfg, broker: { ...cfg.broker, account_id: e.target.value } })}
                style={{ width: "100%" }} />
            </div>
            <div>
              <label>Credential reference <FieldHelp text="A pointer to your Deriv API token stored securely in the backend — don't paste your actual token here. Use the format 'secret://env/DERIV_API_TOKEN'. Ask your admin if you're unsure what value to use." /></label>
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
              <label>Symbol namespace <FieldHelp text="Tells the bot which set of market symbols to use. 'deriv' for real Deriv markets (Volatility indices, forex pairs). 'paper' for simulated symbols used in paper trading mode. This is set automatically when you change the adapter." /></label>
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
          <SanityCheckBanner config={cfg} diff={diff} />
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

function FieldHelp({ text }: { text: string }) {
  const [show, setShow] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  return (
    <span style={{ position: "relative", display: "inline-flex", alignItems: "center" }}>
      <span
        ref={ref}
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        style={{ cursor: "help", color: "#94a3b8", fontSize: 13, marginLeft: 5, lineHeight: 1, userSelect: "none" }}
        aria-label={text}
      >ⓘ</span>
      {show && (
        <span style={{
          position: "absolute",
          bottom: "calc(100% + 6px)",
          left: "50%",
          transform: "translateX(-50%)",
          background: "#1e293b",
          color: "#f1f5f9",
          padding: "8px 12px",
          borderRadius: 6,
          fontSize: 12,
          lineHeight: 1.55,
          width: 240,
          zIndex: 1000,
          boxShadow: "0 4px 16px rgba(0,0,0,0.25)",
          pointerEvents: "none",
          whiteSpace: "normal",
        }}>
          {text}
        </span>
      )}
    </span>
  );
}

function SanityCheckBanner({ config, diff }: { config: BotConfig; diff: DiffEntry[] }) {
  const [data, setData] = useState<Awaited<ReturnType<typeof api.configSanityCheck>> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Auto-clear when the diff changes (re-validation)
  useEffect(() => { setData(null); setErr(null); }, [diff]);

  async function review() {
    setErr(null); setLoading(true);
    try { setData(await api.configSanityCheck(config, diff)); }
    catch (e) { setErr(e instanceof Error ? e.message : "failed"); }
    finally { setLoading(false); }
  }

  if (diff.length === 0) return null;

  return (
    <div style={{ marginTop: 12, padding: 12, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ fontWeight: 700 }}>✨ AI sanity check</div>
        <button className="btn ghost" disabled={loading} onClick={review} style={{ fontSize: 12, padding: "3px 8px" }}>
          {loading ? "Reviewing…" : data ? "Re-review" : "Review before apply"}
        </button>
      </div>
      {err && <div style={{ color: "#cc2626", fontSize: 12 }}>{err}</div>}
      {!data && !err && !loading && (
        <div style={{ fontSize: 12, color: "#64748b" }}>
          Optional. Asks Groq to flag obvious foot-guns in this config diff (e.g. <code>kill_switch</code> turned off,
          drawdown limit too loose). Advisory only — the typed-confirmation gate below is still the hard guard.
        </div>
      )}
      {data && (
        <div>
          {data.summary && (
            <div style={{ fontSize: 13, marginBottom: 8 }}><b>Summary:</b> {data.summary}</div>
          )}
          {data.warnings.length === 0 ? (
            <div style={{ fontSize: 13, color: "#008265" }}>✓ No issues detected.</div>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13 }}>
              {data.warnings.map((w, i) => (
                <li key={i} style={{
                  marginBottom: 4,
                  color: w.severity === "critical" ? "#cc2626" : w.severity === "warning" ? "#b37600" : "#555",
                }}>
                  <b>[{w.severity}]</b> <code>{w.field}</code> — {w.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
