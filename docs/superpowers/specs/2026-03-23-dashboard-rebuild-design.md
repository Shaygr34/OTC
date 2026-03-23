# ATM Trading Engine — Dashboard Rebuild & Shared Environment

**Date:** 2026-03-23
**Status:** Design approved, pending implementation
**Authors:** Shay (architect), Claude (design partner)

---

## Problem Statement

The OTC ATM Trading Engine has a working analysis pipeline (v0 complete, 360 tests, validated with live IBKR data). But the product layer is broken:

1. **No shared environment** — Shay and Eldar work on separate machines, see different data, have code mismatches. Neither can observe the other's state.
2. **Dashboard is unusable** — the Streamlit dashboard is mismatched with the engine, only partially functional, and can only run locally.
3. **Interaction is CLI-only** — Eldar can only check tickers through Claude Code terminal. The system is not a product.

## Goals

- Shay and Eldar see the **same app, same data, same URL**
- A clean web dashboard that shows the **live pipeline**: insert ticker → data pooling → analysis → score → ATM plan
- Eldar can run the engine on his machine with IBKR and both see results on Vercel
- Unblock the validation/calibration loop (Path C) by making scores and data observable

## Non-Goals (for this phase)

- WebSocket/real-time streaming (polling is sufficient)
- Historical score trend charts (need more data first)
- Session summaries / end-of-day reports
- Universe scanning / automated ticker discovery
- Hebrew/RTL (English-first, Hebrew added later)
- L2 Refresh FSM or Prop Bid Detection engine features
- Trade logging page (exists in Streamlit V1, deferred to next dashboard iteration)

---

## Architecture

```
┌─────────────────────────────┐       ┌──────────────────────┐
│  ELDAR'S MACHINE            │       │  RAILWAY             │
│                             │       │                      │
│  TWS (IBKR) ──→ Engine     │──────→│  PostgreSQL          │
│                (Python)     │ write │  (single source      │
│                             │       │   of truth)          │
└─────────────────────────────┘       └──────────┬───────────┘
                                                 │ read
                                      ┌──────────▼───────────┐
                                      │  VERCEL              │
                                      │                      │
                                      │  Next.js Dashboard   │
                                      │  (Shay + Eldar       │
                                      │   see same app)      │
                                      └──────────────────────┘
```

### Three pieces, same git repo

| Piece | Tech | Where it runs | What it does |
|-------|------|---------------|-------------|
| **Engine** | Python 3.12, asyncio, ib_async, SQLAlchemy | Eldar's machine | IBKR data → analysis → scores → writes to Railway PG |
| **Database** | PostgreSQL | Railway | Single source of truth, replaces SQLite |
| **Dashboard** | Next.js, Tailwind, SWR | Vercel | Reads from PG, displays live pipeline, accepts ticker input |

### Future-proofing: Multi-broker support

The engine uses `BrokerAdapter` ABC. Currently only `IBAdapter` exists. A future `SchwabAdapter` will implement the same interface, publishing the same event types to the same EventBus. The dashboard and scoring pipeline are broker-agnostic — they read from the database, not from the broker. No architectural changes needed when Schwab is added.

---

## Repo Structure

Zero disruption to existing engine code. New `dashboard/` directory added alongside existing `src/`.

