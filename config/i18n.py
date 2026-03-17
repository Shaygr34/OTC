"""Internationalization — English / Hebrew string mappings.

Usage:
    from config.i18n import t, get_lang, set_lang

    t("page.overview")  →  "Overview" or "סקירה"
"""

from __future__ import annotations

_current_lang: str = "en"

_STRINGS: dict[str, dict[str, str]] = {
    # ── Page names ──
    "page.overview": {"en": "Overview", "he": "סקירה"},
    "page.detail": {"en": "Stock Detail", "he": "פרטי מניה"},
    "page.trade_log": {"en": "Trade Log", "he": "יומן עסקאות"},
    "page.settings": {"en": "Settings", "he": "הגדרות"},

    # ── Status ──
    "status.connected": {"en": "Connected", "he": "מחובר"},
    "status.disconnected": {"en": "Disconnected", "he": "מנותק"},
    "status.active": {"en": "Active", "he": "פעיל"},
    "status.paused": {"en": "Paused", "he": "מושהה"},
    "status.live": {"en": "LIVE", "he": "פעיל"},
    "status.no_data": {"en": "NO DATA", "he": "אין נתונים"},
    "status.manual": {"en": "MANUAL", "he": "ידני"},
    "status.removed": {"en": "Removed", "he": "הוסר"},

    # ── Actions ──
    "action.save": {"en": "Save", "he": "שמור"},
    "action.test": {"en": "Test", "he": "בדוק"},
    "action.add": {"en": "Add", "he": "הוסף"},
    "action.remove": {"en": "Remove", "he": "הסר"},
    "action.close": {"en": "Close", "he": "סגור"},
    "action.pause": {"en": "Pause", "he": "השהה"},
    "action.prioritize": {"en": "Prioritize", "he": "תעדף"},
    "action.test_connection": {"en": "Test Connection", "he": "בדוק חיבור"},
    "action.send_test_ping": {"en": "Send Test Ping", "he": "שלח הודעת בדיקה"},
    "action.add_ticker": {"en": "Add Ticker", "he": "הוסף מניה"},
    "action.manage_candidates": {"en": "Manage Candidates", "he": "נהל מניות"},
    "action.close_position": {"en": "Close Position", "he": "סגור פוזיציה"},

    # ── Alerts ──
    "alert.volume_anomaly": {"en": "Volume Anomaly", "he": "חריגת ווליום"},
    "alert.dilution": {"en": "Dilution", "he": "דילול"},
    "alert.bid_collapse": {"en": "Bid Collapse", "he": "קריסת ביד"},
    "alert.ratio_change": {"en": "Ratio Change", "he": "שינוי יחס"},

    # ── Scores ──
    "score.atm_score": {"en": "ATM Score", "he": "ציון כספומט"},
    "score.l2_imbalance": {"en": "L2 Imbalance", "he": "יחס חוסר איזון"},
    "score.dilution_score": {"en": "Dilution Score", "he": "ציון דילול"},
    "score.stability": {"en": "Stability", "he": "יציבות"},
    "score.volume": {"en": "Volume", "he": "ווליום"},
    "score.ts_ratio": {"en": "T&S Ratio", "he": "יחס עסקאות"},
    "score.l2_imbalance_desc": {
        "en": "Bid vs ask share ratio",
        "he": "יחס חוסר איזון בין קונים למוכרים",
    },

    # ── Trade log ──
    "trade.entry": {"en": "Entry", "he": "כניסה"},
    "trade.exit": {"en": "Exit", "he": "יציאה"},
    "trade.pnl": {"en": "P&L", "he": "רווח-הפסד"},
    "trade.win_rate": {"en": "Win Rate", "he": "אחוז הצלחה"},
    "trade.hold_time": {"en": "Hold Time", "he": "זמן החזקה"},
    "trade.side_buy": {"en": "Buy", "he": "קנייה"},
    "trade.side_sell": {"en": "Sell", "he": "מכירה"},
    "trade.shares": {"en": "Shares", "he": "מניות"},
    "trade.price": {"en": "Price", "he": "מחיר"},
    "trade.notes": {"en": "Notes", "he": "הערות"},
    "trade.ticker": {"en": "Ticker", "he": "מניה"},
    "trade.total_trades": {"en": "Total Trades", "he": "סה״כ עסקאות"},
    "trade.avg_pnl": {"en": "Avg P&L", "he": "רווח ממוצע"},
    "trade.total_pnl": {"en": "Total P&L", "he": "סה״כ רווח"},
    "trade.active_positions": {"en": "Active Positions", "he": "פוזיציות פתוחות"},
    "trade.history": {"en": "Trade History", "he": "היסטוריית עסקאות"},
    "trade.correlation": {"en": "Score vs Outcome", "he": "ציון מול תוצאה"},
    "trade.exit_reason": {"en": "Exit Reason", "he": "סיבת יציאה"},

    # ── Risk ──
    "risk.position_size": {"en": "Position Size", "he": "גודל פוזיציה"},
    "risk.max_loss": {"en": "Max Loss", "he": "הפסד מקסימלי"},
    "risk.stop_conditions": {"en": "Stop Conditions", "he": "תנאי עצירה"},
    "risk.portfolio_value": {"en": "Portfolio Value", "he": "ערך תיק"},

    # ── Settings ──
    "settings.ibkr_connection": {"en": "IBKR Connection", "he": "חיבור IBKR"},
    "settings.telegram_alerts": {"en": "Telegram Alerts", "he": "התראות טלגרם"},
    "settings.risk_params": {"en": "Risk Parameters", "he": "פרמטרים של סיכון"},
    "settings.system_status": {"en": "System Status", "he": "סטטוס מערכת"},
    "settings.language": {"en": "Language / שפה", "he": "שפה / Language"},
    "settings.host": {"en": "Host", "he": "כתובת"},
    "settings.port": {"en": "Port", "he": "פורט"},
    "settings.client_id": {"en": "Client ID", "he": "מזהה לקוח"},
    "settings.bot_token": {"en": "Bot Token", "he": "טוקן בוט"},
    "settings.chat_id": {"en": "Chat ID", "he": "מזהה צ׳אט"},
    "settings.not_configured": {"en": "Not configured", "he": "לא מוגדר"},
    "settings.saved": {"en": "Settings saved!", "he": "ההגדרות נשמרו!"},
    "settings.max_hold_trips": {"en": "Max Hold (TRIPS) hours", "he": "זמן החזקה מקסימלי (TRIPS) שעות"},
    "settings.max_hold_dubs": {"en": "Max Hold (DUBS) days", "he": "זמן החזקה מקסימלי (DUBS) ימים"},
    "settings.max_hold_pennies": {"en": "Max Hold (PENNIES) days", "he": "זמן החזקה מקסימלי (PENNIES) ימים"},
    "settings.ohi_strong": {"en": "OHI Strong (≥)", "he": "OHI חזק (≥)"},
    "settings.ohi_neutral": {"en": "OHI Neutral (≥)", "he": "OHI ניטרלי (≥)"},
    "settings.atm_trade": {"en": "ATM Trade (≥)", "he": "ציון מסחר (≥)"},
    "settings.atm_watchlist": {"en": "ATM Watchlist (≥)", "he": "ציון מעקב (≥)"},
    "settings.l2_min": {"en": "L2 Imbalance Min", "he": "חוסר איזון L2 מינימלי"},
    "settings.dilution_exit": {"en": "Dilution Exit (≥)", "he": "סף יציאה דילול (≥)"},
    "settings.db_size": {"en": "Database Size", "he": "גודל מסד נתונים"},
    "settings.candidates_count": {"en": "Active Candidates", "he": "מועמדים פעילים"},
    "settings.last_scan": {"en": "Last Scan", "he": "סריקה אחרונה"},

    # ── Section headers ──
    "section.candidates": {"en": "Candidates", "he": "מועמדים"},
    "section.alerts": {"en": "Recent Alerts", "he": "התראות אחרונות"},
    "section.l2_depth": {"en": "L2 Depth", "he": "עומק L2"},
    "section.trade_activity": {"en": "Trade Activity", "he": "פעילות מסחר"},
    "section.component_scores": {"en": "Component Scores", "he": "ציונים לפי רכיב"},

    # ── Wizard ──
    "wizard.welcome_title": {"en": "ATM Engine Setup", "he": "הגדרת מערכת הכספומט"},
    "wizard.welcome_body": {
        "en": "Welcome! Let's set up your trading engine in a few steps.",
        "he": "ברוכים הבאים! בואו נגדיר את מערכת המסחר בכמה שלבים.",
    },
    "wizard.step_language": {"en": "Choose Language", "he": "בחר שפה"},
    "wizard.step_ibkr": {"en": "IBKR Connection", "he": "חיבור IBKR"},
    "wizard.step_telegram": {"en": "Telegram Alerts", "he": "התראות טלגרם"},
    "wizard.step_risk": {"en": "Risk Defaults", "he": "ברירות מחדל סיכון"},
    "wizard.step_done": {"en": "System Ready", "he": "המערכת מוכנה"},
    "wizard.next": {"en": "Next", "he": "הבא"},
    "wizard.back": {"en": "Back", "he": "חזור"},
    "wizard.skip": {"en": "Skip", "he": "דלג"},
    "wizard.finish": {"en": "Enter Dashboard", "he": "כניסה לדשבורד"},

    # ── Misc ──
    "misc.no_db": {
        "en": "No database found. Start the engine to see data.",
        "he": "לא נמצא מסד נתונים. הפעל את המנוע כדי לראות נתונים.",
    },
    "misc.no_candidates": {
        "en": "No candidates yet. Start the engine and push market data.",
        "he": "אין מועמדים עדיין. הפעל את המנוע ושלח נתוני שוק.",
    },
    "misc.no_alerts": {"en": "No alerts recorded.", "he": "לא נרשמו התראות."},
    "misc.no_score_data": {"en": "No score data", "he": "אין נתוני ציון"},
    "misc.filter_tier": {"en": "Filter by tier", "he": "סינון לפי שכבה"},
    "misc.filter_status": {"en": "Filter by status", "he": "סינון לפי סטטוס"},
    "misc.sort_by": {"en": "Sort by", "he": "מיין לפי"},
    "misc.empty_start": {
        "en": "Add a ticker to get started",
        "he": "הוסף מניה כדי להתחיל",
    },
    "settings.clear_data": {
        "en": "Clear All Data",
        "he": "מחק את כל הנתונים",
    },
    "settings.clear_confirm": {
        "en": "Are you sure? This will delete all candidates, alerts, scores, and trade data.",
        "he": "בטוח? פעולה זו תמחק את כל המועמדים, ההתראות, הציונים ונתוני המסחר.",
    },
    "settings.data_cleared": {
        "en": "All data cleared.",
        "he": "כל הנתונים נמחקו.",
    },
}


def get_lang() -> str:
    """Return current language code ('en' or 'he')."""
    return _current_lang


def set_lang(lang: str) -> None:
    """Set current language. Accepts 'en' or 'he'."""
    global _current_lang
    if lang in ("en", "he"):
        _current_lang = lang


def t(key: str) -> str:
    """Translate a key to the current language. Falls back to English, then key."""
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(_current_lang, entry.get("en", key))
