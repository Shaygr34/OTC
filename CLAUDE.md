# CLAUDE.md — ATM Trading Engine

## Identity

You are the lead engineer on an OTC penny stock market-making engine. The system implements the "ATM Pattern" — buying at the Bid during buyer/seller imbalances and selling at the Ask on Pink Sheet/Grey Market stocks priced $0.0001–$0.03.

You operate with full technical autonomy. Challenge assumptions. Flag risks. Propose better approaches when you see them. Do not over-explain basics or pad responses.

---

## Project Owner Context

The owner is a systems-level thinker and project architect, not a beginner. They understand the strategy deeply and have produced the full system specification and research. Communicate as a senior engineering peer. Be direct, precise, and concise.

---

## Current Phase: v0.5 — Product Polish (v0 engine complete)

v0 engine is **complete** — all 9 analysis/infrastructure modules built and tested (312 engine tests).
v0.5 focuses on the **product layer** — making it a daily-driver tool for Eldar. V1 dashboard deployed (Phase 11): Settings, Wizard, Watchlist management, Trade Logger, Hebrew/RTL. Eldar running locally as of 2026-03-17.

The system does NOT make entry decisions or execute trades. The human trades manually based on the system's output.

### v0 Modules to Build

1. **Scanner** — filters OTC universe by price, stability, volume
2. **L2 Analyzer** — imbalance ratio, MM classification, wall detection, refresh detection
3. **Volume Analyzer** — modified z-score, RVOL, anomaly flagging
4. **Dilution Sentinel** — composite score, bad MM hard reject, volume/price divergence
5. **T&S Analyzer** — bid vs ask classifier, block trade detector, cross trade patterns
6. **ATM Probability Scorer** — composite score from all modules
7. **Alert System** — Telegram/Discord on anomalies
8. **Logging** — every event persisted to SQLite
9. **Risk Module** — position sizing rules, OHI market health gate, hold time enforcement

### v0 Does NOT Include

- Order execution (manual only)
- Backtesting engine (v1+)
- Polygon.io integration (IBKR data only to minimize cost)

---

## Tech Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| Language | Python 3.12+ | Only viable option for IBKR + OTC |
| Broker API | `ib_async` (successor to `ib_insync`) | IBKR is the only broker with OTC L2 + MPID via API |
| Database | SQLite (dev) → TimescaleDB (prod) | Zero setup for v0, migration path clear |
| Config | Pydantic v2 + `python-dotenv` | Type-safe settings, env separation |
| Logging | `structlog` | Structured JSON logs |
| Alerts | `python-telegram-bot` v21+ | Free, async, reliable |
| Monitoring | `prometheus-client` | Metrics endpoint for future Grafana |
| Arithmetic | `decimal.Decimal` everywhere | **NEVER use float for prices or shares** |
| Async | `asyncio` event bus (no external deps) | Single-process, no Redis/Kafka for v0 |
| Linting | `ruff` | Replaces black + flake8 + isort |
| Testing | `pytest` + `pytest-asyncio` | Async-native tests |

### Critical: Decimal Arithmetic

Sub-penny prices break with floating point. Every price, share count, and financial calculation MUST use `decimal.Decimal`. Never `float`.

```python
from decimal import Decimal
price = Decimal("0.0001")  # correct
price = 0.0001             # WRONG — floating point
```

---

## Architecture: Event-Driven Monolith

Single Python process using asyncio with internal pub/sub event bus. No microservices, no external message brokers.

```
[IBKR TWS API] ──→ [Event Bus] ──→ [Scanner]
                               ──→ [L2 Analyzer]     ──→ [Rule Engine] ──→ [Alert Manager]
                               ──→ [Volume Analyzer]                   ──→ [Database]
                               ──→ [T&S Analyzer]                      ──→ [Risk Module]
                               ──→ [Dilution Sentinel]
```

### Event Types

- `MarketDataEvent` — raw L2/T&S data from IBKR
- `ScannerHitEvent` — stock passes initial filters
- `AnalysisCompleteEvent` — all modules scored a candidate
- `AlertEvent` — threshold breached, needs attention
- `DilutionAlertEvent` — dilution detected, critical priority

### Event Bus

Lightweight `collections.defaultdict` mapping event types to async handler callbacks. No external deps.

```python
class EventBus:
    def __init__(self):
        self._handlers = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable):
        self._handlers[event_type].append(handler)

    async def publish(self, event):
        for handler in self._handlers[type(event)]:
            await handler(event)
```

---

## Project Structure