```
otc/
├── src/                     ← existing Python, untouched
├── config/                  ← existing, untouched
├── scripts/                 ← existing, untouched
├── tests/                   ← existing, untouched
├── dashboard/               ← NEW Next.js app
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx              ← Watchlist (home)
│   │   │   ├── ticker/
│   │   │   │   └── [symbol]/
│   │   │   │       └── page.tsx      ← Ticker Detail + ATM Plan
│   │   │   ├── alerts/
│   │   │   │   └── page.tsx          ← Alerts feed
│   │   │   └── api/
│   │   │       ├── candidates/
│   │   │       │   └── route.ts      ← GET list, POST add ticker
│   │   │       ├── ticker/
│   │   │       │   └── [symbol]/
│   │   │       │       └── route.ts  ← GET full ticker data
│   │   │       └── alerts/
│   │   │           └── route.ts      ← GET alerts
│   │   ├── components/
│   │   │   ├── ScoreBar.tsx
│   │   │   ├── ScoreBreakdown.tsx
│   │   │   ├── L2DepthPanel.tsx
│   │   │   ├── TSFeed.tsx
│   │   │   ├── ATMPlan.tsx
│   │   │   ├── AddTickerInput.tsx
│   │   │   ├── AlertCard.tsx
│   │   │   ├── StatusBadge.tsx
│   │   │   └── ConnectionStatus.tsx
│   │   └── lib/
│   │       ├── db.ts                 ← PG connection pool (pg)
│   │       ├── queries.ts            ← SQL query functions
│   │       └── types.ts              ← shared TypeScript types
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── next.config.js
│   └── .env.local                    ← DATABASE_URL
├── shared/
│   ├── schema.sql                    ← canonical PG schema (6 tables + new columns)
│   └── migrate.py                    ← one-shot SQLite → PG migration
├── requirements.txt
├── vercel.json                       ← { "rootDirectory": "dashboard" }
├── CLAUDE.md
└── start.sh
```

---

## Database Migration: SQLite → PostgreSQL

### Schema (6 existing tables, unchanged structure)

Same 6 tables. Key dialect differences handled automatically by SQLAlchemy:

| SQLite | PostgreSQL | Notes |
|--------|-----------|-------|
| `INTEGER PRIMARY KEY` | `SERIAL PRIMARY KEY` | Auto-increment |
| `JSON` | `JSONB` | Better indexing for L2 bid/ask levels |
| `TEXT` for prices | `TEXT` for prices | Decimal-as-string preserved |
| `TIMESTAMP` | `TIMESTAMP WITH TIME ZONE` | Timezone-aware |

### New columns on `daily_scores`

```sql
ALTER TABLE daily_scores ADD COLUMN components_scored INTEGER;
ALTER TABLE daily_scores ADD COLUMN score_detail JSONB;
```

`score_detail` structure:
```json
{
  "stability": {"score": 15, "max": 15, "has_data": true},
  "l2_imbalance": {"score": 20, "max": 20, "has_data": true},
  "no_bad_mm": {"score": 15, "max": 15, "has_data": true},
  "no_vol_anomaly": {"score": 10, "max": 10, "has_data": true},
  "consistent_vol": {"score": 10, "max": 10, "has_data": true},
  "bid_support": {"score": 0, "max": 10, "has_data": false},
  "ts_ratio": {"score": 0, "max": 10, "has_data": false},
  "dilution_clear": {"score": 10, "max": 10, "has_data": true}
}
```

### Engine changes (not just config — code changes required)

**1. Connection string swap:**
```
# Engine .env (Python, SQLAlchemy async)
DATABASE_URL=postgresql+asyncpg://user:pass@host.railway.app:5432/railway

# Dashboard .env.local (Next.js, pg npm package — different format, no driver suffix)
DATABASE_URL=postgresql://user:pass@host.railway.app:5432/railway
```

Note: these are **two different formats** for the same database. The Python engine uses the `+asyncpg` SQLAlchemy driver prefix. The Next.js dashboard uses raw `postgresql://` for the `pg` npm package.

**2. Replace SQLite-specific upsert code:**

`repository.py` currently imports `from sqlalchemy.dialects.sqlite import insert as sqlite_insert` and uses it in `upsert_daily_score()` and `upsert_candidate()`. This is **not dialect-agnostic** — it will fail on PostgreSQL.

Fix: Replace with `from sqlalchemy.dialects.postgresql import insert as pg_insert` and use `.on_conflict_do_update()` (same API, different dialect). Since we're committing to PostgreSQL, use the PG dialect directly.

**3. Add `asyncpg` to `requirements.txt`.**

### Score detail — new engine work required

The `components_scored` and `score_detail` fields **do not exist** in the current codebase. This requires:

