# Real-Edge Gaps — What's Built vs What's Missing

This document is an **honest accounting** of where Brindle stands as a research
platform versus what would be required to actually source profitable trading
edge. Read it before considering live or even demo deployment with real money.

## What this iteration delivered

| Component | Status | Notes |
|-----------|--------|-------|
| Walk-forward 2.0 harness | ✅ Built | k-fold rolling windows, pooled z-score, per-fold consistency check |
| Regime-filtered strategy (`regime_v1`) | ✅ Built | ADX-gated trend follower — only trades when market is trending |
| Force-paper hard mode | ✅ Built | `FORCE_PAPER_ONLY=true` env flag silently reroutes all bots through paper adapter |
| Paginated Deriv historical fetch | ✅ Built | Walks backwards through `ticks_history` for >1000-bar samples |
| Honest verdict criteria | ✅ Built | Returns `EDGE` / `NO_EDGE` / `INSUFFICIENT_DATA` based on stats, not vibes |

## What's still missing for real edge

These are the gaps between "research platform" and "actually profitable
trading system." None of these can be hand-waved.

### 1. News event windows
**Status:** Not implemented — requires external data feed.

**What it needs:**
- A news API subscription (Bloomberg, Reuters, NewsAPI, ForexFactory) — typically $20-$2000/mo
- A scheduled-event database (FOMC, NFP, ECB, BoE, etc.) updated daily
- An event impact classifier (high / medium / low) — manual or NLP-based
- Strategy logic that opens/closes positions in pre/post-event windows
- Backtests showing event-time trades have positive expectancy net of slippage

**Why it matters:** Forex moves are concentrated around scheduled news. A
strategy that simply *avoids* the 5 minutes around high-impact news already
removes a major source of variance loss. Profiting *from* news requires
faster execution than retail brokers offer; profiting from *post-news drift*
is more achievable.

### 2. Order-flow imbalances
**Status:** Not possible on Deriv — they don't expose Level-2 order book.

**What it needs:**
- A broker that publishes Level-2 / Level-3 market data:
  - Interactive Brokers (TWS API, includes L2)
  - LMAX Exchange
  - direct exchange feeds (CME for futures)
- Real-time order book reconstruction
- Imbalance metrics (bid stack vs ask stack volume, queue position)
- Latency-sensitive execution (sub-second to act on imbalances)

**Why it matters:** Order-flow imbalances are one of the most consistently
documented sources of microstructure alpha in academic literature. They are
also the hardest to act on — by the time a retail trader sees an imbalance,
HFT has already responded.

### 3. Cross-asset signals
**Status:** Partially possible — Deriv exposes multiple symbols, but limited.

**What it needs:**
- Multi-feed market data ingestion (currently single-symbol per bot)
- Correlation calculation across symbols (currency basket vs DXY, gold vs USD, etc.)
- Strategy logic conditioned on cross-asset state (e.g., "trade EUR/USD long only when DXY is falling")
- Synchronized data feeds across instruments (timestamp alignment)

**What's blocking it:**
- Deriv's API focuses on single-asset binary options
- Real macro signals (DXY, VIX, US10Y yield) require a multi-asset broker
  or separate market data subscription (Polygon.io, Alpaca, IEX Cloud)

### 4. Alternative data
**Status:** Not implemented — requires per-source integration commitment.

**Examples and what each needs:**
- **Crypto whale-watching:** on-chain analytics API (Glassnode $100-1000/mo, Nansen)
- **Sentiment:** Twitter/X API (paid tier), StockTwits API
- **Satellite:** SpaceKnow, Orbital Insight (enterprise pricing)
- **Earnings call NLP:** Transcript provider + LLM analysis

Each is a multi-week integration. None will be added without a specific
hypothesis about what edge they unlock.

## What the empirical evidence shows so far

From rigorous walk-forward testing on real Deriv data:

| Strategy | Instrument | Verdict |
|----------|-----------|---------|
| `trend_v1` | V75/USD | NO_EDGE — V75 is a synthetic random walk |
| `bollinger_v1` | V75/USD | NO_EDGE — same random walk problem |
| `macd_v1` | V75/USD | NO_EDGE — same random walk problem |
| `trend_v1` | EUR/USD | INSUFFICIENT_DATA — filter blocks all signals on tick-data scale |
| `bollinger_v1` | EUR/USD | ≈ coin flip (46.2% on 40 trades) |
| `macd_v1` | EUR/USD | ≈ coin flip (48.1% on 109 trades) |
| `regime_v1` | EUR/USD | INSUFFICIENT_DATA — needs more history to evaluate |

**Bottom line:** No strategy in the registry has proven out-of-sample edge
on either V75 or EUR/USD. The platform's primary current value is *as a
research environment* — not as a trading system.

## Recommended next steps (in order)

1. **Stay in `FORCE_PAPER_ONLY=true` mode** until something passes walk-forward.
2. **Source one specific edge hypothesis** — e.g., "trade EUR/USD post-NFP drift," "trade volatility breakout after >2σ moves," "trade BTC mean reversion after Asian session liquidations."
3. **Build a custom strategy** in `app/strategies/user/` implementing that hypothesis.
4. **Run it through `walk_forward()`** with at least 5000 bars of history and 4+ folds.
5. **Verdict must be `EDGE`** with z > 1.96 and consistent across folds.
6. **Then paper-trade for 4+ weeks** with `FORCE_PAPER_ONLY=true`.
7. **Then drop to real Deriv demo** with small stakes.
8. **Real money? Only after months of demo profitability.**

There are no shortcuts. Anyone telling you otherwise is selling something.
