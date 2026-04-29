/** Hebrew translations for ATM Engine dashboard tooltips. */

export const tips = {
  // Score components
  stability: { en: "Range Stability (30d)", he: "יציבות טווח — 30 יום" },
  l2_imbalance: { en: "L2 Bid/Ask Imbalance", he: "יחס ביקוש/היצע בספר הפקודות" },
  no_bad_mm: { en: "No Bad Market Makers on Ask", he: "אין עושי שוק מסוכנים בצד המכירה" },
  no_vol_anomaly: { en: "No Volume Anomaly", he: "אין חריגה בנפח מסחר" },
  consistent_vol: { en: "Consistent Daily Volume", he: "נפח מסחר יומי עקבי" },
  bid_support: { en: "Bid Support Below Entry", he: "תמיכה בביקוש מתחת לכניסה" },
  ts_ratio: { en: "Time & Sales Ratio Bullish", he: "יחס קניות/מכירות חיובי" },
  dilution_clear: { en: "No Dilution Detected", he: "לא זוהה דילול מניות" },

  // Page labels
  watchlist: { en: "Watchlist", he: "רשימת מעקב" },
  alerts: { en: "Alerts", he: "התראות" },
  scanner: { en: "Scanner", he: "סורק אוטומטי" },
  score: { en: "ATM Score", he: "ציון ATM — דירוג כללי של ההזדמנות" },
  tier: { en: "Price Tier", he: "טווח מחיר — TRIPS/DUBS/PENNIES" },
  l2_depth: { en: "L2 Depth", he: "עומק שוק ברמה 2 — ביקוש והיצע" },
  ts_feed: { en: "Time & Sales", he: "עסקאות בזמן אמת" },
  atm_plan: { en: "ATM Plan", he: "תוכנית מסחר — כניסה, גודל, סטופ" },
  imbalance: { en: "Bid/Ask Ratio", he: "יחס ביקוש/היצע — מעל 3:1 = חיובי" },
  bad_mm: { en: "Bad Market Maker", he: "עושה שוק מסוכן — סימן לדילול" },
  signal_trade: { en: "TRADE Signal", he: "ציון 80+ — מתאים למסחר" },
  signal_watch: { en: "WATCHLIST Signal", he: "ציון 70-79 — במעקב" },
  signal_pass: { en: "PASS", he: "ציון מתחת 70 — לא מתאים כרגע" },
  engine_status: { en: "Engine Status", he: "סטטוס מנוע — חיבור לשרת IBKR" },
  scanner_status: { en: "Scanner Status", he: "סורק — מחפש מניות חדשות כל 15 דקות" },
  source_scanner: { en: "Found by Scanner", he: "נמצא אוטומטית ע״י הסורק" },
  source_manual: { en: "Added Manually", he: "נוסף ידנית" },
  position_size: { en: "Position Size", he: "גודל פוזיציה — 5% מהתיק" },
  max_loss: { en: "Max Loss", he: "הפסד מקסימלי — 2% מהתיק" },
  hold_time: { en: "Max Hold Time", he: "זמן החזקה מקסימלי" },
} as const;

export type TipKey = keyof typeof tips;
