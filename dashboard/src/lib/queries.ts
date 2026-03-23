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