1. **Schema** (`src/database/schema.py`): Add `components_scored` (Integer) and `score_detail` (JSON) columns to `DailyScore` model
2. **RuleEngine** (`src/rules/engine.py`): After computing each of the 8 component scores, build a `score_detail` dict tracking `{score, max, has_data}` per component. Count components where `has_data=True` for `components_scored`.
3. **Events** (`src/core/events.py`): Add `score_detail` and `components_scored` fields to `AnalysisCompleteEvent`
4. **PersistenceSubscriber** (`src/database/persistence.py`): Pass the new fields through to `upsert_daily_score()`
5. **Repository** (`src/database/repository.py`): `upsert_daily_score()` gains `components_scored` and `score_detail` params

This is ~50-80 lines of new code across 5 files, not a trivial config change.

### Migration script (`shared/migrate.py`)

One-shot: reads local SQLite, writes to Railway PG. Run once during cutover. Not needed if starting fresh (demo data can be re-seeded directly to PG).

---

## Dashboard Pages

### Page 1: Watchlist (`/`) — Home

**Purpose:** Overview of all candidates. Primary landing page.

**Components:**
- **Header bar**: connection status (engine heartbeat check), total candidates, avg score
- **Add Ticker input**: text field + button → `POST /api/candidates` → inserts with `status='manual'`
- **Candidates table** (sortable):
  - Ticker (link to detail page)
  - Tier badge (TRIP_ZERO / TRIPS / DUBS / PENNIES)
  - Score bar (color-coded: <70 grey, 70-79 yellow WATCHLIST, 80+ green TRADE)
  - Data completeness (e.g. "7/8")
  - Status badge (manual / active / rejected)
  - L2 ratio (if available)
  - Bad MMs on ask (red highlight if any)
  - Last updated timestamp

### Page 2: Ticker Detail (`/ticker/[symbol]`)

**Purpose:** Deep dive into a single ticker. Everything needed to make a trade decision.

**Sections:**
1. **Score card** — large score number, PASS/WATCHLIST/TRADE label, data completeness ("7/8 components scored")
2. **Component breakdown** — 8-row table: component name, score/max, has_data flag, source detail (e.g. "5.3:1 ratio → STRONG")
3. **L2 Depth panel** — bid/ask levels with:
   - MM name (MPID)
   - Size (formatted: "100M", "8.5M")
   - Bad MMs highlighted red
   - Total bid vs ask shares, imbalance ratio
4. **T&S feed** — recent trades: time, price, size, side (bid/ask/unknown), block trade flag
5. **ATM Plan section** — computed server-side from existing data, not a new engine table:
   - Recommended position size: `risk.max_position_pct * risk.portfolio_value / current_price` (from risk settings + latest price in daily_scores)
   - Entry price level: current bid from latest L2 snapshot
   - Estimated hold time: tier-based lookup from `config/constants.py` thresholds (TRIP_ZERO: 4h/2d, DUBS: 2d, PENNIES: 5d)
   - Stop loss level: entry price - 2 * NATR (from stability metrics in score_detail)
   - Max dollar loss: `risk.max_loss_pct * risk.portfolio_value`
   - Dilution status: from latest daily_scores dilution_score
   - All values derived from existing DB data + constants — no new engine persistence needed
6. **Alerts** — ticker-specific, recent, severity-colored

### Page 3: Alerts (`/alerts`)

**Purpose:** Cross-ticker alert feed.

**Components:**
- Chronological list of all alerts
- Filterable by: severity (INFO/WARNING/HIGH/CRITICAL), ticker
- Each alert: timestamp, ticker, type, severity badge, message

### Shared Layout

- **Sidebar nav**: Watchlist / Alerts
- **Dark theme**: trading-terminal aesthetic, dark backgrounds, bright data
- **Auto-refresh**: SWR with 5-second polling interval on all data-fetching hooks

---

## API Routes

All routes are Next.js API routes (`app/api/`), querying Railway PG via the `pg` npm package with a connection pool.

### Connection Pooling

Vercel serverless functions spin up/down constantly. Without pooling, each invocation opens a new PG connection. With 5-second polling from 2 users across multiple routes, connection exhaustion is a real risk (Railway default: ~100 max connections).