```
atm-trading-engine/
├── CLAUDE.md                # This file
├── config/
│   ├── settings.py          # Pydantic settings (reads .env)
│   ├── constants.py         # Price tiers, thresholds, MM lists
│   ├── rules.yaml           # Rule engine configuration
│   ├── i18n.py              # Hebrew/English string mappings + t() helper
│   ├── user_config.py       # JSON config persistence (data/user_config.json)
│   └── watchlist.yaml       # User-populated symbol list (unused when managing via UI)
├── src/
│   ├── core/
│   │   ├── events.py        # Event dataclasses
│   │   ├── event_bus.py     # Pub/sub bus
│   │   └── models.py        # Shared domain models
│   ├── scanner/
│   │   ├── screener.py      # Price/volume/stability filters
│   │   ├── stability.py     # CV, NATR, TRR, Bollinger calculations
│   │   └── watchlist.py     # YAML watchlist loader
│   ├── analysis/
│   │   ├── level2.py        # L2 imbalance, wall detection, refresh FSM
│   │   ├── volume.py        # Z-score, RVOL, anomaly detection
│   │   ├── time_sales.py    # Bid/ask classifier, block/cross detection
│   │   └── dilution.py      # Composite dilution score (0-10)
│   ├── rules/
│   │   └── engine.py        # YAML-driven rule engine
│   ├── alerts/
│   │   ├── dispatcher.py    # Priority routing
│   │   └── telegram.py      # Telegram bot integration
│   ├── risk/
│   │   ├── position.py      # Position sizing, exposure limits
│   │   ├── market_health.py # OTC Health Index (OHI)
│   │   └── stops.py         # Time-based, L2-collapse, dilution stops
│   ├── broker/
│   │   ├── adapter.py       # Abstract BrokerAdapter interface
│   │   ├── ibkr.py          # IBAdapter using ib_async
│   │   ├── mock.py          # MockAdapter for testing
│   │   └── history.py       # HistoryLoader for seeding bar data
│   ├── database/
│   │   ├── schema.py        # SQLAlchemy models (6 tables)
│   │   ├── repository.py    # Async CRUD operations
│   │   └── persistence.py   # PersistenceSubscriber (event→DB routing)
│   └── dashboard/
│       └── app.py           # Streamlit dashboard (V1 — 4 tabs, wizard, Hebrew/RTL)
├── tests/                   # 16 test files, 327 tests
├── scripts/
│   ├── run_system.py        # Main engine entry point
│   ├── run_dashboard.py     # Dashboard launcher
│   ├── seed_realistic.py    # Demo data seeder (20 candidates, 7-day history)
│   └── seed_demo_data.py    # Simple demo data seeder
├── data/
│   ├── atm.db               # SQLite database (gitignored)
│   └── user_config.json     # User overrides (gitignored)
├── logs/
├── .env                     # Environment variables (gitignored)
├── .env.example             # Template for .env
├── .gitignore
├── setup.sh                 # One-command bootstrap
├── start.sh                 # Launch engine + dashboard
├── requirements.txt
├── pyproject.toml
└── ruff.toml
```

---

## Formalized Rules and Thresholds

### Price Tiers

| Tier | Range | Name | Notes |
|------|-------|------|-------|
| TRIP_ZERO | $0.0001–$0.0005 | Low Trips | Very low liquidity |
| TRIPS | $0.0001–$0.0009 | Trips | Core ATM zone |
| LOW_DUBS | $0.001–$0.003 | Low Dubs | Intermediate |
| DUBS | $0.001–$0.0099 | Dubs | Between Trips and Penny |
| PENNIES | $0.01–$0.03 | Pennies | Higher volume |

### Stability Detection (Scanner)

A stock is ATM-eligible only when trading in a stable, mean-reverting range for ≥30 days.

**For TRIP_ZERO stocks ($0.0001):** Use Tick Range Ratio (TRR) — count distinct price levels over 30 days. TRR ≤ 2-3 levels = stable.

**For all other tiers — four metrics must pass:**

| Metric | TRIPS | DUBS | PENNIES |
|--------|-------|------|---------|
| Coefficient of Variation (CV) | < 0.40 | < 0.25 | < 0.15 |
| Normalized ATR (NATR) | < 0.40 | < 0.25 | < 0.25 |
| Bollinger Band Width | < 0.50 | < 0.50 | < 0.50 |
| 30-day Price Range Ratio | < 0.50 | < 0.50 | < 0.50 |

Require ≥15 non-zero-volume trading days in the 30-day window.

### Abnormal Candle Detection

Dual threshold — flag if EITHER triggers:

| Tier | Absolute Threshold | Z-Score Threshold |
|------|-------------------|-------------------|
| TRIP_ZERO | ≥3 ticks movement + volume > 1.5x avg | N/A (tick-based only) |
| TRIPS | 150% daily move | > 3.0 σ from 30-day mean |
| DUBS | 75% daily move | > 2.5 σ |
| PENNIES | 30% daily move | > 2.5 σ |

Confirm with candle body-to-range ratio > 0.60 for directional moves.

### L2 Imbalance

```
L2_Imbalance_Ratio = Total_Bid_Shares / Total_Ask_Shares

≥ 3.0 → FAVORABLE (minimum for entry consideration)
≥ 5.0 → STRONG
< 3.0 → INSUFFICIENT (do not enter)
```

### Market Maker Classification

**Bad MMs (HARD REJECT if on Ask):**
MAXM, GLED, CFGN, PAUL, JANE, BBAR, BLAS, ALPS, STXG, AEXG, VFIN, VERT, BMAK

**Retail / Good MMs:**
ETRF, CSTI, GTSM, NITE

