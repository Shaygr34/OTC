# Dashboard Rebuild & Shared Environment — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a shared Next.js dashboard on Vercel reading from Railway PostgreSQL, with the Python engine writing to the same PG instance.

**Architecture:** Engine (Python, Eldar's machine) → Railway PostgreSQL ← Next.js Dashboard (Vercel). Same git repo, `dashboard/` directory for Next.js, existing Python code untouched at root.

**Tech Stack:** Next.js 15 (App Router), Tailwind CSS, SWR, `pg` npm package, Railway PostgreSQL, Vercel. Engine: Python 3.12, SQLAlchemy + asyncpg.

**Spec:** `docs/superpowers/specs/2026-03-23-dashboard-rebuild-design.md`

---

## Chunk 1: Database Migration (Engine → PostgreSQL)

### Task 1: Provision Railway PostgreSQL

**Files:**
- Create: `shared/schema.sql`
- Modify: `.env.example`

- [ ] **Step 1: Create Railway PostgreSQL instance**

```bash
cd /Users/shay/otc
railway link  # link to existing project or create new
railway add --plugin postgresql
railway variables  # copy DATABASE_URL
```

- [ ] **Step 2: Write canonical PG schema**

Create `shared/schema.sql`:

```sql
-- ATM Trading Engine — PostgreSQL Schema

CREATE TABLE IF NOT EXISTS candidates (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL UNIQUE,
    price_tier TEXT NOT NULL,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_scored TIMESTAMPTZ,
    atm_score TEXT,
    status TEXT DEFAULT 'active',
    exchange TEXT DEFAULT 'PINK',
    rejection_reason TEXT
);

CREATE TABLE IF NOT EXISTS l2_snapshots (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    bid_levels JSONB NOT NULL,
    ask_levels JSONB NOT NULL,
    imbalance_ratio TEXT,
    total_bid_shares INTEGER,
    total_ask_shares INTEGER
);

CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    price TEXT NOT NULL,
    size INTEGER NOT NULL,
    side TEXT,
    mm_id TEXT
);

CREATE TABLE IF NOT EXISTS trade_log (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    timestamp_entry TIMESTAMPTZ,
    timestamp_exit TIMESTAMPTZ,
    entry_price TEXT NOT NULL,
    exit_price TEXT,
    shares INTEGER NOT NULL,
    position_pct TEXT,
    portfolio_value_at_entry TEXT,
    l2_ratio_at_entry TEXT,
    atm_score_at_entry TEXT,
    bad_mm_present BOOLEAN DEFAULT FALSE,
    avg_volume_30d INTEGER,
    tracking_days INTEGER,
    exit_reason TEXT,
    pnl_usd TEXT,
    pnl_pct TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT,
    acknowledged BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS daily_scores (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    atm_score TEXT,
    stability_score TEXT,
    l2_score TEXT,
    volume_score TEXT,
    dilution_score TEXT,
    ts_score TEXT,
    ohi_score TEXT,
    components_scored INTEGER,
    score_detail JSONB,
    UNIQUE(ticker, date)
);

-- Indexes for dashboard query performance
CREATE INDEX IF NOT EXISTS idx_daily_scores_ticker_date ON daily_scores(ticker, date DESC);
CREATE INDEX IF NOT EXISTS idx_l2_snapshots_ticker_ts ON l2_snapshots(ticker, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trades_ticker_ts ON trades(ticker, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_ticker_ts ON alerts(ticker, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);
```

- [ ] **Step 3: Apply schema to Railway PG**

```bash
railway run psql < shared/schema.sql
```

- [ ] **Step 4: Update .env.example**

Add:
```
# PostgreSQL (Railway) — used by engine
DATABASE_URL=postgresql+asyncpg://user:pass@host.railway.app:5432/railway
```

- [ ] **Step 5: Commit**

```bash
git add shared/schema.sql .env.example
git commit -m "feat: add PostgreSQL schema and Railway provisioning"
```

---

### Task 2: Migrate engine from SQLite to PostgreSQL

**Files:**
- Modify: `src/database/schema.py`
- Modify: `src/database/repository.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add asyncpg dependency**

In `requirements.txt`, add:
```
asyncpg>=0.29
```

Run:
```bash
.venv/bin/pip install asyncpg
```

- [ ] **Step 2: Add score_detail columns to schema.py**

In `src/database/schema.py`, add to `DailyScore` class (after `ohi_score`):

```python
    components_scored: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 3: Replace sqlite_insert with pg_insert in repository.py**

In `src/database/repository.py`:

Replace:
```python
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
```
With:
```python
from sqlalchemy.dialects.postgresql import insert as pg_insert
```

In `upsert_daily_score()`, replace:
```python
            stmt = (
                sqlite_insert(DailyScore)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["ticker", "date"],
                    set_=update_cols,
                )
            )
```
With:
```python
            stmt = (
                pg_insert(DailyScore)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["ticker", "date"],
                    set_=update_cols,
                )
            )
```

In `upsert_candidate()`, same change — `sqlite_insert(Candidate)` → `pg_insert(Candidate)`.

- [ ] **Step 4: Add components_scored and score_detail to upsert_daily_score**

In `repository.py`, update `upsert_daily_score` signature and values dict:

```python
    async def upsert_daily_score(
        self,
        ticker: str,
        date: str,
        atm_score: Decimal | None = None,
        stability_score: Decimal | None = None,
        l2_score: Decimal | None = None,
        volume_score: Decimal | None = None,
        dilution_score: Decimal | None = None,
        ts_score: Decimal | None = None,
        ohi_score: Decimal | None = None,
        components_scored: int | None = None,
        score_detail: dict | None = None,
    ) -> None:
```

Add to the `values` dict:
```python
            "components_scored": components_scored,
            "score_detail": score_detail,
```

- [ ] **Step 5: Remove the SQLite ALTER TABLE migration in create_all_tables**

In `schema.py`, the `create_all_tables` function has a try/except block adding `exchange` column for old SQLite DBs. Keep it for now — it's harmless on PG and handles edge cases.

- [ ] **Step 6: Run existing tests to verify nothing broke**

```bash
.venv/bin/pytest tests/ -x -q
```

Expected: tests may fail because they use SQLite in-memory. Tests need to keep working with SQLite for CI — see next step.

- [ ] **Step 7: Make repository dialect-agnostic for tests**

The tests use SQLite in-memory. We need both dialects to work. Add a `use_postgres` flag to Repository:

In `repository.py`, keep both dialect imports and add a constructor flag:

```python
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
```

Update the Repository class:
```python
class Repository:
    def __init__(self, session_factory, *, use_postgres: bool = False) -> None:
        self._session_factory = session_factory
        self._use_pg = use_postgres

    def _insert_for(self, table):
        """Return dialect-appropriate insert construct."""
        if self._use_pg:
            return pg_insert(table)
        return sqlite_insert(table)
```

Then in both `upsert_daily_score()` and `upsert_candidate()`, replace `pg_insert(DailyScore)` / `pg_insert(Candidate)` with `self._insert_for(DailyScore)` / `self._insert_for(Candidate)`.

In `scripts/run_system.py`, pass `use_postgres="postgresql" in database_url`.
In tests, default `use_postgres=False` keeps SQLite working.

- [ ] **Step 8: Run tests again**

```bash
.venv/bin/pytest tests/ -x -q
```

Expected: 360 passed.

- [ ] **Step 9: Update engine .env with Railway DATABASE_URL**

```bash
# In .env (on Eldar's machine AND locally for testing)
DATABASE_URL=postgresql+asyncpg://user:pass@containers-us-west-XXX.railway.app:5432/railway
```

- [ ] **Step 10: Test engine against Railway PG**

```bash
.venv/bin/python -c "
import asyncio
from src.database.repository import get_engine, get_session_factory
from src.database.schema import create_all_tables

async def test():
    engine = get_engine('postgresql+asyncpg://...')  # paste Railway URL
    await create_all_tables(engine)
    print('Tables created on Railway PG!')

asyncio.run(test())
"
```

- [ ] **Step 11: Commit**

```bash
git add src/database/schema.py src/database/repository.py requirements.txt
git commit -m "feat: migrate engine to PostgreSQL with dual-dialect upsert support"
```

---

### Task 3: Score detail in RuleEngine

**Files:**
- Modify: `src/core/events.py`
- Modify: `src/rules/engine.py`
- Modify: `src/database/persistence.py`
- Test: `tests/test_rule_engine.py`

- [ ] **Step 1: Add score_detail fields to AnalysisCompleteEvent**

In `src/core/events.py`, update `AnalysisCompleteEvent`:

```python
@dataclass(frozen=True)
class AnalysisCompleteEvent:
    ticker: str
    atm_score: Decimal
    stability_score: Decimal
    l2_score: Decimal
    volume_score: Decimal
    dilution_score: Decimal
    ts_score: Decimal
    components_scored: int = 0
    score_detail: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
```

Note: `score_detail` must come before `timestamp` in the field order since `timestamp` has a default.

- [ ] **Step 2: Update RuleEngine.score() to emit score_detail**

In `src/rules/engine.py`, update the `score()` method. After computing each component, build the detail dict:

```python
    def score(self, symbol: str) -> ScoringResult:
        r = self._rules
        detail = {}

        # 1) Stability
        stability_result = self._screener.get_last_result(symbol)
        has_stability = stability_result is not None
        if has_stability and stability_result.is_stable:
            stability_pts = Decimal(str(r.weight_stability))
        else:
            stability_pts = _ZERO
        detail["stability"] = {
            "score": float(stability_pts), "max": r.weight_stability,
            "has_data": has_stability,
        }

        # 2) L2 Imbalance
        l2 = self._l2.get_result(symbol)
        has_l2 = l2 is not None
        if has_l2 and l2.imbalance_ratio >= r.l2_imbalance_strong:
            l2_pts = Decimal(str(r.weight_l2_imbalance))
        elif has_l2 and l2.imbalance_ratio >= r.l2_imbalance_favorable:
            l2_pts = Decimal(str(r.weight_l2_imbalance)) * Decimal("0.6")
        else:
            l2_pts = _ZERO
        detail["l2_imbalance"] = {
            "score": float(l2_pts), "max": r.weight_l2_imbalance,
            "has_data": has_l2,
        }

        # 3) No Bad MM
        if has_l2 and not l2.has_bad_mm_on_ask:
            bad_mm_pts = Decimal(str(r.weight_no_bad_mm))
        else:
            bad_mm_pts = _ZERO
        detail["no_bad_mm"] = {
            "score": float(bad_mm_pts), "max": r.weight_no_bad_mm,
            "has_data": has_l2,
        }

        # 4) No Volume Anomaly
        vol = self._volume.get_result(symbol)
        has_vol = vol is not None
        if has_vol and vol.zscore < r.volume_anomaly_zscore_max:
            vol_anomaly_pts = Decimal(str(r.weight_no_volume_anomaly))
        else:
            vol_anomaly_pts = _ZERO
        detail["no_vol_anomaly"] = {
            "score": float(vol_anomaly_pts), "max": r.weight_no_volume_anomaly,
            "has_data": has_vol,
        }

        # 5) Consistent Volume
        if has_vol and vol.active_days >= r.consistent_volume_min_days:
            consistent_vol_pts = Decimal(str(r.weight_consistent_volume))
        else:
            consistent_vol_pts = _ZERO
        detail["consistent_vol"] = {
            "score": float(consistent_vol_pts), "max": r.weight_consistent_volume,
            "has_data": has_vol,
        }

        # 6) Bid Support
        if has_l2 and l2.imbalance_ratio >= r.bid_support_min_ratio:
            bid_support_pts = Decimal(str(r.weight_bid_support))
        else:
            bid_support_pts = _ZERO
        detail["bid_support"] = {
            "score": float(bid_support_pts), "max": r.weight_bid_support,
            "has_data": has_l2,
        }

        # 7) T&S Ratio
        ts = self._ts.get_result(symbol)
        has_ts = ts is not None and ts.total_trades > 0
        if has_ts and ts.buy_sell_ratio >= r.ts_ratio_bullish_min:
            ts_pts = Decimal(str(r.weight_ts_ratio))
        else:
            ts_pts = _ZERO
        detail["ts_ratio"] = {
            "score": float(ts_pts), "max": r.weight_ts_ratio,
            "has_data": has_ts,
        }

        # 8) Dilution Clear
        dil = self._dilution.get_result(symbol)
        has_dil = dil is not None
        if has_dil and dil.score <= r.dilution_clear_max:
            dil_pts = Decimal(str(r.weight_dilution_clear))
        else:
            dil_pts = _ZERO
        detail["dilution_clear"] = {
            "score": float(dil_pts), "max": r.weight_dilution_clear,
            "has_data": has_dil,
        }

        # Composite
        total = (stability_pts + l2_pts + bad_mm_pts + vol_anomaly_pts
                 + consistent_vol_pts + bid_support_pts + ts_pts + dil_pts)

        if total >= Decimal(str(r.min_trade)):
            action = "TRADE"
        elif total >= Decimal(str(r.min_watchlist)):
            action = "WATCHLIST"
        else:
            action = "PASS"

        components_scored = sum(1 for d in detail.values() if d["has_data"])

        return ScoringResult(
            ticker=symbol,
            total_score=total,
            stability_score=stability_pts,
            l2_score=l2_pts + bad_mm_pts + bid_support_pts,
            volume_score=vol_anomaly_pts + consistent_vol_pts,
            dilution_score=dil_pts,
            ts_score=ts_pts,
            action=action,
            components_scored=components_scored,
            score_detail=detail,
        )
```

- [ ] **Step 3: Update ScoringResult dataclass**

Add two fields:
```python
@dataclass(frozen=True)
class ScoringResult:
    ticker: str
    total_score: Decimal
    stability_score: Decimal
    l2_score: Decimal
    volume_score: Decimal
    dilution_score: Decimal
    ts_score: Decimal
    action: str
    components_scored: int = 0
    score_detail: dict = field(default_factory=dict)
```

(Note: need to import `field` from dataclasses at top of file)

- [ ] **Step 4: Update _on_scanner_hit to pass new fields to event**

In `engine.py`, update `_on_scanner_hit`:

```python
        analysis_event = AnalysisCompleteEvent(
            ticker=event.ticker,
            atm_score=result.total_score,
            stability_score=result.stability_score,
            l2_score=result.l2_score,
            volume_score=result.volume_score,
            dilution_score=result.dilution_score,
            ts_score=result.ts_score,
            components_scored=result.components_scored,
            score_detail=result.score_detail,
        )
```

- [ ] **Step 5: Update PersistenceSubscriber to pass new fields**

In `src/database/persistence.py`, update `_on_analysis_complete`:

```python
    async def _on_analysis_complete(self, event: AnalysisCompleteEvent) -> None:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        await self._repo.upsert_daily_score(
            ticker=event.ticker,
            date=today,
            atm_score=event.atm_score,
            stability_score=event.stability_score,
            l2_score=event.l2_score,
            volume_score=event.volume_score,
            dilution_score=event.dilution_score,
            ts_score=event.ts_score,
            components_scored=event.components_scored,
            score_detail=event.score_detail,
        )
```

- [ ] **Step 6: Run tests**

```bash
.venv/bin/pytest tests/ -x -q
```

Fix any test failures from the new fields (likely in `test_rule_engine.py` — tests may need to accept the new `components_scored` and `score_detail` fields on `ScoringResult`).

- [ ] **Step 7: Commit**

```bash
git add src/core/events.py src/rules/engine.py src/database/persistence.py
git commit -m "feat: add score_detail and components_scored to scoring pipeline"
```

---

### Task 4: Update run_system.py for PostgreSQL

**Files:**
- Modify: `scripts/run_system.py`

- [ ] **Step 1: Pass use_postgres flag to Repository**

In `run_system.py`, where Repository is constructed, detect PG from the URL:

```python
database_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///data/atm.db")
use_postgres = "postgresql" in database_url
# ...
repo = Repository(session_factory, use_postgres=use_postgres)
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/ -x -q
```

- [ ] **Step 3: Commit**

```bash
git add scripts/run_system.py
git commit -m "feat: wire PostgreSQL detection into system runner"
```

---

## Chunk 2: Next.js Dashboard Scaffold

### Task 5: Initialize Next.js project

**Files:**
- Create: `dashboard/` directory with Next.js scaffold
- Create: `vercel.json`

- [ ] **Step 1: Create Next.js app**

```bash
cd /Users/shay/otc
npx create-next-app@latest dashboard \
  --typescript --tailwind --eslint --app \
  --src-dir --import-alias "@/*" \
  --no-turbopack
```

- [ ] **Step 2: Install dependencies**

```bash
cd /Users/shay/otc/dashboard
npm install pg swr
npm install -D @types/pg
```

- [ ] **Step 3: Create vercel.json at repo root**

Create `/Users/shay/otc/vercel.json`:
```json
{
  "rootDirectory": "dashboard"
}
```

- [ ] **Step 4: Create database connection pool**

Create `dashboard/src/lib/db.ts`:

```typescript
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 5,
  idleTimeoutMillis: 10000,
  connectionTimeoutMillis: 5000,
});

export default pool;
```

- [ ] **Step 5: Create shared types**

Create `dashboard/src/lib/types.ts`:

```typescript
export interface Candidate {
  id: number;
  ticker: string;
  price_tier: string;
  status: string;
  exchange: string;
  first_seen: string;
  atm_score: number | null;
  components_scored: number | null;
  score_detail: ScoreDetail | null;
  stability_score: number | null;
  l2_score: number | null;
  volume_score: number | null;
  dilution_score: number | null;
  ts_score: number | null;
}

export interface ScoreDetail {
  stability: ComponentScore;
  l2_imbalance: ComponentScore;
  no_bad_mm: ComponentScore;
  no_vol_anomaly: ComponentScore;
  consistent_vol: ComponentScore;
  bid_support: ComponentScore;
  ts_ratio: ComponentScore;
  dilution_clear: ComponentScore;
}

export interface ComponentScore {
  score: number;
  max: number;
  has_data: boolean;
}

export interface L2Snapshot {
  id: number;
  ticker: string;
  timestamp: string;
  bid_levels: L2Level[];
  ask_levels: L2Level[];
  imbalance_ratio: number | null;
  total_bid_shares: number | null;
  total_ask_shares: number | null;
}

export interface L2Level {
  price: string;
  size: number;
  mm_id: string;
}

export interface Trade {
  id: number;
  ticker: string;
  timestamp: string;
  price: string;
  size: number;
  side: string | null;
  mm_id: string | null;
}

export interface Alert {
  id: number;
  ticker: string;
  timestamp: string;
  alert_type: string;
  severity: string;
  message: string | null;
}

export interface HealthStatus {
  last_trade: string | null;
  last_l2: string | null;
  active_tickers: number;
  pending_tickers: number;
  engine_status: "connected" | "stale" | "disconnected";
}
```

- [ ] **Step 6: Create query functions**

Create `dashboard/src/lib/queries.ts`:

```typescript
import pool from "./db";
import type { Candidate, L2Snapshot, Trade, Alert, HealthStatus } from "./types";

export async function getCandidates(): Promise<Candidate[]> {
  const { rows } = await pool.query(`
    SELECT c.ticker, c.price_tier, c.status, c.exchange, c.first_seen,
           CAST(NULLIF(d.atm_score, '') AS FLOAT) as atm_score,
           d.components_scored, d.score_detail,
           CAST(NULLIF(d.stability_score, '') AS FLOAT) as stability_score,
           CAST(NULLIF(d.l2_score, '') AS FLOAT) as l2_score,
           CAST(NULLIF(d.volume_score, '') AS FLOAT) as volume_score,
           CAST(NULLIF(d.dilution_score, '') AS FLOAT) as dilution_score,
           CAST(NULLIF(d.ts_score, '') AS FLOAT) as ts_score
    FROM candidates c
    LEFT JOIN daily_scores d ON c.ticker = d.ticker
      AND d.date = (SELECT MAX(date) FROM daily_scores WHERE ticker = c.ticker)
    WHERE c.status != 'rejected'
    ORDER BY CAST(NULLIF(d.atm_score, '') AS FLOAT) DESC NULLS LAST
  `);
  return rows;
}

export async function addCandidate(ticker: string): Promise<boolean> {
  const result = await pool.query(
    `INSERT INTO candidates (ticker, price_tier, status, first_seen)
     VALUES ($1, 'UNKNOWN', 'manual', NOW())
     ON CONFLICT (ticker) DO NOTHING
     RETURNING id`,
    [ticker.toUpperCase().trim()]
  );
  return (result.rowCount ?? 0) > 0;
}

export async function getTickerData(symbol: string) {
  const [candidateRes, l2Res, tradesRes, alertsRes] = await Promise.all([
    pool.query(`
      SELECT c.*, CAST(NULLIF(d.atm_score, '') AS FLOAT) as atm_score,
             d.components_scored, d.score_detail,
             CAST(NULLIF(d.stability_score, '') AS FLOAT) as stability_score,
             CAST(NULLIF(d.l2_score, '') AS FLOAT) as l2_score,
             CAST(NULLIF(d.volume_score, '') AS FLOAT) as volume_score,
             CAST(NULLIF(d.dilution_score, '') AS FLOAT) as dilution_score,
             CAST(NULLIF(d.ts_score, '') AS FLOAT) as ts_score
      FROM candidates c
      LEFT JOIN daily_scores d ON c.ticker = d.ticker
        AND d.date = (SELECT MAX(date) FROM daily_scores WHERE ticker = c.ticker)
      WHERE c.ticker = $1
    `, [symbol]),
    pool.query(`
      SELECT * FROM l2_snapshots
      WHERE ticker = $1 ORDER BY timestamp DESC LIMIT 10
    `, [symbol]),
    pool.query(`
      SELECT * FROM trades
      WHERE ticker = $1 ORDER BY timestamp DESC LIMIT 50
    `, [symbol]),
    pool.query(`
      SELECT * FROM alerts
      WHERE ticker = $1 ORDER BY timestamp DESC LIMIT 10
    `, [symbol]),
  ]);

  return {
    candidate: candidateRes.rows[0] || null,
    l2_snapshots: l2Res.rows as L2Snapshot[],
    trades: tradesRes.rows as Trade[],
    alerts: alertsRes.rows as Alert[],
  };
}

export async function getAlerts(severity?: string, ticker?: string): Promise<Alert[]> {
  const conditions: string[] = [];
  const params: string[] = [];
  let idx = 1;

  if (severity) {
    conditions.push(`severity = $${idx++}`);
    params.push(severity);
  }
  if (ticker) {
    conditions.push(`ticker = $${idx++}`);
    params.push(ticker);
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
  const { rows } = await pool.query(
    `SELECT * FROM alerts ${where} ORDER BY timestamp DESC LIMIT 50`,
    params
  );
  return rows;
}

export async function getHealth(): Promise<HealthStatus> {
  const { rows } = await pool.query(`
    SELECT
      (SELECT MAX(timestamp) FROM trades) as last_trade,
      (SELECT MAX(timestamp) FROM l2_snapshots) as last_l2,
      (SELECT COUNT(*) FROM candidates WHERE status = 'active') as active_tickers,
      (SELECT COUNT(*) FROM candidates WHERE status = 'manual') as pending_tickers
  `);

  const row = rows[0];
  const lastActivity = row.last_trade > row.last_l2 ? row.last_trade : row.last_l2;
  const ageMs = lastActivity ? Date.now() - new Date(lastActivity).getTime() : Infinity;

  let engine_status: "connected" | "stale" | "disconnected";
  if (ageMs < 30_000) engine_status = "connected";
  else if (ageMs < 300_000) engine_status = "stale";
  else engine_status = "disconnected";

  return { ...row, engine_status };
}
```

- [ ] **Step 7: Commit**

```bash
git add dashboard/ vercel.json
git commit -m "feat: scaffold Next.js dashboard with PG connection and query layer"
```

---

### Task 6: API routes

**Files:**
- Create: `dashboard/src/app/api/candidates/route.ts`
- Create: `dashboard/src/app/api/ticker/[symbol]/route.ts`
- Create: `dashboard/src/app/api/alerts/route.ts`
- Create: `dashboard/src/app/api/health/route.ts`

- [ ] **Step 1: Candidates API (GET + POST)**

Create `dashboard/src/app/api/candidates/route.ts`:

```typescript
import { NextResponse } from "next/server";
import { getCandidates, addCandidate } from "@/lib/queries";

export async function GET() {
  try {
    const candidates = await getCandidates();
    return NextResponse.json(candidates);
  } catch (error) {
    console.error("Failed to fetch candidates:", error);
    return NextResponse.json({ error: "Database error" }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const { ticker } = await request.json();
    if (!ticker || typeof ticker !== "string") {
      return NextResponse.json({ error: "ticker is required" }, { status: 400 });
    }
    const created = await addCandidate(ticker);
    return NextResponse.json({ ticker: ticker.toUpperCase().trim(), created }, {
      status: created ? 201 : 200,
    });
  } catch (error) {
    console.error("Failed to add candidate:", error);
    return NextResponse.json({ error: "Database error" }, { status: 500 });
  }
}
```

- [ ] **Step 2: Ticker detail API**

Create `dashboard/src/app/api/ticker/[symbol]/route.ts`:

```typescript
import { NextResponse } from "next/server";
import { getTickerData } from "@/lib/queries";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  try {
    const { symbol } = await params;
    const data = await getTickerData(symbol.toUpperCase());
    if (!data.candidate) {
      return NextResponse.json({ error: "Ticker not found" }, { status: 404 });
    }
    return NextResponse.json(data);
  } catch (error) {
    console.error("Failed to fetch ticker data:", error);
    return NextResponse.json({ error: "Database error" }, { status: 500 });
  }
}
```

- [ ] **Step 3: Alerts API**

Create `dashboard/src/app/api/alerts/route.ts`:

```typescript
import { NextResponse } from "next/server";
import { getAlerts } from "@/lib/queries";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const severity = searchParams.get("severity") || undefined;
    const ticker = searchParams.get("ticker") || undefined;
    const alerts = await getAlerts(severity, ticker);
    return NextResponse.json(alerts);
  } catch (error) {
    console.error("Failed to fetch alerts:", error);
    return NextResponse.json({ error: "Database error" }, { status: 500 });
  }
}
```

- [ ] **Step 4: Health API**

Create `dashboard/src/app/api/health/route.ts`:

```typescript
import { NextResponse } from "next/server";
import { getHealth } from "@/lib/queries";

export async function GET() {
  try {
    const health = await getHealth();
    return NextResponse.json(health);
  } catch (error) {
    console.error("Health check failed:", error);
    return NextResponse.json(
      { engine_status: "disconnected", error: "Database unreachable" },
      { status: 503 }
    );
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/app/api/
git commit -m "feat: add API routes for candidates, ticker, alerts, health"
```

---

## Chunk 3: Dashboard UI Pages

### Task 7: Shared layout and components

**Files:**
- Modify: `dashboard/src/app/layout.tsx`
- Modify: `dashboard/src/app/globals.css`
- Create: `dashboard/src/lib/hooks.ts`
- Create: `dashboard/src/components/ConnectionStatus.tsx`
- Create: `dashboard/src/components/ScoreBar.tsx`
- Create: `dashboard/src/components/StatusBadge.tsx`
- Create: `dashboard/src/components/Sidebar.tsx`

- [ ] **Step 1: Set up dark theme globals**

Replace `dashboard/src/app/globals.css` with dark-first theme:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bg-primary: #0a0a0f;
  --bg-secondary: #12121a;
  --bg-card: #1a1a2e;
  --border: #2a2a3e;
  --text-primary: #e4e4e7;
  --text-secondary: #a1a1aa;
  --accent-green: #22c55e;
  --accent-yellow: #eab308;
  --accent-red: #ef4444;
  --accent-blue: #3b82f6;
}