**Solution:** Use `pg.Pool` with aggressive limits:
```typescript
// dashboard/src/lib/db.ts
import { Pool } from 'pg'

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 5,                    // max connections per serverless instance
  idleTimeoutMillis: 10000,  // close idle connections after 10s
  connectionTimeoutMillis: 5000,
})
```

This keeps connection count low even under polling load.

### Authentication

The dashboard is deployed to a public Vercel URL. Minimum security for a trading system:

**Phase 1 (MVP):** Vercel password protection (built-in, free on Pro plan). Locks the entire app behind a password without code changes.

**Phase 2 (if needed):** API key middleware — all API routes check for `x-api-key` header matching an env var. Dashboard sends it with every request.

### `GET /api/candidates`

Returns all candidates with latest daily score.

```sql
SELECT c.ticker, c.price_tier, c.status, c.exchange, c.first_seen,
       d.atm_score, d.components_scored, d.score_detail,
       d.stability_score, d.l2_score, d.volume_score, d.dilution_score, d.ts_score
FROM candidates c
LEFT JOIN daily_scores d ON c.ticker = d.ticker
  AND d.date = (SELECT MAX(date) FROM daily_scores WHERE ticker = c.ticker)
WHERE c.status != 'rejected'
ORDER BY CAST(d.atm_score AS FLOAT) DESC NULLS LAST
```

### `POST /api/candidates`

Add a ticker. Body: `{ "ticker": "MWWC" }`

```sql
INSERT INTO candidates (ticker, price_tier, status, first_seen)
VALUES ($1, 'UNKNOWN', 'manual', NOW())
ON CONFLICT (ticker) DO NOTHING
```

Returns 201 if inserted, 200 if already exists.

**Tier resolution flow:** The `price_tier` is set to `'UNKNOWN'` on insert. This is correct — the `TickerWatcher` on Eldar's machine picks up `status='manual'` candidates, qualifies the IBKR contract, fetches historical bars, determines the actual price tier from the last close, and updates the row to `status='active'` with the real tier. This flow already exists in `src/core/ticker_watcher.py` — no changes needed.

### `GET /api/health`

Returns engine and database status for the `ConnectionStatus` component.

```sql
SELECT
  (SELECT MAX(timestamp) FROM trades) as last_trade,
  (SELECT MAX(timestamp) FROM l2_snapshots) as last_l2,
  (SELECT COUNT(*) FROM candidates WHERE status = 'active') as active_tickers,
  (SELECT COUNT(*) FROM candidates WHERE status = 'manual') as pending_tickers
```

Distinguishes: "engine is running" (recent data) vs "engine is stopped" (stale data) vs "database is down" (query fails).

### `GET /api/ticker/[symbol]`

Returns full ticker data: candidate info, latest score with component breakdown, recent L2 snapshots, recent trades, recent alerts.

Multiple queries:
1. Candidate + latest daily_score (with score_detail JSONB)
2. Last 10 L2 snapshots: `SELECT * FROM l2_snapshots WHERE ticker = $1 ORDER BY timestamp DESC LIMIT 10`
3. Last 50 trades: `SELECT * FROM trades WHERE ticker = $1 ORDER BY timestamp DESC LIMIT 50`
4. Last 10 alerts: `SELECT * FROM alerts WHERE ticker = $1 ORDER BY timestamp DESC LIMIT 10`

### `GET /api/alerts`

Returns recent alerts across all tickers. Supports `?severity=` and `?ticker=` query params.

```sql
SELECT * FROM alerts
WHERE ($1::text IS NULL OR severity = $1)
  AND ($2::text IS NULL OR ticker = $2)
ORDER BY timestamp DESC
LIMIT 50
```

---

## PostgreSQL Indexes

Dashboard queries filter/sort by ticker, timestamp, date, and severity. Without indexes, queries degrade as L2 snapshots and trades accumulate (~170K L2 rows/day with 10 active tickers).

