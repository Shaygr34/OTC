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