**Neutral:**
OTCN, OTCX, CDEL, INTL, VIRT

⚠️ This list requires manual update every ~6 months. Store in `config/constants.py` as an easily editable dict.

### Wall Detection (L2)

```
Wall_Ratio = Order_Size_At_Level / 20_Day_ADV

≥ 0.05 (5%) → Significant wall
≥ 0.10 (10%) → Major wall
≥ 0.25 (25%) → Mega wall / Dominant

Wall_Score = min(10, (Order_Size / ADV) × 10)
≥ 5 → Strong wall
≥ 8 → Dominant
```

A "breaking" wall = cumulative volume hitting it exceeds 50% of displayed size without price moving.

### L2 Refresh Detection (Finite State Machine)

Refresh = order filled at price P → new order appears at same price P:
- Size within ±20% of previous
- Appears within 30 seconds (algo) or 60 seconds (manual)
- ≥3 consecutive refreshes = confirmed

```
Refresh_Intensity = (refresh_events / time_window) × (tranche_size / ADV)
> 0.5 → Significant hidden liquidity
```

Fill-to-Display Ratio > 5.0 confirms iceberg/refresh.

Bid refresh = bullish (hidden buyer). Ask refresh = bearish (hidden seller).

### Prop Bid Detection (6-Factor Scoring)

Score each bid 0-3 on six factors (max 18):

1. **MPID history** — new MPID in this stock = suspicious
2. **Bid persistence** — sits for hours without execution
3. **Size vs MPID history** — outsized relative to MPID's normal
4. **Pulling behavior** — bid disappears when selling pressure arrives
5. **Stacking** — multiple entries at same price from one MPID
6. **Time-of-day** — unusual timing patterns

**Flag bid as suspected prop if score ≥ 6/18.**

Additional signals:
- Bid-to-execution ratio > 10:1
- Cancellation rate > 80% when price approaches

### Volume Analysis

**Modified Z-Score** (only non-zero volume days):
```
Z = (Today_Volume - μ_nonzero) / σ_nonzero

Z > 2.0 → Notable
Z > 3.0 → Significant (alert)
Z > 5.0 → Extreme (investigate immediately)
```

**RVOL** (Relative Volume):
```
RVOL = Today_Volume / 20_Day_MA_Volume

> 2.0 → Significant
> 5.0 → Extreme
```

Lookback: 20-30 active trading days. Extend to 50 for very low-activity stocks.

Zero-volume day handling: exclude from mean/σ calculation, but count them — if zero_days > 10 in 30-day window, flag as low-activity warning.

### Dilution Sentinel (Composite Score 0-10)

**Hard Rejects (immediate, no scoring needed):**
- Bad MM detected on Ask → REJECT

**Scoring signals:**

| Signal | Points | Detection |
|--------|--------|-----------|
| Bad MM on Ask | +4 | L2 MM lookup |
| Volume > 3x avg, price flat/down | +3 | Volume module |
| Bid erosion 3+ consecutive days | +2 | Daily L2 comparison |
| Block trades on bid (same time, price) | +2 | T&S pattern |
| Outstanding shares increase > 5% in 14 days | +3 | OTCMarkets data (manual check for v0) |
| Buyer/seller ratio drop below 2:1 | +1 | L2 imbalance |

**Actions by score:**
```
0-2  → CLEAR — normal operation
3-4  → WARNING — increase monitoring, tighten stops
5-6  → HIGH ALERT — prepare exit, no new entries
7+   → CRITICAL — exit immediately
```

Exit trigger: score ≥ 3.

### T&S Analysis

**Trade classification:**
```
IF trade_price == bid_price → Bid hit (sell, bearish)
IF trade_price == ask_price → Ask hit (buy, bullish)
```

**Ratio:**
```
Ask_Buys / Bid_Sells
> 1.0 → Bullish
< 1.0 → Bearish
```

**Block trade detection:**
- Multiple trades at same price, same fractional second
- Quantities in millions (e.g., 2.6M, 4.8M at same price/time)
- Flag as potential dilution dumping

**Cross trade detection:**
- "Odd" share quantities (not round lots)
- Same MMID on both sides
- Flag as wash trade / manipulation

### Risk Management

**Position sizing:**
```
position_value = portfolio_value × 0.05          # 5% max per position
max_loss_per_position = portfolio_value × 0.02   # 2% max loss
```

Recalculate portfolio_value at start of each month.

**Stop conditions (layered, any one triggers exit):**

1. **Hard dollar stop**: loss exceeds 2% of account value
2. **Volatility stop**: price drops 2× ATR below entry
3. **Time stop**: exceeds max hold time (see below)
4. **Dilution stop**: dilution score ≥ 3
5. **L2 collapse stop**: total bid size drops below 30% of bid size at entry

**Max hold times:**
```
TRIP_ZERO / TRIPS: 4 hours (intraday), 2 days (overnight)
DUBS: 2 days
PENNIES: 5 days absolute max
Never hold over a weekend.
```

### OTC Health Index (OHI) — Market Condition Gate