body {
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
}
```

- [ ] **Step 2: Create SWR hooks**

Create `dashboard/src/lib/hooks.ts`:

```typescript
import useSWR from "swr";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function useCandidates() {
  return useSWR("/api/candidates", fetcher, { refreshInterval: 5000 });
}

export function useTicker(symbol: string) {
  return useSWR(`/api/ticker/${symbol}`, fetcher, { refreshInterval: 5000 });
}

export function useAlerts(severity?: string, ticker?: string) {
  const params = new URLSearchParams();
  if (severity) params.set("severity", severity);
  if (ticker) params.set("ticker", ticker);
  const qs = params.toString();
  return useSWR(`/api/alerts${qs ? `?${qs}` : ""}`, fetcher, { refreshInterval: 5000 });
}

export function useHealth() {
  return useSWR("/api/health", fetcher, { refreshInterval: 5000 });
}
```

- [ ] **Step 3: Create ScoreBar component**

Create `dashboard/src/components/ScoreBar.tsx`:

```tsx
interface ScoreBarProps {
  score: number | null;
  max?: number;
  completeness?: number | null;
}

export default function ScoreBar({ score, max = 100, completeness }: ScoreBarProps) {
  if (score === null) return <span className="text-zinc-600">--</span>;

  const pct = (score / max) * 100;
  const color = score >= 80 ? "bg-green-500" : score >= 70 ? "bg-yellow-500" : "bg-zinc-600";
  const label = score >= 80 ? "TRADE" : score >= 70 ? "WATCHLIST" : "PASS";

  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-2 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm font-mono">{score}</span>
      <span className={`text-xs px-1.5 py-0.5 rounded ${
        score >= 80 ? "bg-green-500/20 text-green-400" :
        score >= 70 ? "bg-yellow-500/20 text-yellow-400" :
        "bg-zinc-700/50 text-zinc-400"
      }`}>{label}</span>
      {completeness !== null && completeness !== undefined && (
        <span className="text-xs text-zinc-500">{completeness}/8</span>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Create StatusBadge component**

Create `dashboard/src/components/StatusBadge.tsx`:

```tsx
const STATUS_COLORS: Record<string, string> = {
  active: "bg-green-500/20 text-green-400",
  manual: "bg-blue-500/20 text-blue-400",
  rejected: "bg-red-500/20 text-red-400",
  watching: "bg-yellow-500/20 text-yellow-400",
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_COLORS[status] || "bg-zinc-700 text-zinc-400"}`}>
      {status}
    </span>
  );
}
```

- [ ] **Step 5: Create ConnectionStatus component**

Create `dashboard/src/components/ConnectionStatus.tsx`:

```tsx
"use client";
import { useHealth } from "@/lib/hooks";