```sql
CREATE INDEX idx_daily_scores_ticker_date ON daily_scores(ticker, date DESC);
CREATE INDEX idx_l2_snapshots_ticker_ts ON l2_snapshots(ticker, timestamp DESC);
CREATE INDEX idx_trades_ticker_ts ON trades(ticker, timestamp DESC);
CREATE INDEX idx_alerts_ticker_ts ON alerts(ticker, timestamp DESC);
CREATE INDEX idx_alerts_severity ON alerts(severity);
CREATE INDEX idx_candidates_status ON candidates(status);
```

### Data Retention

L2 snapshots and trades grow fast. For MVP, no automatic pruning — Railway's paid tier has sufficient storage. Monitor and add retention (e.g. keep 7 days of L2 snapshots, 30 days of trades) when data volume becomes a concern.

---

## Engine Changes (5 files, ~80 lines)

1. **Connection string swap**: `DATABASE_URL` env var → `postgresql+asyncpg://...`
2. **Add `asyncpg` to requirements.txt**
3. **Replace `sqlite_insert`** in `repository.py` → `from sqlalchemy.dialects.postgresql import insert as pg_insert`. Both `upsert_daily_score()` and `upsert_candidate()` must be updated. Same `.on_conflict_do_update()` API, different import.
4. **Score detail in RuleEngine** (`src/rules/engine.py`): new work — build `score_detail` dict and `components_scored` count after computing each component. See "Score detail — new engine work required" section above.
5. **Events** (`src/core/events.py`): Add `score_detail` (dict) and `components_scored` (int) to `AnalysisCompleteEvent`
6. **PersistenceSubscriber** (`src/database/persistence.py`): Pass new fields through to `upsert_daily_score()`
7. **Schema** (`src/database/schema.py`): Add `components_scored` (Integer) and `score_detail` (JSON) columns to `DailyScore` model
8. **Repository** (`src/database/repository.py`): `upsert_daily_score()` gains `components_scored` and `score_detail` params

---

## Auto-Refresh Strategy

**SWR polling, 5-second interval.** No WebSocket.

```typescript
// dashboard/src/lib/hooks.ts
export function useCandidates() {
  return useSWR('/api/candidates', fetcher, { refreshInterval: 5000 })
}

export function useTicker(symbol: string) {
  return useSWR(`/api/ticker/${symbol}`, fetcher, { refreshInterval: 5000 })
}
```

**Why not WebSocket:**
- OTC stocks don't tick every millisecond — 5s polling is sufficient
- Vercel serverless doesn't support long-lived connections
- Engine writes to PG every few seconds anyway
- Polling is simpler to implement, debug, and deploy

---

## Connection Status Detection

Dashboard checks engine liveness by querying the most recent data timestamp:

```sql
SELECT MAX(timestamp) as last_activity FROM (
  SELECT MAX(timestamp) as timestamp FROM trades
  UNION ALL
  SELECT MAX(timestamp) as timestamp FROM l2_snapshots
) recent
```

If `last_activity` is within 30 seconds → "Connected" (green)
If 30s-5min → "Stale" (yellow)
If >5min or null → "Disconnected" (red)

---

## Deployment

### Railway PostgreSQL
- Provision via Railway CLI: `railway add --plugin postgresql`
- Get connection string from Railway dashboard
- Set as `DATABASE_URL` in both engine `.env` and dashboard `.env.local`

### Vercel
- `vercel.json` at repo root: `{ "rootDirectory": "dashboard" }`
- Connect repo on Vercel, set `DATABASE_URL` env var
- Auto-deploys on push to main

### Eldar's Machine
- `pip install asyncpg` (add to requirements.txt)
- Update `.env`: `DATABASE_URL=postgresql+asyncpg://...`
- Run engine as before: `python scripts/run_system.py`

---

## What This Enables

1. **Shared environment** — Shay and Eldar see the same app at the same URL
2. **Observable pipeline** — insert ticker → watch data pool → see scores climb → view ATM plan
3. **Push code, see results** — Vercel auto-deploys on push to main
4. **Validation loop unlocked** — both can observe the same scores and data to calibrate thresholds
5. **Multi-broker ready** — Schwab adapter slots in alongside IBKR, writes to same PG, appears in same dashboard