Composite score 0-100 from:
- OTC advance/decline ratio (25% weight)
- Total OTC dollar volume vs 20-day avg (20%)
- Count of stocks with 100%+ daily moves (15%)
- SPY direction (15%)
- Active sector theme presence (15%)
- Net new 52-week highs minus lows (10%)

```
≥ 65 → STRONG — full position sizing
40-64 → NEUTRAL — half position sizing
< 40 → WEAK — no new entries
```

### ATM Probability Scorer (Composite)

Replaces the original heuristic 100-point model. Each module contributes:

| Component | Max Score | Source Module |
|-----------|-----------|---------------|
| Range stability (30d) | 15 | Scanner |
| L2 imbalance ≥ 3:1 | 20 | L2 Analyzer |
| No bad MMs on Ask | 15 | L2 Analyzer |
| No volume anomalies | 10 | Volume Analyzer |
| Consistent daily volume | 10 | Volume Analyzer |
| Bid support below entry | 10 | L2 Analyzer |
| T&S ratio bullish | 10 | T&S Analyzer |
| Dilution score = 0 | 10 | Dilution Sentinel |

**Minimum score for watchlist addition: 70/100**
**Minimum score for trade consideration: 80/100**

---

## Database Schema (SQLite v0)

```sql
-- Scanned candidates
CREATE TABLE candidates (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    price_tier TEXT NOT NULL,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_scored TIMESTAMP,
    atm_score REAL,
    status TEXT DEFAULT 'active',  -- active | watching | rejected | trading
    rejection_reason TEXT
);

-- L2 snapshots (for building proprietary dataset)
CREATE TABLE l2_snapshots (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    bid_levels JSON NOT NULL,   -- [{price, size, mm_id}, ...]
    ask_levels JSON NOT NULL,
    imbalance_ratio REAL,
    total_bid_shares INTEGER,
    total_ask_shares INTEGER
);

-- Time & Sales records
CREATE TABLE trades (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    price TEXT NOT NULL,          -- Decimal as string
    size INTEGER NOT NULL,
    side TEXT,                    -- 'bid' | 'ask' | 'unknown'
    mm_id TEXT
);

-- Trade log (your manual trades)
CREATE TABLE trade_log (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    timestamp_entry TIMESTAMP,
    timestamp_exit TIMESTAMP,
    entry_price TEXT NOT NULL,
    exit_price TEXT,
    shares INTEGER NOT NULL,
    position_pct REAL,
    portfolio_value_at_entry REAL,
    l2_ratio_at_entry REAL,
    atm_score_at_entry REAL,
    bad_mm_present BOOLEAN DEFAULT FALSE,
    avg_volume_30d INTEGER,
    tracking_days INTEGER,
    exit_reason TEXT,             -- TARGET | DILUTION | DUMP | TIMEOUT | MANUAL
    pnl_usd REAL,
    pnl_pct REAL,
    notes TEXT
);

-- Alert history
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    alert_type TEXT NOT NULL,     -- VOLUME_ANOMALY | DILUTION | BID_COLLAPSE | RATIO_CHANGE
    severity TEXT NOT NULL,       -- INFO | WARNING | HIGH | CRITICAL
    message TEXT,
    acknowledged BOOLEAN DEFAULT FALSE
);

-- Daily scoring snapshots
CREATE TABLE daily_scores (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    atm_score REAL,
    stability_score REAL,
    l2_score REAL,
    volume_score REAL,
    dilution_score REAL,
    ts_score REAL,
    ohi_score REAL,
    UNIQUE(ticker, date)
);
```

---

## IBKR Connection Details

- **Library**: `ib_async`
- **Paper port**: 7497
- **Live port**: 7496
- **Host**: 127.0.0.1
- **Separate client IDs**: scanner = 1, data recorder = 2
- **Auto-reconnect**: exponential backoff on disconnect
- **OTC contract qualification**: SMART-first routing — OTC stocks can't qualify directly on PINK/GREY, must go through SMART. `primaryExchange` set to preserve venue attribution.
- **L2 data**: `reqMktDepth()` with `isSmartDepth=True` — required to get MPID (marketMaker) data. `isSmartDepth=False` returns empty MPIDs for OTC stocks.
- **L2 depth limit**: IBKR paper allows max 3 concurrent `reqMktDepth` subscriptions. IBAdapter manages a 3-slot queue with LRU eviction — oldest L2 sub is cancelled when a 4th ticker needs depth.
- **L2 contract**: Separate `_l2_contracts` dict stores contracts qualified with `primaryExchange` set (e.g., `Stock(sym, "SMART", "USD", primaryExchange="PINK")`). This is needed because the standard SMART-qualified contract may not carry venue-specific depth.
- **T&S data**: `reqTickByTickData()`
- **Orders**: LIMIT GTC only. Never MARKET orders.

---

## Coding Standards

- **Type hints everywhere**. Use `Decimal` for all financial values.
- **Pydantic models** for all data structures crossing module boundaries.
- **Async by default** — all I/O operations are async.
- **Structured logging** via `structlog` — every significant action logged with context.
- **No print statements** — use logger.
- **Tests for every module** — pytest, focus on rule logic and edge cases.
- **Config in YAML / .env** — no magic numbers in code. All thresholds in `config/constants.py` or `config/rules.yaml`.
- **Fail loud** — errors surface immediately, no silent swallowing.
- **Line length**: 100 chars max.

