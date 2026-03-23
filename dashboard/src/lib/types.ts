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
