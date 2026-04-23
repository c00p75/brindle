# GO_LIVE_CHECKLIST.md

## 🚀 Go-Live Checklist (Real Money Trading)

> You are only ready for live trading when **ALL sections pass**.  
> If any item fails → **DO NOT GO LIVE**

---

## 🧠 1. Strategy Validation (Non-Negotiable)

### Minimum requirements per strategy:

- [ ] ≥ 200 trades **OR** ≥ 90 days equivalent runtime
- [ ] Net profit **after fees + slippage**
- [ ] Profit factor ≥ **1.15**
- [ ] Sharpe ratio ≥ **0.8**
- [ ] Max drawdown ≤ **8–10%**
- [ ] No single period contributes > 60% of profits
- [ ] Works across ≥ 2 market regimes (trend + range)

### Stability checks:

- [ ] No parameter overfitting (validated via walk-forward)
- [ ] Strategy behaves consistently across different datasets
- [ ] No unexplained performance spikes

---

## 🧪 2. Paper Trading Soak Test

- [ ] ≥ 30–90 consecutive days running
- [ ] No crashes or restarts required
- [ ] No memory leaks or performance degradation
- [ ] Stable PnL behavior

### Critical:

- [ ] **Zero unresolved errors**
- [ ] **Zero unknown order states**
- [ ] **Zero reconciliation failures**

---

## ⚙️ 3. Execution System Validation

### OMS (Order Management System)

- [ ] Correct order state transitions
- [ ] Partial fills handled correctly
- [ ] Idempotency works (no duplicate orders)
- [ ] Retry logic tested

### Fill realism:

- [ ] Slippage model realistic
- [ ] Fees correctly applied
- [ ] Large order behavior tested

---

## 📊 4. Data Pipeline Integrity

- [ ] Symbol normalization correct
- [ ] Data validation blocks bad data
- [ ] Staleness detection works → NOOP
- [ ] Time synchronization verified

---

## 🛡️ 5. Risk System

- [ ] Position size limits enforced
- [ ] Exposure limits enforced
- [ ] Drawdown controls working
- [ ] Daily loss limits enforced
- [ ] Kill switch works (manual + automatic)

---

## 🔁 6. Reconciliation & Ledger Accuracy

- [ ] Ledger matches positions
- [ ] Balance snapshots consistent
- [ ] PnL reproducible
- [ ] Reconciliation job runs automatically

---

## 🧩 7. Broker Adapter Readiness

- [ ] Tested on demo account
- [ ] Auth/session stable
- [ ] Reconnect logic tested
- [ ] Symbol mapping correct
- [ ] Precision/lot sizes correct

---

## 🖥️ 8. Config & Governance

- [ ] Configs are versioned
- [ ] Validation enforced
- [ ] Rollback works
- [ ] Audit logs present

---

## 🔔 9. Observability & Alerts

- [ ] Structured logging
- [ ] Alerts working (Telegram/email)
- [ ] Dashboard shows key metrics

---

## 🧪 10. Testing Coverage

- [ ] Unit tests complete
- [ ] Integration tests complete
- [ ] Replay tests deterministic
- [ ] No network calls in tests

---

## 🧾 11. Incident Readiness

- [ ] Incident levels defined
- [ ] Runbook exists
- [ ] Can pause all bots instantly

---

## 💰 12. Capital Deployment Plan

- [ ] Start with 1–5% capital
- [ ] Single bot + strategy
- [ ] Scale gradually

---

## ⚠️ 13. Live Trading Safety Mode

- [ ] Demo tested first
- [ ] Micro-capital live start
- [ ] Extra logging enabled
- [ ] Lower risk limits

---

## ❌ HARD STOP CONDITIONS

DO NOT GO LIVE IF:

- [ ] Strategy not validated
- [ ] Paper trading < 30 days
- [ ] Reconciliation issues exist
- [ ] Risk system incomplete
- [ ] No kill switch
- [ ] No alerting
- [ ] No audit trail

---

## 🧠 Final Rule

> If you wouldn’t trust the system unattended with fake money,  
> you should not trust it with real money.

---

## 🚀 After Passing

1. Connect broker (demo first)
2. Deploy with micro capital
3. Monitor closely
4. Scale slowly