---

## Order of Build

Build in dependency order:

1. **config/** — settings, constants, price tiers, MM lists ✅ DONE (Phase 1)
2. **src/core/** — events, event bus, shared models ✅ DONE (Phase 1)
3. **src/database/** — schema, repository, persistence ✅ DONE (Phase 1 + Phase 9)
4. **src/broker/** — adapter ABC, IBAdapter, MockAdapter ✅ DONE (Phase 2)
5. **src/scanner/** — screener.py, stability.py ✅ DONE (Phase 3)
6. **src/analysis/** — level2.py, volume.py, time_sales.py, dilution.py ✅ DONE (Phase 4)
7. **src/rules/** — rule engine with YAML config ✅ DONE (Phase 5)
8. **src/risk/** — position sizing, OHI, stop conditions ✅ DONE (Phase 6)
9. **src/alerts/** — Telegram dispatcher ✅ DONE (Phase 7)
10. **scripts/run_system.py** — main entry, wires everything together ✅ DONE (Phase 8)

Each module should be independently testable before integration.

---

## Build Progress

**327 tests passing across 16 test files. Zero regressions at each phase. v0 pipeline complete + V1 dashboard deployed. Live IBKR data flow validated (Phase 12) — real L2 with MPIDs, real scores, real persistence confirmed against TWS.**

### Phase 1 — Config, Core, Database (48 tests)
- `config/constants.py` — all price tiers, stability thresholds, MM lists, volume/dilution/risk constants
- `config/settings.py` — Pydantic settings (IBKRSettings, DatabaseSettings, RiskSettings, etc.)
- `src/core/events.py` — 7 frozen event dataclasses (MarketDataEvent, L2UpdateEvent, TradeEvent, etc.)
- `src/core/event_bus.py` — async pub/sub with error isolation via asyncio.gather
- `src/core/models.py` — L2Level, L2Snapshot, Trade, CandidateScore, OHIScore
- `src/database/schema.py` — 6 SQLAlchemy ORM tables
- `src/database/repository.py` — async CRUD for all tables

### Phase 2 — Broker Adapter Layer (33 tests)
- `src/broker/adapter.py` — abstract BrokerAdapter ABC (10 abstract methods)
- `src/broker/ibkr.py` — IBAdapter: real ib_async with auto-reconnect (exp backoff 1s→60s), Decimal(str(float)) conversion, sync→async bridge via create_task, _background_tasks set for GC safety
- `src/broker/mock.py` — MockAdapter: push_market_data/push_l2_update/push_trade for synthetic data injection, get_subscriptions for test introspection, MockContract dataclass
- **Key pattern**: ABC accepts `symbol: str` + `exchange: str`, not broker-specific contract objects. `create_otc_contract` returns `object` to avoid ib_async import leak.

### Phase 3 — Scanner Module (58 tests)
- `src/scanner/stability.py` — pure-computation metrics:
  - TRIP_ZERO: Tick Range Ratio (count distinct price levels, ≤3 = stable)
  - TRIPS/DUBS/PENNIES: CV, NATR, Bollinger Band Width, Price Range Ratio
  - LOW_DUBS: mapped to DUBS thresholds (no separate entry in constants)
  - Abnormal candle detection: dual threshold (absolute move OR z-score), body/range ratio for directional confirm
  - TRIP_ZERO abnormal: requires BOTH ≥3 tick move AND volume > 1.5x avg
  - Zero-volume days excluded from all metric calculations, MIN_ACTIVE_TRADING_DAYS=15
- `src/scanner/screener.py` — event-driven Screener:
  - Subscribes to MarketDataEvent via start()
  - add_daily_bar() for historical data injection (30-day rolling window)
  - evaluate() runs tier check → stability check → abnormal candle check → publishes ScannerHitEvent
  - reject()/unreject() for manual symbol management

### Phase 4 — Analysis Modules (46 tests)
- `src/analysis/level2.py` — L2Analyzer:
  - Subscribes to L2UpdateEvent, computes imbalance ratio (STRONG ≥5.0, FAVORABLE ≥3.0, INSUFFICIENT)
  - Bad MM detection on ask side (checks against MM_BAD frozenset)
  - Wall detection: wall_ratio = size/ADV, wall_score = min(10, ratio×10), requires set_adv()
- `src/analysis/volume.py` — VolumeAnalyzer:
  - Subscribes to MarketDataEvent, maintains deque(maxlen=20) per symbol
  - Modified z-score on non-zero-volume days only
  - RVOL = current/mean, anomaly levels: NORMAL/NOTABLE(z≥2)/SIGNIFICANT(z≥3)/EXTREME(z≥5)
  - Auto-publishes AlertEvent for SIGNIFICANT+
- `src/analysis/time_sales.py` — TSAnalyzer:
  - Subscribes to TradeEvent, classifies as bid/ask/unknown
  - buy_sell_ratio = ask_hits/bid_hits, is_bullish = ratio > 1.0
  - Block trade detection: ≥3 fills at same price within 1 second
  - Tracks recent MM IDs (deduplicated, order-preserved)
- `src/analysis/dilution.py` — DilutionSentinel:
  - Pull model: queries L2Analyzer, VolumeAnalyzer, TSAnalyzer results on demand
  - 5 signals: bad MM on ask (+4), volume spike (+3), bid erosion (+2), block trades on bid (+2), low buy/sell ratio (+1)
  - Score capped at 10, severity: CLEAR(0-2), WARNING(3-4), HIGH_ALERT(5-6), CRITICAL(7+)
  - Exit trigger: score ≥ 3. Publishes DilutionAlertEvent for WARNING+
  - Tracks previous imbalance for bid erosion detection (>30% drop)

### Phase 5 — Rule Engine (29 tests)
- `config/rules.yaml` — declarative scoring weights, thresholds, action config
- `src/rules/engine.py` — RuleEngine:
  - Subscribes to ScannerHitEvent, pulls all 5 analyzer results
  - 8 scoring components: stability (15), L2 imbalance (20, scaled), no bad MM (15), no volume anomaly (10), consistent volume (10), bid support (10), T&S ratio (10), dilution clear (10)
  - YAML-driven: load_rules() reads config/rules.yaml with fallback to constants.py
  - Action: PASS (<70), WATCHLIST (≥70), TRADE (≥80)
  - Publishes AnalysisCompleteEvent after scoring

### Phase 6 — Risk Module (44 tests)
- `src/risk/position.py` — PositionSizer:
  - 5% max position, 2% max loss from RiskSettings
  - compute_with_ohi() adjusts sizing by OHI factor
  - Monthly portfolio value rebalance
- `src/risk/market_health.py` — MarketHealthAnalyzer:
  - OTC Health Index (OHI) composite 0-100 from 6 weighted components
  - STRONG (≥65) full size, NEUTRAL (40-64) half size, WEAK (<40) no entries
  - Input clamping [0, 100]
- `src/risk/stops.py` — StopManager:
  - 5 layered stop conditions (any triggers exit):
    1. Hard dollar: loss > 2% of portfolio
    2. Volatility: price < entry - 2×ATR
    3. Time: per-tier max hold (TRIPS 4h intraday/2d overnight, DUBS 2d, PENNIES 5d)
    4. Dilution: score ≥ 3
    5. L2 collapse: bid shares < 30% of entry

### Phase 7 — Alert System (23 tests)
- `src/alerts/dispatcher.py` — AlertDispatcher:
  - Subscribes to AlertEvent + DilutionAlertEvent
  - Priority mapping: INFO→LOW, WARNING→MEDIUM, HIGH→HIGH, CRITICAL→CRITICAL
  - Dilution alerts always HIGH+ priority
  - min_priority filtering, dispatch history tracking
- `src/alerts/telegram.py` — TelegramChannel:
  - python-telegram-bot v21+ async API wrapper
  - Graceful degradation: disabled by default, never crashes on send failure
  - Lazy import of telegram library

### Phase 8 — System Runner (12 tests)
- `scripts/run_system.py` — SystemRunner:
  - Composition root wiring all modules in dependency order
  - EventBus → IBAdapter → Screener → L2/Volume/TS Analyzers → DilutionSentinel → RuleEngine → DatabasePersistence → AlertDispatcher
  - Always uses IBAdapter (MockAdapter removed as default — Phase 12)
  - Async lifecycle: start() → run() → stop() with SIGINT/SIGTERM handlers
  - Windows-compatible signal handling (signal.signal fallback for SIGINT)
  - Telegram integration optional (disabled by default)

### Phase 9 — Go-Live Wiring (19 tests)
- `src/database/persistence.py` — PersistenceSubscriber:
  - Subscribes to 6 event types, routes each to correct Repository method
  - L2UpdateEvent → save_l2_snapshot (converts tuple levels to dict)
  - TradeEvent → save_trade
  - AlertEvent → save_alert
  - DilutionAlertEvent → save_alert (mapped to DILUTION type)
  - AnalysisCompleteEvent → upsert_daily_score (by ticker+date)
  - ScannerHitEvent → upsert_candidate (first-time only via _seen_candidates set)
- `src/database/repository.py` — added upsert_daily_score() and upsert_candidate() using SQLite INSERT ON CONFLICT DO UPDATE
- `src/database/schema.py` — added UNIQUE constraint on candidates.ticker
- `src/scanner/watchlist.py` — YAML watchlist loader + WatchlistEntry dataclass
- `config/watchlist.yaml` — user-populated symbol list
- `src/broker/history.py` — HistoryLoader.seed() one-shot seeder
- `src/broker/adapter.py` — added abstract request_historical_bars()
- `src/broker/ibkr.py` — implemented request_historical_bars() via reqHistoricalDataAsync
- `src/broker/mock.py` — implemented request_historical_bars() + set_historical_data()
- `scripts/run_system.py` — wired: DB init, persistence, watchlist, history seed, adapter selection (ATM_USE_IBKR=1), market data subscriptions per watchlist symbol
- `src/dashboard/app.py` — redesigned: dark terminal UI, card-based metrics, L2 depth viz, component score bars
- `.env.example` — updated with ATM_USE_IBKR, TELEGRAM_ENABLED

### Phase 10 — Dashboard Polish & Local Deploy
- `src/dashboard/app.py` — fixed: nav cutoff CSS, avg score query (JOINs daily_scores), candidate list JOINs daily_scores for real scores, Volume component max corrected to 20
- `scripts/seed_realistic.py` — realistic mock data seeder: 20 candidates across all 5 price tiers, 7-day score history with drift, L2 snapshots with MM IDs, 300+ trades, severity-distributed alerts
- `setup.sh` — one-command bootstrap: venv, deps, .env, dirs, demo data seed
- `start.sh` — launches engine + dashboard together, `--live` flag for IBKR, clean Ctrl+C shutdown via trap
- `README.md` — quick-start guide for non-developers (clone + setup + run)

### Phase 11 — V1 Dashboard Enhancement (15 new tests, 327 total)
- `config/i18n.py` — 120+ Hebrew/English string mappings, `t()` helper, `set_lang()`/`get_lang()`
- `config/user_config.py` — JSON config persistence at `data/user_config.json`, deep merge on defaults, `wizard_completed()` check
- `src/dashboard/app.py` — complete rewrite (1000+ lines added):
  - **4-tab layout**: Overview, Stock Detail, Trade Log, Settings
  - **First-run wizard**: 6-step (Welcome → Language → IBKR → Telegram → Risk → Done), shows once
  - **Settings page**: IBKR connection config, Telegram alerts with live test ping, risk parameters (12 fields), language toggle, system status summary
  - **Watchlist management**: manual ticker add (📌 MANUAL tag), per-candidate Remove/Pause/Prioritize actions, filter by tier+status, sort by score/ticker/date, prioritized pinned to top (⭐)
  - **Trade Logger**: entry form with auto-capture of ATM/L2 scores, active positions with Close Position (P&L calc), trade history with summary stats (win rate, avg/total P&L), score-vs-outcome correlation (bucket analysis + scatter)
  - **Hebrew/RTL**: full bidirectional support, RTL CSS on text containers, technical values stay LTR
  - **Nav bar**: real connection status (checks data activity, not hardcoded)
- `.gitignore` — added `data/user_config.json`
- `data/user_config.json` — local user overrides (gitignored), takes priority over `.env`
- **Dashboard uses sync sqlite3** (not async SQLAlchemy) — appropriate for read-heavy Streamlit UI
- **User config merges over defaults** — `config/user_config.py` deep-merges JSON overrides on top of `constants.py` defaults. Changes take effect immediately on Streamlit rerun.

### Phase 12 — Live IBKR Data Flow (2026-03-23)

First end-to-end live test against real TWS. Validated full pipeline with real OTC market data.

**Code changes:**
- `scripts/run_system.py` — removed MockAdapter as default, always uses IBAdapter. Removed `ATM_USE_IBKR` env var check.
- `src/broker/ibkr.py` — two fixes:
  1. **L2 depth limit management**: IBKR paper allows max 3 concurrent `reqMktDepth` streams. Added `_l2_active` list tracking active L2 subs, LRU eviction when limit reached (`_MAX_L2_SUBSCRIPTIONS = 3`).
  2. **MPID fix**: `isSmartDepth=False` returns empty `marketMaker` fields for OTC. Switched to `isSmartDepth=True` which populates MPIDs (CDEL, ETRF, GTSM, CSTI, NITE, etc.). Added `_create_l2_contract()` that qualifies a separate contract with `primaryExchange` set for venue-attributed depth. Falls back to SMART contract if OTC qualification fails.

**Live test results (tickers tested: CBDD, HADV, MWWC, CEIN, AGYP):**
- TWS server v178, paper account U21464598
- Contract qualification: all OTC stocks qualify via SMART routing only (direct PINK/GREY fails)
- L2 depth: real MPIDs flowing — CDEL, ETRF, GTSM, CSTI, NITE, INTL, OTCN, PUMA, VERT
- T&S: trade events with bid/ask side classification working
- Historical bars: 29-30 daily bars loaded per ticker
- Scoring pipeline: MWWC scored 50→72(WATCHLIST)→80(TRADE) in real-time as L2 data accumulated
- MWWC L2: 332M bid vs 62M ask (5.3:1 ratio), all neutral/good MMs, TRADE threshold hit
- CEIN L2: VERT (bad MM) detected on ask side — dilution sentinel can now flag this
- All data persisted to SQLite: L2 snapshots, trades, daily scores, candidates

**Known limitation:** Startup L2 subscriptions in `run_system.py` don't go through the limit manager — existing `active` candidates subscribe before TickerWatcher, which can exceed the 3-slot limit for the first batch.

### What's NOT built yet (v0 deferred items)
- L2 refresh detection FSM (constants exist, implementation deferred)
- Prop bid detection (constants exist, implementation deferred)

---

## End-User: Eldar

Eldar is the sole operator/trader. He is NOT a developer. The product must be operable by someone who:
- Understands OTC penny stock mechanics deeply (ATM pattern, L2, MMs, dilution)
- Manually trades via TWS — the system is his decision-support co-pilot
- Needs clear, actionable signals — not raw data dumps
- Wants to see: "Which stocks are ATM-ready? What changed? Should I exit?"

### What Eldar's daily workflow should look like

1. **Morning**: Opens dashboard → sees overnight scoring changes, new candidates, any critical alerts
2. **During session**: Dashboard auto-updates → L2 shifts, dilution warnings, volume spikes surface in real-time
3. **Trade decision**: Clicks into a candidate → sees ATM score, component breakdown, L2 depth, T&S flow → decides to enter/skip
4. **Position monitoring**: Active positions show stop status, dilution score, L2 collapse risk
5. **End of day**: Reviews what happened, logs manual trades, system learns from decisions vs outcomes

### Product layer progress (v0 → v0.5 roadmap)

1. ✅ **Watchlist management via UI** — add/remove/pause/prioritize tickers from dashboard (Phase 11)
2. ✅ **Position tracker** — Trade Log page: entry form, active positions, close with P&L, history (Phase 11)
3. ⬜ **Score change notifications** — "ABCD dropped from 85 → 62" as a Telegram push
4. ⬜ **Historical score view** — trend charts per ticker over days/weeks
5. ✅ **One-click actions** — Remove / Pause / Prioritize from candidate rows (Phase 11)
6. ⬜ **Mobile-friendly alerts** — Telegram messages with enough context to act on
7. ⬜ **Session summary** — end-of-day report: what scored, what alerted, what the human decided
8. ✅ **Settings page** — IBKR, Telegram, risk params, language toggle (Phase 11)
9. ✅ **First-run wizard** — 6-step setup, never shows again (Phase 11)
10. ✅ **Hebrew mode** — full bilingual UI with RTL support (Phase 11)
11. ✅ **Score vs outcome correlation** — bucket analysis + scatter chart in Trade Log (Phase 11)

---

## What Success Looks Like for v0

- Scanner identifies ATM candidates from OTC universe
- L2 snapshots being recorded continuously (proprietary dataset)
- All analysis modules score candidates on every data update
- Alerts fire on anomalies (volume spikes, dilution signals, bid collapse)
- Every event and score persisted to SQLite
- Human reviews candidates, makes trade decisions, logs them
- System logs human decisions against its own scoring
- After 50+ logged cycles: enough data to calibrate and validate

---

## What Comes After v0

**v0.5** (PARTIALLY COMPLETE): Product polish for Eldar. Watchlist UI ✅, position tracker ✅, settings/wizard ✅, Hebrew ✅. Still needed: score trends, actionable Telegram alerts, session summaries.

**v1**: Paper execution layer. System logs human decisions vs its scoring. L2 dataset grows. After 200+ cycles, statistical validation begins.

**v2**: Backtesting engine using proprietary L2 data. Custom event-driven backtester with OTC fill simulation (5% ADV cap, spread estimation via EDGE, square-root market impact). Walk-forward optimization.

**v3**: Semi-automated execution. System proposes trades, human confirms. Gradual automation of high-confidence patterns.

Do not build ahead. Stay in current phase until explicitly told to advance.

---

## Running the System

```bash
# First-time setup (creates venv, installs deps, seeds demo data)
bash setup.sh

# Start engine + dashboard together (mock mode)
bash start.sh

# Start with real IBKR data (TWS must be running on port 7497)
bash start.sh --live

# Or run individually:
.venv/bin/python scripts/run_system.py              # engine only
.venv/bin/python scripts/run_dashboard.py --port 8501  # dashboard only
ATM_USE_IBKR=1 .venv/bin/python scripts/run_system.py  # engine with IBKR

# Re-seed demo data
.venv/bin/python scripts/seed_realistic.py

# Tests
.venv/bin/pytest tests/ -x -q

# Lint
.venv/bin/ruff check src/ tests/ config/
```

### Config files
- `.env` — environment variables (copy from `.env.example`)
- `data/user_config.json` — user overrides (created by wizard/settings, gitignored, takes priority over .env)
- `config/watchlist.yaml` — tickers to monitor (engine-side; dashboard manages watchlist via DB)
- `config/rules.yaml` — scoring weights and thresholds
- `config/constants.py` — all hardcoded thresholds and MM lists
- `config/i18n.py` — Hebrew/English UI strings
- `config/user_config.py` — JSON config loader/saver with deep merge

### Co-founder deployment
Eldar runs TWS on his machine. To set up his environment:
1. Install Python 3.12+ and Git
2. `git clone <repo> && cd OTC && bash setup.sh`
3. Edit `.env` -> `ATM_USE_IBKR=1`, edit `config/watchlist.yaml` with tickers
4. `bash start.sh --live`

A hand-off prompt for his Claude Code CLI is available to automate the full setup.