export default function ConnectionStatus() {
  const { data } = useHealth();
  const status = data?.engine_status || "disconnected";

  const configs = {
    connected: { color: "bg-green-500", label: "Engine Connected" },
    stale: { color: "bg-yellow-500", label: "Engine Stale" },
    disconnected: { color: "bg-red-500", label: "Engine Offline" },
  };
  const config = configs[status] || configs.disconnected;

  return (
    <div className="flex items-center gap-2 text-sm">
      <div className={`w-2 h-2 rounded-full ${config.color} animate-pulse`} />
      <span className="text-zinc-400">{config.label}</span>
      {data && (
        <span className="text-zinc-600 text-xs">
          {data.active_tickers} active / {data.pending_tickers} pending
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Create Sidebar**

Create `dashboard/src/components/Sidebar.tsx`:

```tsx
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import ConnectionStatus from "./ConnectionStatus";

const NAV_ITEMS = [
  { href: "/", label: "Watchlist" },
  { href: "/alerts", label: "Alerts" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 h-screen bg-[var(--bg-secondary)] border-r border-[var(--border)] flex flex-col p-4 fixed">
      <div className="mb-8">
        <h1 className="text-lg font-bold tracking-tight">ATM Engine</h1>
        <p className="text-xs text-zinc-500 mt-1">OTC Decision Support</p>
      </div>
      <nav className="flex flex-col gap-1">
        {NAV_ITEMS.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={`px-3 py-2 rounded-md text-sm ${
              pathname === href
                ? "bg-[var(--bg-card)] text-white"
                : "text-zinc-400 hover:text-white hover:bg-[var(--bg-card)]/50"
            }`}
          >
            {label}
          </Link>
        ))}
      </nav>
      <div className="mt-auto">
        <ConnectionStatus />
      </div>
    </aside>
  );
}
```

- [ ] **Step 7: Update layout.tsx**

Replace `dashboard/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "ATM Engine",
  description: "OTC penny stock decision support",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <div className="flex">
          <Sidebar />
          <main className="ml-56 flex-1 min-h-screen p-6">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
```

- [ ] **Step 8: Commit**

```bash
cd /Users/shay/otc
git add dashboard/
git commit -m "feat: add dashboard layout, dark theme, shared components, SWR hooks"
```

---

### Task 8: Watchlist page (home)

**Files:**
- Modify: `dashboard/src/app/page.tsx`
- Create: `dashboard/src/components/AddTickerInput.tsx`

- [ ] **Step 1: Create AddTickerInput**

Create `dashboard/src/components/AddTickerInput.tsx`:

```tsx
"use client";
import { useState } from "react";
import { mutate } from "swr";

export default function AddTickerInput() {
  const [ticker, setTicker] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ticker.trim()) return;
    setLoading(true);
    try {
      await fetch("/api/candidates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: ticker.trim() }),
      });
      mutate("/api/candidates");
      setTicker("");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={ticker}
        onChange={(e) => setTicker(e.target.value.toUpperCase())}
        placeholder="Enter ticker..."
        className="bg-[var(--bg-card)] border border-[var(--border)] rounded-md px-3 py-1.5 text-sm font-mono focus:outline-none focus:border-blue-500 w-40"
      />
      <button
        type="submit"
        disabled={loading || !ticker.trim()}
        className="bg-blue-600 hover:bg-blue-700 disabled:bg-zinc-700 text-white text-sm px-4 py-1.5 rounded-md transition-colors"
      >
        {loading ? "..." : "Add"}
      </button>
    </form>
  );
}
```

- [ ] **Step 2: Create Watchlist page**

Replace `dashboard/src/app/page.tsx`:

```tsx
"use client";
import Link from "next/link";
import { useCandidates } from "@/lib/hooks";
import AddTickerInput from "@/components/AddTickerInput";
import ScoreBar from "@/components/ScoreBar";
import StatusBadge from "@/components/StatusBadge";

export default function WatchlistPage() {
  const { data: candidates, isLoading } = useCandidates();

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">Watchlist</h2>
        <AddTickerInput />
      </div>

      {isLoading ? (
        <div className="text-zinc-500">Loading...</div>
      ) : (
        <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] text-zinc-400 text-left">
                <th className="px-4 py-3 font-medium">Ticker</th>
                <th className="px-4 py-3 font-medium">Tier</th>
                <th className="px-4 py-3 font-medium">Score</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Exchange</th>
              </tr>
            </thead>
            <tbody>
              {(candidates || []).map((c: any) => (
                <tr
                  key={c.ticker}
                  className="border-b border-[var(--border)] hover:bg-[var(--bg-card)] transition-colors"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/ticker/${c.ticker}`}
                      className="font-mono font-bold text-blue-400 hover:text-blue-300"
                    >
                      {c.ticker}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs bg-zinc-800 px-2 py-0.5 rounded">
                      {c.price_tier}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <ScoreBar
                      score={c.atm_score}
                      completeness={c.components_scored}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={c.status} />
                  </td>
                  <td className="px-4 py-3 text-zinc-400 font-mono text-xs">
                    {c.exchange}
                  </td>
                </tr>
              ))}
              {(!candidates || candidates.length === 0) && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-zinc-500">
                    No candidates yet. Add a ticker to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/
git commit -m "feat: add watchlist page with add ticker input and score table"
```

---

### Task 9: Ticker Detail page

**Files:**
- Create: `dashboard/src/app/ticker/[symbol]/page.tsx`
- Create: `dashboard/src/components/ScoreBreakdown.tsx`
- Create: `dashboard/src/components/L2DepthPanel.tsx`
- Create: `dashboard/src/components/TSFeed.tsx`
- Create: `dashboard/src/components/ATMPlan.tsx`

- [ ] **Step 1: Create ScoreBreakdown**

Create `dashboard/src/components/ScoreBreakdown.tsx`:

```tsx
import type { ScoreDetail } from "@/lib/types";

const LABELS: Record<string, string> = {
  stability: "Range Stability (30d)",
  l2_imbalance: "L2 Imbalance",
  no_bad_mm: "No Bad MMs on Ask",
  no_vol_anomaly: "No Volume Anomaly",
  consistent_vol: "Consistent Volume",
  bid_support: "Bid Support",
  ts_ratio: "T&S Ratio Bullish",
  dilution_clear: "Dilution Clear",
};

export default function ScoreBreakdown({ detail }: { detail: ScoreDetail | null }) {
  if (!detail) return <div className="text-zinc-500">No score data</div>;

  return (
    <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-lg p-4">
      <h3 className="text-sm font-bold mb-3 text-zinc-300">Score Breakdown</h3>
      <div className="space-y-2">
        {Object.entries(detail).map(([key, comp]) => (
          <div key={key} className="flex items-center justify-between text-sm">
            <span className={comp.has_data ? "text-zinc-300" : "text-zinc-600"}>
              {LABELS[key] || key}
            </span>
            <div className="flex items-center gap-2">
              <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    !comp.has_data ? "bg-zinc-700" :
                    comp.score === comp.max ? "bg-green-500" :
                    comp.score > 0 ? "bg-yellow-500" : "bg-red-500"
                  }`}
                  style={{ width: `${(comp.score / comp.max) * 100}%` }}
                />
              </div>
              <span className="font-mono w-12 text-right">
                {comp.score}/{comp.max}
              </span>
              {!comp.has_data && (
                <span className="text-xs text-zinc-600">no data</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create L2DepthPanel**

Create `dashboard/src/components/L2DepthPanel.tsx`:

```tsx
import type { L2Snapshot } from "@/lib/types";

const BAD_MMS = new Set([
  "MAXM", "GLED", "CFGN", "PAUL", "JANE", "BBAR", "BLAS",
  "ALPS", "STXG", "AEXG", "VFIN", "VERT", "BMAK",
]);

function formatSize(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

export default function L2DepthPanel({ snapshot }: { snapshot: L2Snapshot | null }) {
  if (!snapshot) return <div className="text-zinc-500">No L2 data</div>;

  const ratio = snapshot.total_bid_shares && snapshot.total_ask_shares
    ? (snapshot.total_bid_shares / snapshot.total_ask_shares).toFixed(1)
    : "--";

  return (
    <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-zinc-300">L2 Depth</h3>
        <span className="text-xs text-zinc-400">
          Ratio: <span className="font-mono font-bold text-white">{ratio}:1</span>
          {" "}({formatSize(snapshot.total_bid_shares || 0)} bid / {formatSize(snapshot.total_ask_shares || 0)} ask)
        </span>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs text-green-400 font-bold mb-2">BIDS</div>
          {(snapshot.bid_levels || []).map((level, i) => (
            <div key={i} className="flex justify-between text-xs py-0.5 font-mono">
              <span className="text-zinc-400">{level.mm_id || "?"}</span>
              <span className="text-green-400">{formatSize(level.size)}</span>
              <span className="text-zinc-500">{level.price}</span>
            </div>
          ))}
        </div>
        <div>
          <div className="text-xs text-red-400 font-bold mb-2">ASKS</div>
          {(snapshot.ask_levels || []).map((level, i) => (
            <div key={i} className="flex justify-between text-xs py-0.5 font-mono">
              <span className="text-zinc-500">{level.price}</span>
              <span className="text-red-400">{formatSize(level.size)}</span>
              <span className={BAD_MMS.has(level.mm_id) ? "text-red-500 font-bold" : "text-zinc-400"}>
                {level.mm_id || "?"}
                {BAD_MMS.has(level.mm_id) && " !!"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create TSFeed**

Create `dashboard/src/components/TSFeed.tsx`:

```tsx
import type { Trade } from "@/lib/types";

export default function TSFeed({ trades }: { trades: Trade[] }) {
  if (!trades.length) return <div className="text-zinc-500">No trades</div>;

  return (
    <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-lg p-4">
      <h3 className="text-sm font-bold mb-3 text-zinc-300">Time & Sales</h3>
      <div className="max-h-48 overflow-y-auto space-y-0.5">
        {trades.map((t) => (
          <div key={t.id} className="flex justify-between text-xs font-mono py-0.5">
            <span className="text-zinc-500 w-20">
              {new Date(t.timestamp).toLocaleTimeString()}
            </span>
            <span className={
              t.side === "ask" ? "text-green-400" :
              t.side === "bid" ? "text-red-400" :
              "text-zinc-400"
            }>
              {t.side || "?"}
            </span>
            <span className="text-zinc-300">{Number(t.size).toLocaleString()}</span>
            <span className="text-zinc-400">${t.price}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create ATMPlan**

Create `dashboard/src/components/ATMPlan.tsx`:

```tsx
import type { Candidate, ScoreDetail } from "@/lib/types";

const HOLD_TIMES: Record<string, string> = {
  TRIP_ZERO: "4h intraday / 2d overnight",
  TRIPS: "4h intraday / 2d overnight",
  LOW_DUBS: "2 days",
  DUBS: "2 days",
  PENNIES: "5 days max",
};

const PORTFOLIO_VALUE = 10000; // default, could come from settings API later
const MAX_POSITION_PCT = 0.05;
const MAX_LOSS_PCT = 0.02;

interface ATMPlanProps {
  candidate: Candidate;
  bidPrice: string | null;
}

export default function ATMPlan({ candidate, bidPrice }: ATMPlanProps) {
  const score = candidate.atm_score;
  const tier = candidate.price_tier;
  const price = bidPrice ? parseFloat(bidPrice) : null;

  const positionValue = PORTFOLIO_VALUE * MAX_POSITION_PCT;
  const shares = price && price > 0 ? Math.floor(positionValue / price) : null;
  const maxLoss = PORTFOLIO_VALUE * MAX_LOSS_PCT;
  const holdTime = HOLD_TIMES[tier] || "Unknown";

  const action = score !== null && score >= 80 ? "TRADE" : score !== null && score >= 70 ? "WATCHLIST" : "PASS";

  return (
    <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-lg p-4">
      <h3 className="text-sm font-bold mb-3 text-zinc-300">ATM Plan</h3>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-zinc-500 text-xs">Signal</div>
          <div className={`font-bold ${
            action === "TRADE" ? "text-green-400" :
            action === "WATCHLIST" ? "text-yellow-400" : "text-zinc-400"
          }`}>{action}</div>
        </div>
        <div>
          <div className="text-zinc-500 text-xs">Entry Price</div>
          <div className="font-mono">{bidPrice ? `$${bidPrice}` : "--"}</div>
        </div>
        <div>
          <div className="text-zinc-500 text-xs">Position Size</div>
          <div className="font-mono">
            {shares ? `${shares.toLocaleString()} shares ($${positionValue})` : "--"}
          </div>
        </div>
        <div>
          <div className="text-zinc-500 text-xs">Max Loss</div>
          <div className="font-mono text-red-400">${maxLoss}</div>
        </div>
        <div>
          <div className="text-zinc-500 text-xs">Est. Hold Time</div>
          <div>{holdTime}</div>
        </div>
        <div>
          <div className="text-zinc-500 text-xs">Dilution</div>
          {(() => {
            const dil = candidate.score_detail?.dilution_clear;
            if (!dil) return <div className="text-zinc-500">--</div>;
            if (!dil.has_data) return <div className="text-zinc-500">No data</div>;
            return (
              <div className={dil.score >= 10 ? "text-green-400" : "text-red-400"}>
                {dil.score >= 10 ? "Clear" : "Detected"}
              </div>
            );
          })()}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create Ticker Detail page**

Create `dashboard/src/app/ticker/[symbol]/page.tsx`:

```tsx
"use client";
import { use } from "react";
import Link from "next/link";
import { useTicker } from "@/lib/hooks";
import ScoreBar from "@/components/ScoreBar";
import ScoreBreakdown from "@/components/ScoreBreakdown";
import L2DepthPanel from "@/components/L2DepthPanel";
import TSFeed from "@/components/TSFeed";
import ATMPlan from "@/components/ATMPlan";

export default function TickerDetailPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = use(params);
  const { data, isLoading } = useTicker(symbol);

  if (isLoading) return <div className="text-zinc-500">Loading {symbol}...</div>;
  if (!data?.candidate) return <div className="text-zinc-500">Ticker {symbol} not found.</div>;

  const { candidate, l2_snapshots, trades, alerts } = data;
  const latestL2 = l2_snapshots[0] || null;
  const bidPrice = latestL2?.bid_levels?.[0]?.price || null;

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <Link href="/" className="text-zinc-500 hover:text-zinc-300 text-sm">&larr; Back</Link>
        <h2 className="text-xl font-bold font-mono">{symbol}</h2>
        <span className="text-xs bg-zinc-800 px-2 py-0.5 rounded">{candidate.price_tier}</span>
        <ScoreBar score={candidate.atm_score} completeness={candidate.components_scored} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ScoreBreakdown detail={candidate.score_detail} />
        <ATMPlan candidate={candidate} bidPrice={bidPrice} />
        <L2DepthPanel snapshot={latestL2} />
        <TSFeed trades={trades} />
      </div>

      {alerts.length > 0 && (
        <div className="mt-4 bg-[var(--bg-card)] border border-[var(--border)] rounded-lg p-4">
          <h3 className="text-sm font-bold mb-2 text-zinc-300">Alerts</h3>
          {alerts.map((a: any) => (
            <div key={a.id} className="flex gap-3 text-xs py-1 border-b border-[var(--border)] last:border-0">
              <span className={`px-1.5 py-0.5 rounded ${
                a.severity === "CRITICAL" ? "bg-red-500/20 text-red-400" :
                a.severity === "HIGH" ? "bg-orange-500/20 text-orange-400" :
                a.severity === "WARNING" ? "bg-yellow-500/20 text-yellow-400" :
                "bg-zinc-700/50 text-zinc-400"
              }`}>{a.severity}</span>
              <span className="text-zinc-400">{a.alert_type}</span>
              <span className="text-zinc-300">{a.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/
git commit -m "feat: add ticker detail page with score breakdown, L2 depth, T&S, ATM plan"
```

---

### Task 10: Alerts page

**Files:**
- Create: `dashboard/src/app/alerts/page.tsx`

- [ ] **Step 1: Create Alerts page**

Create `dashboard/src/app/alerts/page.tsx`:

```tsx
"use client";
import { useAlerts } from "@/lib/hooks";
import Link from "next/link";

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "bg-red-500/20 text-red-400",
  HIGH: "bg-orange-500/20 text-orange-400",
  WARNING: "bg-yellow-500/20 text-yellow-400",
  INFO: "bg-zinc-700/50 text-zinc-400",
};

export default function AlertsPage() {
  const { data: alerts, isLoading } = useAlerts();

  return (
    <div>
      <h2 className="text-xl font-bold mb-6">Alerts</h2>

      {isLoading ? (
        <div className="text-zinc-500">Loading...</div>
      ) : (
        <div className="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg overflow-hidden">
          {(alerts || []).length === 0 ? (
            <div className="px-4 py-8 text-center text-zinc-500">No alerts.</div>
          ) : (
            <div className="divide-y divide-[var(--border)]">
              {(alerts || []).map((a: any) => (
                <div key={a.id} className="flex items-center gap-4 px-4 py-3 text-sm">
                  <span className="text-zinc-500 text-xs font-mono w-20">
                    {new Date(a.timestamp).toLocaleTimeString()}
                  </span>
                  <span className={`px-2 py-0.5 rounded text-xs ${SEVERITY_COLORS[a.severity] || ""}`}>
                    {a.severity}
                  </span>
                  <Link href={`/ticker/${a.ticker}`} className="font-mono text-blue-400 hover:text-blue-300">
                    {a.ticker}
                  </Link>
                  <span className="text-zinc-400 text-xs">{a.alert_type}</span>
                  <span className="text-zinc-300 flex-1">{a.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/src/app/alerts/
git commit -m "feat: add alerts page with severity filtering"
```

---

## Chunk 4: Deploy & Verify

### Task 11: Deploy to Vercel

**Files:**
- Create: `dashboard/.env.local` (gitignored)
- Modify: `dashboard/.gitignore`

- [ ] **Step 1: Add DATABASE_URL to dashboard .env.local**

```bash
# Get the Railway PG URL (without the +asyncpg driver prefix)
# Railway URL: postgresql://user:pass@host:port/db
echo "DATABASE_URL=postgresql://user:pass@host.railway.app:5432/railway" > dashboard/.env.local
```

- [ ] **Step 2: Ensure .env.local is gitignored**

Check `dashboard/.gitignore` includes `.env.local` (Next.js default does this).

- [ ] **Step 3: Test locally**

```bash
cd /Users/shay/otc/dashboard
npm run dev
```

Open http://localhost:3000 — verify:
- Watchlist shows (empty or with data if engine has run)
- Add ticker input works (inserts to PG)
- Connection status shows engine state
- Click ticker navigates to detail page

- [ ] **Step 4: Deploy to Vercel**

```bash
cd /Users/shay/otc
vercel link  # link to new project
vercel env add DATABASE_URL  # paste Railway PG URL (postgresql:// format)
vercel --prod
```

- [ ] **Step 5: Enable Vercel password protection**

In Vercel dashboard → Project Settings → General → Password Protection → Enable.
Set a shared password for Shay and Eldar. This locks the entire app behind a password without code changes.

- [ ] **Step 6: Verify on Vercel**

Open the Vercel URL — enter password, then verify:
- Watchlist shows (empty or with data if engine has run)
- Add ticker input works
- Connection status shows engine state
- Both Shay and Eldar can access the same URL with the password

- [ ] **Step 7: Commit any remaining changes**

```bash
git add -A
git commit -m "feat: complete dashboard deployment configuration"
```

---

### Task 12: Wire engine to Railway PG and end-to-end test

- [ ] **Step 1: Update engine .env on Eldar's machine**

```
DATABASE_URL=postgresql+asyncpg://user:pass@host.railway.app:5432/railway
```

- [ ] **Step 2: Run engine**

```bash
python scripts/run_system.py
```

Verify: engine connects to Railway PG, creates tables if needed, starts TickerWatcher.

- [ ] **Step 3: Add a ticker from the Vercel dashboard**

Type "MWWC" in the Add Ticker input on the Vercel URL. Verify it appears in the watchlist as `manual` status.

- [ ] **Step 4: Watch TickerWatcher pick it up**

On Eldar's machine, engine logs should show:
```
ticker_activating ticker=MWWC
contract_qualified ticker=MWWC exchange=SMART
ticker_activated ticker=MWWC status=active
```

- [ ] **Step 5: Verify data flows to dashboard**

On the Vercel URL:
- MWWC status changes from `manual` to `active`
- Score appears and climbs as data accumulates
- Click into MWWC — see L2 depth, T&S, score breakdown
- Connection status shows "Engine Connected"

- [ ] **Step 6: Final commit and push**

```bash
git add -A
git commit -m "feat: complete OTC dashboard rebuild — shared environment on Vercel + Railway PG"
git push origin main
```
