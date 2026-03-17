"""ATM Trading Engine — Dashboard V1.

Dark trading terminal UI with multi-page layout.
Pages: Overview, Stock Detail, Trade Log, Settings.
First-run wizard when no user_config.json exists.
Hebrew/English bilingual with RTL support.
"""

import json
import os
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from config.i18n import get_lang, set_lang, t
from config.user_config import (
    config_exists,
    load_config,
    save_config,
    wizard_completed,
)

_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "atm.db"


# ── Theme & CSS ────────────────────────────────────────────────

def _build_css() -> str:
    lang = get_lang()
    rtl_block = """
    /* RTL overrides for Hebrew */
    .nav-bar, .candidate-row, .comp-row, .alert-card { direction: rtl; }
    .nav-status { margin-left: 0; margin-right: auto; }
    .nav-logo { margin-right: 0; margin-left: 24px; }
    .alert-time { margin-left: 0; margin-right: auto; }
    .comp-label { text-align: right; }
    .comp-value { text-align: left; }
    .stTextInput, .stSelectbox, .stNumberInput { direction: rtl; }
    """ if lang == "he" else ""

    return f"""
<style>
/* Font loading — non-blocking, graceful fallback to system fonts */
@font-face {{
    font-family: 'JetBrains Mono';
    font-display: swap;
    src: local('JetBrains Mono'), local('JetBrainsMono-Regular');
}}
@font-face {{
    font-family: 'Inter';
    font-display: swap;
    src: local('Inter'), local('Inter-Regular');
}}

/* Global overrides */
.stApp {{ background-color: #0a0e17; }}
[data-testid="stSidebar"] {{ display: none; }}
[data-testid="stHeader"] {{ background-color: #0a0e17; height: 0 !important; }}
[data-testid="stAppViewBlockContainer"] {{ padding-top: 24px; }}
.block-container {{ padding-top: 24px; max-width: 1400px; }}
h1, h2, h3, h4 {{ font-family: 'Inter', sans-serif !important; }}

/* Top nav bar */
.nav-bar {{
    display: flex; align-items: center; gap: 8px;
    padding: 16px 0 12px; margin-bottom: 20px;
    border-bottom: 1px solid #1a2332;
}}
.nav-logo {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 18px; font-weight: 700;
    color: #00d4aa; margin-right: 24px;
    letter-spacing: -0.5px;
}}
.nav-status {{
    margin-left: auto; display: flex; align-items: center; gap: 12px;
    font-family: 'Inter', sans-serif; font-size: 12px; color: #5a6a7a;
}}
.nav-dot {{
    width: 8px; height: 8px; border-radius: 50%;
    display: inline-block; margin-right: 4px;
}}
.nav-dot.live {{ background: #00d4aa; box-shadow: 0 0 6px #00d4aa; }}
.nav-dot.off {{ background: #ff4455; }}

/* Metric cards */
.metric-card {{
    background: linear-gradient(135deg, #111827 0%, #0d1321 100%);
    border: 1px solid #1a2332; border-radius: 12px;
    padding: 20px; position: relative; overflow: hidden;
}}
.metric-card::before {{
    content: ''; position: absolute; top: 0; left: 0; right: 0;
    height: 3px; border-radius: 12px 12px 0 0;
}}
.metric-card.cyan::before {{ background: linear-gradient(90deg, #00d4aa, #00b4d8); }}
.metric-card.blue::before {{ background: linear-gradient(90deg, #3b82f6, #6366f1); }}
.metric-card.amber::before {{ background: linear-gradient(90deg, #f59e0b, #ef4444); }}
.metric-card.green::before {{ background: linear-gradient(90deg, #10b981, #34d399); }}
.metric-label {{
    font-family: 'Inter', sans-serif; font-size: 11px;
    font-weight: 600; color: #5a6a7a; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 8px;
}}
.metric-value {{
    font-family: 'JetBrains Mono', monospace; font-size: 28px;
    font-weight: 700; color: #e2e8f0; line-height: 1;
}}
.metric-sub {{
    font-family: 'Inter', sans-serif; font-size: 11px;
    color: #4a5568; margin-top: 6px;
}}

/* Score badge */
.score-badge {{
    display: inline-block; padding: 4px 12px; border-radius: 6px;
    font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700;
}}
.score-trade {{ background: #052e1c; color: #00d4aa; border: 1px solid #00d4aa33; }}
.score-watch {{ background: #1a2000; color: #84cc16; border: 1px solid #84cc1633; }}
.score-pass {{ background: #1c0a0a; color: #ef4444; border: 1px solid #ef444433; }}

/* Candidate row */
.candidate-row {{
    background: #111827; border: 1px solid #1a2332; border-radius: 10px;
    padding: 16px 20px; margin-bottom: 8px;
    display: flex; align-items: center; gap: 20px;
    transition: border-color 0.2s;
}}
.candidate-row:hover {{ border-color: #00d4aa44; }}
.candidate-ticker {{
    font-family: 'JetBrains Mono', monospace; font-size: 16px;
    font-weight: 700; color: #e2e8f0; min-width: 70px;
}}
.candidate-tier {{
    font-family: 'Inter', sans-serif; font-size: 11px; font-weight: 600;
    color: #5a6a7a; text-transform: uppercase; letter-spacing: 0.5px;
    min-width: 80px;
}}
.candidate-bar-wrap {{
    flex: 1; display: flex; align-items: center; gap: 10px;
}}
.candidate-bar-bg {{
    flex: 1; height: 6px; background: #1a2332; border-radius: 3px;
    overflow: hidden;
}}
.candidate-bar-fill {{
    height: 100%; border-radius: 3px;
    transition: width 0.5s ease;
}}
.candidate-tag {{
    font-size: 10px; padding: 2px 6px; border-radius: 4px;
    font-family: 'JetBrains Mono', monospace; font-weight: 600;
}}
.tag-manual {{ background: #1e1b4b; color: #818cf8; border: 1px solid #818cf833; }}
.tag-pinned {{ background: #422006; color: #f59e0b; border: 1px solid #f59e0b33; }}

/* Alert card */
.alert-card {{
    background: #111827; border-radius: 10px; padding: 14px 18px;
    margin-bottom: 6px; display: flex; align-items: flex-start; gap: 12px;
    border-left: 3px solid;
}}
.alert-card.critical {{ border-left-color: #ef4444; }}
.alert-card.high {{ border-left-color: #f59e0b; }}
.alert-card.warning {{ border-left-color: #eab308; }}
.alert-card.info {{ border-left-color: #3b82f6; }}
.alert-severity {{
    font-family: 'JetBrains Mono', monospace; font-size: 10px;
    font-weight: 700; padding: 2px 8px; border-radius: 4px;
    text-transform: uppercase; letter-spacing: 0.5px; white-space: nowrap;
}}
.sev-critical {{ background: #450a0a; color: #ef4444; }}
.sev-high {{ background: #451a03; color: #f59e0b; }}
.sev-warning {{ background: #422006; color: #eab308; }}
.sev-info {{ background: #0c1929; color: #3b82f6; }}
.alert-body {{
    flex: 1; font-family: 'Inter', sans-serif; font-size: 13px; color: #94a3b8;
}}
.alert-ticker {{
    font-family: 'JetBrains Mono', monospace; font-weight: 700;
    color: #e2e8f0; margin-right: 6px;
}}
.alert-time {{
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
    color: #374151; margin-left: auto; white-space: nowrap;
}}

/* Section header */
.section-header {{
    font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 600;
    color: #5a6a7a; text-transform: uppercase; letter-spacing: 1.5px;
    padding: 12px 0 8px; border-bottom: 1px solid #1a2332;
    margin-bottom: 12px; margin-top: 24px;
}}

/* Detail cards */
.detail-card {{
    background: #111827; border: 1px solid #1a2332;
    border-radius: 10px; padding: 16px;
}}

/* Component score bars */
.comp-row {{
    display: flex; align-items: center; gap: 10px;
    padding: 6px 0; border-bottom: 1px solid #0d1321;
}}
.comp-label {{
    font-family: 'Inter', sans-serif; font-size: 12px;
    color: #5a6a7a; min-width: 100px;
}}
.comp-bar-bg {{
    flex: 1; height: 8px; background: #0d1321; border-radius: 4px;
    overflow: hidden;
}}
.comp-bar-fill {{ height: 100%; border-radius: 4px; }}
.comp-value {{
    font-family: 'JetBrains Mono', monospace; font-size: 12px;
    color: #94a3b8; min-width: 40px; text-align: right;
}}

/* L2 depth visualization */
.depth-row {{
    display: flex; align-items: center; height: 28px;
    margin-bottom: 2px; font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
}}
.depth-bid-bar {{
    background: #052e1c; height: 100%; border-radius: 3px 0 0 3px;
    display: flex; align-items: center; justify-content: flex-end;
    padding-right: 8px; color: #00d4aa;
}}
.depth-ask-bar {{
    background: #2d0a0a; height: 100%; border-radius: 0 3px 3px 0;
    display: flex; align-items: center; padding-left: 8px;
    color: #ef4444;
}}
.depth-price {{
    min-width: 80px; text-align: center; color: #e2e8f0;
    font-weight: 500; padding: 0 8px;
}}

/* Settings cards */
.settings-card {{
    background: #111827; border: 1px solid #1a2332;
    border-radius: 12px; padding: 24px; margin-bottom: 16px;
}}
.settings-title {{
    font-family: 'Inter', sans-serif; font-size: 14px; font-weight: 600;
    color: #e2e8f0; margin-bottom: 16px;
}}

/* Wizard */
.wizard-container {{
    max-width: 600px; margin: 60px auto; padding: 40px;
    background: #111827; border: 1px solid #1a2332; border-radius: 16px;
}}
.wizard-title {{
    font-family: 'Inter', sans-serif; font-size: 24px; font-weight: 700;
    color: #e2e8f0; text-align: center; margin-bottom: 8px;
}}
.wizard-subtitle {{
    font-family: 'Inter', sans-serif; font-size: 14px;
    color: #5a6a7a; text-align: center; margin-bottom: 32px;
}}
.wizard-step {{
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
    color: #00d4aa; text-transform: uppercase; letter-spacing: 1px;
    margin-bottom: 20px;
}}

/* Empty state */
.empty-state {{
    text-align: center; padding: 60px 20px; color: #374151;
    font-family: 'Inter', sans-serif;
}}
.empty-icon {{ font-size: 48px; margin-bottom: 16px; opacity: 0.3; }}
.empty-text {{ font-size: 14px; }}

/* Hide default streamlit elements */
footer {{ display: none !important; }}
#MainMenu {{ display: none !important; }}
[data-testid="stToolbar"] {{ display: none !important; }}

{rtl_block}
</style>
"""


# ── DB Helpers ─────────────────────────────────────────────────

def get_db_path() -> str:
    return st.session_state.get("db_path", str(_DEFAULT_DB))


def query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    path = get_db_path()
    if not Path(path).exists():
        return pd.DataFrame()
    conn = sqlite3.connect(path)
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def execute_sql(sql: str, params: tuple = ()) -> None:
    """Execute a write SQL statement."""
    path = get_db_path()
    conn = sqlite3.connect(path)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def db_exists() -> bool:
    p = Path(get_db_path())
    return p.exists() and p.stat().st_size > 0


def get_db_size_mb() -> str:
    p = Path(get_db_path())
    if not p.exists():
        return "0 MB"
    size = p.stat().st_size / (1024 * 1024)
    return f"{size:.1f} MB"


# ── Component helpers ──────────────────────────────────────────

def metric_card(label: str, value: str, sub: str = "", accent: str = "cyan"):
    st.markdown(
        f'<div class="metric-card {accent}">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div>'
        f'{"<div class=metric-sub>" + sub + "</div>" if sub else ""}'
        f'</div>',
        unsafe_allow_html=True,
    )


def score_badge(score: float | None) -> str:
    if score is None or pd.isna(score):
        return '<span class="score-badge score-pass">--</span>'
    s = int(score)
    if s >= 80:
        cls = "score-trade"
    elif s >= 70:
        cls = "score-watch"
    else:
        cls = "score-pass"
    return f'<span class="score-badge {cls}">{s}</span>'


def bar_color(score: float) -> str:
    if score >= 80:
        return "#00d4aa"
    if score >= 70:
        return "#84cc16"
    if score >= 50:
        return "#f59e0b"
    return "#ef4444"


def format_time_ago(ts_str: str) -> str:
    if not ts_str:
        return ""
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        delta = datetime.now(UTC) - ts
        if delta.total_seconds() < 60:
            return f"{int(delta.total_seconds())}s ago"
        if delta.total_seconds() < 3600:
            return f"{int(delta.total_seconds() / 60)}m ago"
        if delta.total_seconds() < 86400:
            return f"{int(delta.total_seconds() / 3600)}h ago"
        return f"{int(delta.days)}d ago"
    except (ValueError, TypeError):
        return str(ts_str)[:16]


def _load_lang_from_config():
    """Load language setting from user config into i18n module."""
    cfg = load_config()
    set_lang(cfg.get("language", "en"))


def _get_connection_status() -> tuple[str, str]:
    """Return (dot_class, status_label) based on real system state."""
    cfg = load_config()
    use_ibkr = os.environ.get("ATM_USE_IBKR", "").lower() in ("1", "true", "yes")

    if use_ibkr or cfg.get("ibkr", {}).get("host"):
        # Check if engine process is writing data recently
        if db_exists():
            recent = query_df(
                "SELECT max(timestamp) as ts FROM trades "
                "UNION ALL SELECT max(timestamp) FROM l2_snapshots "
                "ORDER BY ts DESC LIMIT 1"
            )
            if not recent.empty and recent.iloc[0]["ts"]:
                return "live", t("status.live")
    if db_exists():
        counts = query_df("SELECT count(*) as c FROM candidates")
        if not counts.empty and int(counts.iloc[0]["c"]) > 0:
            return "live", t("status.live")
    return "off", t("status.no_data")


# ── Nav bar ────────────────────────────────────────────────────

def render_nav():
    db_ok = db_exists()
    counts = {}
    if db_ok:
        for table in ["candidates", "trades", "l2_snapshots", "alerts"]:
            r = query_df(f"SELECT count(*) as c FROM {table}")
            counts[table] = int(r.iloc[0]["c"]) if not r.empty else 0

    dot_class, status_label = _get_connection_status()
    now_str = datetime.now(UTC).strftime("%H:%M:%S")

    st.markdown(
        f'<div class="nav-bar">'
        f'<span class="nav-logo">ATM ENGINE</span>'
        f'<div class="nav-status">'
        f'<span><span class="nav-dot {dot_class}"></span>{status_label}</span>'
        + (
            f'<span>{counts.get("candidates", 0)} {t("section.candidates").lower()}</span>'
            f'<span>{counts.get("trades", 0)} trades</span>'
            f'<span>{counts.get("alerts", 0)} {t("section.alerts").split()[-1].lower()}</span>'
            if db_ok else ""
        )
        + f'<span style="opacity:0.5">Updated {now_str} UTC</span>'
        + '</div></div>',
        unsafe_allow_html=True,
    )


# ── Overview section ───────────────────────────────────────────

def render_overview():
    if not db_exists():
        st.markdown(
            f'<div class="empty-state">'
            f'<div class="empty-icon">_</div>'
            f'<div class="empty-text">{t("misc.no_db")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    candidates_df = query_df(
        "SELECT count(*) as total, "
        "sum(case when status IN ('active','manual','prioritized') then 1 else 0 end) as active "
        "FROM candidates"
    )
    avg_score_df = query_df(
        "SELECT avg(CAST(atm_score AS REAL)) as avg_score "
        "FROM daily_scores WHERE date = ("
        "SELECT max(date) FROM daily_scores)"
    )
    trades_count = query_df("SELECT count(*) as c FROM trades")
    l2_count = query_df("SELECT count(*) as c FROM l2_snapshots")
    alerts_count = query_df(
        "SELECT count(*) as c FROM alerts WHERE severity IN ('CRITICAL','HIGH')"
    )

    total = int(candidates_df.iloc[0]["total"] or 0) if not candidates_df.empty else 0
    active = int(candidates_df.iloc[0]["active"] or 0) if not candidates_df.empty else 0
    avg = avg_score_df.iloc[0]["avg_score"] if not avg_score_df.empty else None
    tc = int(trades_count.iloc[0]["c"]) if not trades_count.empty else 0
    lc = int(l2_count.iloc[0]["c"]) if not l2_count.empty else 0
    ac = int(alerts_count.iloc[0]["c"]) if not alerts_count.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card(t("section.candidates"), str(active), f"{total} total", "cyan")
    with c2:
        avg_str = f"{avg:.0f}" if avg and pd.notna(avg) else "--"
        metric_card(t("score.atm_score"), avg_str, "across active", "blue")
    with c3:
        metric_card("Data Points", f"{tc + lc:,}", f"{tc:,} trades / {lc:,} L2", "green")
    with c4:
        metric_card("Critical Alerts", str(ac), "HIGH + CRITICAL", "amber")


# ── Watchlist management ──────────────────────────────────────

def render_watchlist_controls():
    """Manual ticker add, filter, sort controls above candidates list."""
    col_add, col_filter_tier, col_filter_status, col_sort = st.columns([2, 1.5, 1.5, 1.5])

    with col_add:
        add_cols = st.columns([3, 1, 1])
        with add_cols[0]:
            new_ticker = st.text_input(
                t("action.add_ticker"), placeholder="e.g. ABCD",
                label_visibility="collapsed", key="new_ticker_input",
            )
        with add_cols[1]:
            exchange = st.selectbox(
                "Exchange", ["PINK", "GREY"],
                label_visibility="collapsed", key="exchange_select",
            )
        with add_cols[2]:
            add_clicked = st.button(t("action.add_ticker"), key="add_ticker_btn")

        if add_clicked and new_ticker and new_ticker.strip():
            ticker_clean = new_ticker.strip().upper()
            execute_sql(
                "INSERT OR IGNORE INTO candidates "
                "(ticker, price_tier, status, exchange, first_seen) "
                "VALUES (?, 'UNKNOWN', 'manual', ?, ?)",
                (ticker_clean, exchange, datetime.now(UTC).isoformat()),
            )
            st.rerun()

    with col_filter_tier:
        tier_filter = st.selectbox(
            t("misc.filter_tier"),
            ["All", "TRIP_ZERO", "TRIPS", "LOW_DUBS", "DUBS", "PENNIES", "UNKNOWN"],
            label_visibility="collapsed", key="filter_tier",
        )

    with col_filter_status:
        status_filter = st.selectbox(
            t("misc.filter_status"),
            ["All", "active", "manual", "watching", "prioritized"],
            label_visibility="collapsed", key="filter_status",
        )

    with col_sort:
        sort_by = st.selectbox(
            t("misc.sort_by"),
            ["ATM Score", "Ticker", "Last Updated"],
            label_visibility="collapsed", key="sort_by",
        )

    return tier_filter, status_filter, sort_by


def render_candidates():
    st.markdown(f'<div class="section-header">{t("section.candidates")}</div>', unsafe_allow_html=True)

    tier_filter, status_filter, sort_by = render_watchlist_controls()

    # Build query with filters
    where_clauses = ["c.status NOT IN ('removed')"]
    params: list = []
    if tier_filter != "All":
        where_clauses.append("c.price_tier = ?")
        params.append(tier_filter)
    if status_filter != "All":
        where_clauses.append("c.status = ?")
        params.append(status_filter)

    where_sql = " AND ".join(where_clauses)

    order_map = {
        "ATM Score": "d.atm_score DESC NULLS LAST",
        "Ticker": "c.ticker ASC",
        "Last Updated": "c.last_scored DESC NULLS LAST",
    }
    order_sql = order_map.get(sort_by, "d.atm_score DESC NULLS LAST")

    # Prioritized always on top
    df = query_df(f"""
        SELECT c.ticker, c.price_tier,
            CAST(d.atm_score AS REAL) as atm_score,
            c.status, c.first_seen, c.last_scored
        FROM candidates c
        LEFT JOIN daily_scores d ON c.ticker = d.ticker
            AND d.date = (SELECT max(date) FROM daily_scores WHERE ticker = c.ticker)
        WHERE {where_sql}
        ORDER BY (CASE WHEN c.status = 'prioritized' THEN 0 ELSE 1 END),
                 {order_sql}
    """, tuple(params))

    if df.empty:
        # Check if DB has zero candidates at all (not just filtered out)
        total = query_df("SELECT count(*) as c FROM candidates")
        total_count = int(total.iloc[0]["c"]) if not total.empty else 0
        msg = t("misc.empty_start") if total_count == 0 else t("misc.no_candidates")
        st.markdown(
            f'<div class="empty-state"><div class="empty-text">'
            f'{msg}</div></div>',
            unsafe_allow_html=True,
        )
        return

    for idx, row in df.iterrows():
        score = row["atm_score"]
        score_val = score if pd.notna(score) else 0
        pct = min(score_val, 100)
        fill_color = bar_color(score_val)
        badge = score_badge(score)
        tier = row["price_tier"] or "—"
        seen = format_time_ago(row.get("first_seen", ""))
        status = row.get("status", "active")

        # Tags
        tags_html = ""
        if status == "manual":
            tags_html = f' <span class="candidate-tag tag-manual">📌 {t("status.manual")}</span>'
        elif status == "prioritized":
            tags_html = f' <span class="candidate-tag tag-pinned">⭐</span>'

        col_row, col_actions = st.columns([6, 1])
        with col_row:
            st.markdown(
                f'<div class="candidate-row">'
                f'<span class="candidate-ticker">{row["ticker"]}{tags_html}</span>'
                f'<span class="candidate-tier">{tier}</span>'
                f'<div class="candidate-bar-wrap">'
                f'<div class="candidate-bar-bg">'
                f'<div class="candidate-bar-fill" style="width:{pct}%;background:{fill_color}"></div>'
                f'</div>'
                f'{badge}'
                f'</div>'
                f'<span style="font-size:11px;color:#374151;min-width:60px;text-align:right">'
                f'{seen}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with col_actions:
            action = st.selectbox(
                "action", ["—", t("action.remove"), t("action.pause"), t("action.prioritize")],
                key=f"action_{row['ticker']}_{idx}", label_visibility="collapsed",
            )
            if action == t("action.remove"):
                execute_sql("UPDATE candidates SET status = 'removed' WHERE ticker = ?", (row["ticker"],))
                st.rerun()
            elif action == t("action.pause"):
                execute_sql("UPDATE candidates SET status = 'paused' WHERE ticker = ?", (row["ticker"],))
                st.rerun()
            elif action == t("action.prioritize"):
                execute_sql("UPDATE candidates SET status = 'prioritized' WHERE ticker = ?", (row["ticker"],))
                st.rerun()


# ── Alerts section ─────────────────────────────────────────────

def render_alerts():
    st.markdown(f'<div class="section-header">{t("section.alerts")}</div>', unsafe_allow_html=True)

    df = query_df("""
        SELECT ticker, timestamp, alert_type, severity, message
        FROM alerts ORDER BY timestamp DESC LIMIT 25
    """)

    if df.empty:
        st.markdown(
            f'<div class="empty-state"><div class="empty-text">'
            f'{t("misc.no_alerts")}</div></div>',
            unsafe_allow_html=True,
        )
        return

    for _, row in df.iterrows():
        sev = (row["severity"] or "INFO").upper()
        sev_cls = sev.lower()
        time_str = format_time_ago(row.get("timestamp", ""))

        st.markdown(
            f'<div class="alert-card {sev_cls}">'
            f'<span class="alert-severity sev-{sev_cls}">{sev}</span>'
            f'<div class="alert-body">'
            f'<span class="alert-ticker">{row["ticker"]}</span>'
            f'{row["alert_type"]} '
            f'<span style="color:#4a5568">— {row["message"] or ""}</span>'
            f'</div>'
            f'<span class="alert-time">{time_str}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── Stock Detail section ───────────────────────────────────────

def render_detail():
    st.markdown(f'<div class="section-header">{t("page.detail")}</div>', unsafe_allow_html=True)

    tickers_df = query_df(
        "SELECT DISTINCT ticker FROM candidates WHERE status NOT IN ('removed') ORDER BY ticker"
    )
    if tickers_df.empty:
        return

    tickers = tickers_df["ticker"].tolist()
    ticker = st.selectbox(
        "Select", tickers, label_visibility="collapsed", key="detail_select",
    )
    if not ticker:
        return

    info = query_df("SELECT * FROM candidates WHERE ticker = ? LIMIT 1", (ticker,))
    if not info.empty:
        row = info.iloc[0]
        score = row.get("atm_score")
        score_f = float(score) if score and pd.notna(score) else None

        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            metric_card(t("trade.ticker"), row["ticker"], row.get("price_tier", ""), "cyan")
        with c2:
            s_str = f"{score_f:.0f}" if score_f else "--"
            accent = "green" if score_f and score_f >= 80 else "amber" if score_f and score_f >= 70 else "blue"
            metric_card(t("score.atm_score"), s_str, row.get("status", ""), accent)
        with c3:
            render_component_scores(ticker)

    render_l2_depth(ticker)
    render_trade_activity(ticker)
    render_ticker_alerts(ticker)


def render_component_scores(ticker: str):
    df = query_df("""
        SELECT
            CAST(stability_score AS REAL) as stability,
            CAST(l2_score AS REAL) as l2,
            CAST(volume_score AS REAL) as volume,
            CAST(dilution_score AS REAL) as dilution,
            CAST(ts_score AS REAL) as ts
        FROM daily_scores WHERE ticker = ?
        ORDER BY date DESC LIMIT 1
    """, (ticker,))

    components = {
        t("score.stability"): (15, "#3b82f6"),
        t("score.l2_imbalance"): (45, "#00d4aa"),
        t("score.volume"): (20, "#8b5cf6"),
        t("score.dilution_score"): (10, "#f59e0b"),
        t("score.ts_ratio"): (10, "#ec4899"),
    }

    html = '<div class="detail-card">'
    if df.empty:
        html += f'<div style="color:#374151;font-size:12px;padding:8px">{t("misc.no_score_data")}</div>'
    else:
        row = df.iloc[0]
        vals = [row.get("stability"), row.get("l2"), row.get("volume"),
                row.get("dilution"), row.get("ts")]

        for (label, (max_val, color)), val in zip(components.items(), vals, strict=False):
            v = float(val) if val and pd.notna(val) else 0
            pct = min((v / max_val) * 100, 100) if max_val > 0 else 0
            html += (
                f'<div class="comp-row">'
                f'<span class="comp-label">{label}</span>'
                f'<div class="comp-bar-bg">'
                f'<div class="comp-bar-fill" style="width:{pct}%;background:{color}"></div>'
                f'</div>'
                f'<span class="comp-value">{v:.0f}/{max_val}</span>'
                f'</div>'
            )
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_l2_depth(ticker: str):
    df = query_df("""
        SELECT bid_levels, ask_levels, total_bid_shares, total_ask_shares
        FROM l2_snapshots WHERE ticker = ?
        ORDER BY timestamp DESC LIMIT 1
    """, (ticker,))

    if df.empty:
        return

    row = df.iloc[0]
    total_bid = row["total_bid_shares"] or 0
    total_ask = row["total_ask_shares"] or 0

    try:
        raw_bids = row["bid_levels"]
        bids = json.loads(raw_bids) if isinstance(raw_bids, str) else raw_bids
        raw_asks = row["ask_levels"]
        asks = json.loads(raw_asks) if isinstance(raw_asks, str) else raw_asks
    except (json.JSONDecodeError, TypeError):
        return

    if not bids and not asks:
        return

    ratio = total_bid / total_ask if total_ask > 0 else 0
    ratio_color = "#00d4aa" if ratio >= 3.0 else "#f59e0b" if ratio >= 1.5 else "#ef4444"

    st.markdown(
        f'<div class="section-header">{t("section.l2_depth")} '
        f'<span style="color:{ratio_color};font-family:JetBrains Mono,monospace">'
        f'{ratio:.1f}x</span> '
        f'<span style="font-size:11px;color:#374151;text-transform:none;letter-spacing:0">'
        f'bid/ask ratio ({total_bid:,} / {total_ask:,})</span></div>',
        unsafe_allow_html=True,
    )

    max_size = max(
        max((b.get("size", 0) for b in bids), default=0),
        max((a.get("size", 0) for a in asks), default=0),
        1,
    )

    max_rows = max(len(bids), len(asks))
    html = '<div class="detail-card" style="padding:12px">'
    for i in range(min(max_rows, 8)):
        bid = bids[i] if i < len(bids) else None
        ask = asks[i] if i < len(asks) else None

        bid_pct = (bid["size"] / max_size * 100) if bid else 0
        ask_pct = (ask["size"] / max_size * 100) if ask else 0
        bid_label = f'{bid["size"]:,}' if bid else ""
        ask_label = f'{ask["size"]:,}' if ask else ""
        bid_mm = bid.get("mm_id", "") if bid else ""
        ask_mm = ask.get("mm_id", "") if ask else ""
        bid_price = bid.get("price", "") if bid else ""
        ask_price = ask.get("price", "") if ask else ""

        html += (
            f'<div class="depth-row">'
            f'<span style="color:#374151;font-size:10px;min-width:40px">{bid_mm}</span>'
            f'<div style="flex:1;display:flex;justify-content:flex-end">'
            f'<div class="depth-bid-bar" style="width:{bid_pct}%">{bid_label}</div>'
            f'</div>'
            f'<span class="depth-price">{bid_price}</span>'
            f'<span class="depth-price">{ask_price}</span>'
            f'<div style="flex:1">'
            f'<div class="depth-ask-bar" style="width:{ask_pct}%">{ask_label}</div>'
            f'</div>'
            f'<span style="color:#374151;font-size:10px;min-width:40px;text-align:right">'
            f'{ask_mm}</span>'
            f'</div>'
        )
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_trade_activity(ticker: str):
    df = query_df("""
        SELECT
            DATE(timestamp) as date,
            COUNT(*) as trade_count,
            SUM(size) as total_volume,
            SUM(CASE WHEN side='ask' THEN size ELSE 0 END) as buy_volume,
            SUM(CASE WHEN side='bid' THEN size ELSE 0 END) as sell_volume
        FROM trades WHERE ticker = ?
        GROUP BY DATE(timestamp) ORDER BY date DESC LIMIT 14
    """, (ticker,))

    if df.empty:
        return

    st.markdown(
        f'<div class="section-header">{t("section.trade_activity")}</div>',
        unsafe_allow_html=True,
    )

    chart_df = df.sort_values("date").set_index("date")
    st.bar_chart(
        chart_df[["buy_volume", "sell_volume"]],
        color=["#00d4aa", "#ef4444"],
        use_container_width=True,
        height=200,
    )


def render_ticker_alerts(ticker: str):
    df = query_df("""
        SELECT timestamp, alert_type, severity, message
        FROM alerts WHERE ticker = ?
        ORDER BY timestamp DESC LIMIT 10
    """, (ticker,))

    if df.empty:
        return

    st.markdown(f'<div class="section-header">{t("section.alerts")}</div>', unsafe_allow_html=True)
    for _, row in df.iterrows():
        sev = (row["severity"] or "INFO").upper()
        sev_cls = sev.lower()
        time_str = format_time_ago(row.get("timestamp", ""))
        st.markdown(
            f'<div class="alert-card {sev_cls}">'
            f'<span class="alert-severity sev-{sev_cls}">{sev}</span>'
            f'<div class="alert-body">{row["alert_type"]} — '
            f'<span style="color:#4a5568">{row["message"] or ""}</span></div>'
            f'<span class="alert-time">{time_str}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── Trade Logger ───────────────────────────────────────────────

def render_trade_log():
    """Trade Log page: entry form, active positions, history, correlation."""
    if not db_exists():
        st.info(t("misc.no_db"))
        return

    # Ensure trade_log table exists
    execute_sql("""
        CREATE TABLE IF NOT EXISTS trade_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timestamp_entry TEXT,
            timestamp_exit TEXT,
            entry_price TEXT NOT NULL,
            exit_price TEXT,
            shares INTEGER NOT NULL,
            position_pct TEXT,
            portfolio_value_at_entry TEXT,
            l2_ratio_at_entry TEXT,
            atm_score_at_entry TEXT,
            bad_mm_present INTEGER DEFAULT 0,
            avg_volume_30d INTEGER,
            tracking_days INTEGER,
            exit_reason TEXT,
            pnl_usd TEXT,
            pnl_pct TEXT,
            notes TEXT
        )
    """)

    sub_entry, sub_active, sub_history, sub_corr = st.tabs([
        t("trade.entry"), t("trade.active_positions"),
        t("trade.history"), t("trade.correlation"),
    ])

    with sub_entry:
        _render_trade_entry_form()

    with sub_active:
        _render_active_positions()

    with sub_history:
        _render_trade_history()

    with sub_corr:
        _render_trade_correlation()


def _render_trade_entry_form():
    """Trade entry form with auto-capture of system scores."""
    st.markdown(f'<div class="section-header">{t("trade.entry")}</div>', unsafe_allow_html=True)

    # Get active tickers for dropdown
    tickers_df = query_df(
        "SELECT ticker FROM candidates WHERE status NOT IN ('removed','paused') ORDER BY ticker"
    )
    ticker_options = tickers_df["ticker"].tolist() if not tickers_df.empty else []

    col1, col2 = st.columns(2)
    with col1:
        if ticker_options:
            ticker = st.selectbox(t("trade.ticker"), ticker_options, key="trade_ticker")
        else:
            ticker = st.text_input(t("trade.ticker"), key="trade_ticker_text")
        price_str = st.text_input(t("trade.price"), placeholder="0.0001", key="trade_price")

    with col2:
        side = st.selectbox(
            "Side", [t("trade.side_buy"), t("trade.side_sell")], key="trade_side"
        )
        shares = st.number_input(t("trade.shares"), min_value=1, value=100000, step=10000, key="trade_shares")

    notes = st.text_area(t("trade.notes"), key="trade_notes", height=80)

    if st.button(t("action.add"), key="submit_trade"):
        if not ticker or not price_str:
            st.error("Ticker and price required")
            return

        try:
            price = Decimal(price_str.strip())
        except InvalidOperation:
            st.error("Invalid price format")
            return

        # Auto-capture system scores
        scores = query_df("""
            SELECT CAST(atm_score AS REAL) as atm,
                   CAST(l2_score AS REAL) as l2,
                   CAST(dilution_score AS REAL) as dilution,
                   CAST(volume_score AS REAL) as volume
            FROM daily_scores WHERE ticker = ?
            ORDER BY date DESC LIMIT 1
        """, (ticker,))

        atm_at_entry = str(scores.iloc[0]["atm"]) if not scores.empty and pd.notna(scores.iloc[0]["atm"]) else None
        l2_at_entry = str(scores.iloc[0]["l2"]) if not scores.empty and pd.notna(scores.iloc[0]["l2"]) else None

        now = datetime.now(UTC).isoformat()
        execute_sql(
            "INSERT INTO trade_log (ticker, timestamp_entry, entry_price, shares, "
            "atm_score_at_entry, l2_ratio_at_entry, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticker, now, str(price), shares, atm_at_entry, l2_at_entry, notes),
        )

        st.success(f"Trade logged: {side} {shares:,} {ticker} @ {price}")
        if atm_at_entry:
            st.info(f"Auto-captured — ATM Score: {atm_at_entry}, L2: {l2_at_entry}")


def _render_active_positions():
    """Show open trades (no exit price yet)."""
    st.markdown(f'<div class="section-header">{t("trade.active_positions")}</div>', unsafe_allow_html=True)

    df = query_df("""
        SELECT id, ticker, timestamp_entry, entry_price, shares,
               atm_score_at_entry, l2_ratio_at_entry, notes
        FROM trade_log WHERE exit_price IS NULL
        ORDER BY timestamp_entry DESC
    """)

    if df.empty:
        st.markdown(
            '<div class="empty-state"><div class="empty-text">No open positions</div></div>',
            unsafe_allow_html=True,
        )
        return

    for _, row in df.iterrows():
        held_since = format_time_ago(row.get("timestamp_entry", ""))

        st.markdown(
            f'<div class="candidate-row">'
            f'<span class="candidate-ticker">{row["ticker"]}</span>'
            f'<span style="color:#5a6a7a;font-size:12px">'
            f'{row["shares"]:,} @ {row["entry_price"]}</span>'
            f'<span style="color:#5a6a7a;font-size:11px;margin-left:auto">'
            f'ATM: {row.get("atm_score_at_entry", "--")} | {held_since}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Close position form
        with st.expander(f'{t("action.close_position")} — {row["ticker"]}'):
            close_cols = st.columns(3)
            with close_cols[0]:
                exit_price = st.text_input("Exit Price", key=f"exit_price_{row['id']}")
            with close_cols[1]:
                exit_reason = st.selectbox(
                    t("trade.exit_reason"),
                    ["TARGET", "DILUTION", "DUMP", "TIMEOUT", "MANUAL"],
                    key=f"exit_reason_{row['id']}",
                )
            with close_cols[2]:
                exit_notes = st.text_input("Notes", key=f"exit_notes_{row['id']}")

            if st.button(t("action.close"), key=f"close_{row['id']}"):
                if not exit_price:
                    st.error("Exit price required")
                else:
                    try:
                        ep = Decimal(exit_price.strip())
                        entry_p = Decimal(row["entry_price"])
                        pnl_usd = (ep - entry_p) * row["shares"]
                        pnl_pct = ((ep - entry_p) / entry_p * 100) if entry_p else Decimal("0")
                    except InvalidOperation:
                        st.error("Invalid price")
                        return

                    execute_sql(
                        "UPDATE trade_log SET exit_price=?, exit_reason=?, "
                        "timestamp_exit=?, pnl_usd=?, pnl_pct=?, notes=COALESCE(notes,'') || ? "
                        "WHERE id=?",
                        (str(ep), exit_reason, datetime.now(UTC).isoformat(),
                         str(pnl_usd), str(pnl_pct),
                         f" | Exit: {exit_notes}" if exit_notes else "", row["id"]),
                    )
                    st.success(f"Position closed: P&L ${pnl_usd:.2f} ({pnl_pct:.1f}%)")
                    st.rerun()


def _render_trade_history():
    """Closed trades table with summary stats."""
    st.markdown(f'<div class="section-header">{t("trade.history")}</div>', unsafe_allow_html=True)

    df = query_df("""
        SELECT ticker, entry_price, exit_price, shares, exit_reason,
               CAST(pnl_usd AS REAL) as pnl_usd,
               CAST(pnl_pct AS REAL) as pnl_pct,
               CAST(atm_score_at_entry AS REAL) as atm_score,
               timestamp_entry, timestamp_exit, notes
        FROM trade_log WHERE exit_price IS NOT NULL
        ORDER BY timestamp_exit DESC
    """)

    if df.empty:
        st.markdown(
            '<div class="empty-state"><div class="empty-text">No closed trades yet</div></div>',
            unsafe_allow_html=True,
        )
        return

    # Summary stats
    total_trades = len(df)
    wins = len(df[df["pnl_usd"] > 0]) if "pnl_usd" in df.columns else 0
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    avg_pnl = df["pnl_usd"].mean() if "pnl_usd" in df.columns else 0
    total_pnl = df["pnl_usd"].sum() if "pnl_usd" in df.columns else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card(t("trade.total_trades"), str(total_trades), "", "cyan")
    with c2:
        metric_card(t("trade.win_rate"), f"{win_rate:.0f}%", f"{wins}/{total_trades}", "green")
    with c3:
        metric_card(t("trade.avg_pnl"), f"${avg_pnl:.2f}" if pd.notna(avg_pnl) else "--", "", "blue")
    with c4:
        accent = "green" if total_pnl >= 0 else "amber"
        metric_card(t("trade.total_pnl"), f"${total_pnl:.2f}" if pd.notna(total_pnl) else "--", "", accent)

    # Table
    display_df = df[["ticker", "entry_price", "exit_price", "shares", "pnl_usd", "pnl_pct",
                      "exit_reason", "atm_score"]].copy()
    display_df.columns = ["Ticker", "Entry", "Exit", "Shares", "P&L $", "P&L %", "Reason", "ATM Score"]
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def _render_trade_correlation():
    """Score vs outcome analysis."""
    st.markdown(f'<div class="section-header">{t("trade.correlation")}</div>', unsafe_allow_html=True)

    df = query_df("""
        SELECT CAST(atm_score_at_entry AS REAL) as score,
               CAST(pnl_usd AS REAL) as pnl,
               CAST(pnl_pct AS REAL) as pnl_pct,
               ticker
        FROM trade_log
        WHERE exit_price IS NOT NULL AND atm_score_at_entry IS NOT NULL
        ORDER BY score DESC
    """)

    if df.empty or len(df) < 2:
        st.markdown(
            '<div class="empty-state"><div class="empty-text">'
            'Need at least 2 closed trades with scores for correlation analysis'
            '</div></div>',
            unsafe_allow_html=True,
        )
        return

    # Score buckets
    buckets = {"85+": (85, 100), "80-84": (80, 84), "70-79": (70, 79), "<70": (0, 69)}
    rows = []
    for label, (lo, hi) in buckets.items():
        bucket_df = df[(df["score"] >= lo) & (df["score"] <= hi)]
        if len(bucket_df) > 0:
            wins = len(bucket_df[bucket_df["pnl"] > 0])
            rows.append({
                "Score Range": label,
                "Trades": len(bucket_df),
                "Win Rate": f"{wins / len(bucket_df) * 100:.0f}%",
                "Avg P&L %": f"{bucket_df['pnl_pct'].mean():.1f}%",
            })

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Scatter: score vs P&L
    st.scatter_chart(
        df.set_index("score")[["pnl_pct"]],
        use_container_width=True,
        height=250,
    )


# ── Settings Page ──────────────────────────────────────────────

def render_settings():
    """Full settings page: system status, IBKR, Telegram, risk params, language."""
    cfg = load_config()

    # ── System Status Summary ──
    st.markdown(f'<div class="section-header">{t("settings.system_status")}</div>', unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        dot, label = _get_connection_status()
        icon = "🟢" if dot == "live" else "🔴"
        metric_card("IBKR", f"{icon} {label}", "", "cyan")
    with s2:
        tg_ok = bool(cfg.get("telegram", {}).get("bot_token"))
        tg_icon = "🟢" if tg_ok else "🔴"
        tg_label = t("status.active") if tg_ok else t("settings.not_configured")
        metric_card("Telegram", f"{tg_icon} {tg_label}", "", "blue")
    with s3:
        if db_exists():
            ccount = query_df("SELECT count(*) as c FROM candidates WHERE status NOT IN ('removed')")
            metric_card(t("settings.candidates_count"), str(int(ccount.iloc[0]["c"])), "", "green")
        else:
            metric_card(t("settings.candidates_count"), "0", "", "green")
    with s4:
        metric_card(t("settings.db_size"), get_db_size_mb(), "", "amber")

    # ── Language ──
    st.markdown(f'<div class="section-header">{t("settings.language")}</div>', unsafe_allow_html=True)
    lang_choice = st.radio(
        t("settings.language"),
        ["English", "עברית"],
        index=0 if cfg.get("language", "en") == "en" else 1,
        horizontal=True, label_visibility="collapsed",
    )
    new_lang = "en" if lang_choice == "English" else "he"
    if new_lang != cfg.get("language", "en"):
        cfg["language"] = new_lang
        save_config(cfg)
        set_lang(new_lang)
        st.rerun()

    # ── IBKR Connection ──
    st.markdown(f'<div class="section-header">{t("settings.ibkr_connection")}</div>', unsafe_allow_html=True)

    ibkr = cfg.get("ibkr", {})
    col1, col2, col3 = st.columns(3)
    with col1:
        ibkr_host = st.text_input(t("settings.host"), value=ibkr.get("host", "127.0.0.1"), key="ibkr_host")
    with col2:
        ibkr_port = st.number_input(t("settings.port"), value=ibkr.get("port", 7497), key="ibkr_port")
    with col3:
        ibkr_client = st.number_input(t("settings.client_id"), value=ibkr.get("client_id", 1), key="ibkr_client")

    col_test, col_save = st.columns(2)
    with col_test:
        if st.button(t("action.test_connection"), key="test_ibkr"):
            st.info("Connection test requires TWS running. Save settings and start engine with --live flag.")
    with col_save:
        if st.button(f'{t("action.save")} IBKR', key="save_ibkr"):
            cfg["ibkr"] = {"host": ibkr_host, "port": int(ibkr_port), "client_id": int(ibkr_client)}
            save_config(cfg)
            st.success(t("settings.saved"))

    # ── Telegram Alerts ──
    st.markdown(f'<div class="section-header">{t("settings.telegram_alerts")}</div>', unsafe_allow_html=True)

    tg = cfg.get("telegram", {})
    col1, col2 = st.columns(2)
    with col1:
        tg_token = st.text_input(
            t("settings.bot_token"), value=tg.get("bot_token", ""),
            type="password", key="tg_token",
        )
    with col2:
        tg_chat = st.text_input(
            t("settings.chat_id"), value=tg.get("chat_id", ""),
            type="password", key="tg_chat",
        )

    col_test_tg, col_save_tg = st.columns(2)
    with col_test_tg:
        if st.button(t("action.send_test_ping"), key="test_telegram"):
            if tg_token and tg_chat:
                try:
                    import urllib.request
                    url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
                    data = json.dumps({"chat_id": tg_chat, "text": "✅ ATM Engine connected"}).encode()
                    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=10)
                    st.success("Test message sent!")
                except Exception as e:
                    st.error(f"Failed: {e}")
            else:
                st.warning("Enter bot token and chat ID first")
    with col_save_tg:
        if st.button(f'{t("action.save")} Telegram', key="save_telegram"):
            cfg["telegram"] = {
                "bot_token": tg_token,
                "chat_id": tg_chat,
                "enabled": bool(tg_token and tg_chat),
            }
            save_config(cfg)
            st.success(t("settings.saved"))

    # ── Risk Parameters ──
    st.markdown(f'<div class="section-header">{t("settings.risk_params")}</div>', unsafe_allow_html=True)

    risk = cfg.get("risk", {})
    r1, r2, r3 = st.columns(3)
    with r1:
        pos_pct = st.number_input(
            t("risk.position_size") + " %", value=risk.get("max_position_pct", 5.0),
            min_value=0.5, max_value=25.0, step=0.5, key="risk_pos",
        )
        max_loss = st.number_input(
            t("risk.max_loss") + " %", value=risk.get("max_loss_pct", 2.0),
            min_value=0.5, max_value=10.0, step=0.5, key="risk_loss",
        )
        portfolio = st.number_input(
            t("risk.portfolio_value"), value=risk.get("portfolio_value", 10000),
            min_value=100, step=1000, key="risk_portfolio",
        )
    with r2:
        hold_trips = st.number_input(
            t("settings.max_hold_trips"), value=risk.get("max_hold_hours_trips", 4),
            min_value=1, max_value=24, key="risk_hold_trips",
        )
        hold_dubs = st.number_input(
            t("settings.max_hold_dubs"), value=risk.get("max_hold_days_dubs", 2),
            min_value=1, max_value=30, key="risk_hold_dubs",
        )
        hold_pennies = st.number_input(
            t("settings.max_hold_pennies"), value=risk.get("max_hold_days_pennies", 5),
            min_value=1, max_value=30, key="risk_hold_pennies",
        )
    with r3:
        ohi_strong = st.number_input(
            t("settings.ohi_strong"), value=risk.get("ohi_strong", 65),
            min_value=0, max_value=100, key="risk_ohi_strong",
        )
        ohi_neutral = st.number_input(
            t("settings.ohi_neutral"), value=risk.get("ohi_neutral_low", 40),
            min_value=0, max_value=100, key="risk_ohi_neutral",
        )
        atm_trade = st.number_input(
            t("settings.atm_trade"), value=risk.get("atm_min_trade", 80),
            min_value=0, max_value=100, key="risk_atm_trade",
        )

    r4, r5, r6 = st.columns(3)
    with r4:
        atm_watch = st.number_input(
            t("settings.atm_watchlist"), value=risk.get("atm_min_watchlist", 70),
            min_value=0, max_value=100, key="risk_atm_watch",
        )
    with r5:
        l2_min = st.number_input(
            t("settings.l2_min"), value=risk.get("l2_imbalance_min", 3.0),
            min_value=1.0, max_value=20.0, step=0.5, key="risk_l2_min",
        )
    with r6:
        dil_exit = st.number_input(
            t("settings.dilution_exit"), value=risk.get("dilution_exit_trigger", 3),
            min_value=1, max_value=10, key="risk_dil_exit",
        )

    if st.button(f'{t("action.save")} {t("settings.risk_params")}', key="save_risk"):
        cfg["risk"] = {
            "max_position_pct": pos_pct,
            "max_loss_pct": max_loss,
            "portfolio_value": portfolio,
            "max_hold_hours_trips": hold_trips,
            "max_hold_days_dubs": hold_dubs,
            "max_hold_days_pennies": hold_pennies,
            "ohi_strong": ohi_strong,
            "ohi_neutral_low": ohi_neutral,
            "atm_min_trade": atm_trade,
            "atm_min_watchlist": atm_watch,
            "l2_imbalance_min": l2_min,
            "dilution_exit_trigger": dil_exit,
        }
        save_config(cfg)
        st.success(t("settings.saved"))

    # ── Clear All Data ──
    st.markdown(f'<div class="section-header">{t("settings.clear_data")}</div>', unsafe_allow_html=True)
    st.warning(t("settings.clear_confirm"))
    if st.button(t("settings.clear_data"), key="clear_all_data", type="primary"):
        if db_exists():
            db = get_db_path()
            conn = sqlite3.connect(str(db))
            for tbl in ("candidates", "trades", "l2_snapshots", "trade_log", "alerts", "daily_scores"):
                conn.execute(f"DELETE FROM {tbl}")  # noqa: S608
            conn.execute("DELETE FROM sqlite_sequence")
            conn.commit()
            conn.close()
            st.success(t("settings.data_cleared"))
            st.rerun()


# ── First-Run Wizard ───────────────────────────────────────────

def render_wizard():
    """Linear setup wizard for first-time users."""
    if "wizard_step" not in st.session_state:
        st.session_state.wizard_step = 0

    step = st.session_state.wizard_step

    st.markdown(
        '<div class="wizard-container">'
        f'<div class="wizard-title">{t("wizard.welcome_title")}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Step indicators
    steps = [
        t("wizard.welcome_title"),
        t("wizard.step_language"),
        t("wizard.step_ibkr"),
        t("wizard.step_telegram"),
        t("wizard.step_risk"),
        t("wizard.step_done"),
    ]
    st.progress((step) / (len(steps) - 1))
    st.markdown(
        f'<div class="wizard-step">Step {step + 1}/{len(steps)} — {steps[step]}</div>',
        unsafe_allow_html=True,
    )

    cfg = load_config()

    if step == 0:
        # Welcome
        st.markdown(t("wizard.welcome_body"))
        if st.button(t("wizard.next"), key="wiz_next_0"):
            st.session_state.wizard_step = 1
            st.rerun()

    elif step == 1:
        # Language
        lang_choice = st.radio(
            t("settings.language"),
            ["English", "עברית"],
            index=0 if cfg.get("language", "en") == "en" else 1,
            horizontal=True,
        )
        new_lang = "en" if lang_choice == "English" else "he"
        cfg["language"] = new_lang
        set_lang(new_lang)

        col_back, col_next = st.columns(2)
        with col_back:
            if st.button(t("wizard.back"), key="wiz_back_1"):
                st.session_state.wizard_step = 0
                st.rerun()
        with col_next:
            if st.button(t("wizard.next"), key="wiz_next_1"):
                save_config(cfg)
                st.session_state.wizard_step = 2
                st.rerun()

    elif step == 2:
        # IBKR Connection
        ibkr = cfg.get("ibkr", {})
        ibkr_host = st.text_input(t("settings.host"), value=ibkr.get("host", "127.0.0.1"))
        ibkr_port = st.number_input(t("settings.port"), value=ibkr.get("port", 7497))
        ibkr_client = st.number_input(t("settings.client_id"), value=ibkr.get("client_id", 1))

        if st.button(t("action.test_connection"), key="wiz_test_ibkr"):
            st.info("TWS must be running to test. You can configure this later in Settings.")

        col_back, col_next = st.columns(2)
        with col_back:
            if st.button(t("wizard.back"), key="wiz_back_2"):
                st.session_state.wizard_step = 1
                st.rerun()
        with col_next:
            if st.button(t("wizard.next"), key="wiz_next_2"):
                cfg["ibkr"] = {"host": ibkr_host, "port": int(ibkr_port), "client_id": int(ibkr_client)}
                save_config(cfg)
                st.session_state.wizard_step = 3
                st.rerun()

    elif step == 3:
        # Telegram (optional)
        tg = cfg.get("telegram", {})
        tg_token = st.text_input(t("settings.bot_token"), value=tg.get("bot_token", ""), type="password")
        tg_chat = st.text_input(t("settings.chat_id"), value=tg.get("chat_id", ""), type="password")

        if st.button(t("action.send_test_ping"), key="wiz_test_tg"):
            if tg_token and tg_chat:
                try:
                    import urllib.request
                    url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
                    data = json.dumps({"chat_id": tg_chat, "text": "✅ ATM Engine connected"}).encode()
                    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=10)
                    st.success("Test message sent!")
                except Exception as e:
                    st.error(f"Failed: {e}")

        col_back, col_skip, col_next = st.columns(3)
        with col_back:
            if st.button(t("wizard.back"), key="wiz_back_3"):
                st.session_state.wizard_step = 2
                st.rerun()
        with col_skip:
            if st.button(t("wizard.skip"), key="wiz_skip_3"):
                st.session_state.wizard_step = 4
                st.rerun()
        with col_next:
            if st.button(t("wizard.next"), key="wiz_next_3"):
                cfg["telegram"] = {
                    "bot_token": tg_token, "chat_id": tg_chat,
                    "enabled": bool(tg_token and tg_chat),
                }
                save_config(cfg)
                st.session_state.wizard_step = 4
                st.rerun()

    elif step == 4:
        # Risk defaults
        risk = cfg.get("risk", {})
        st.number_input(t("risk.position_size") + " %", value=risk.get("max_position_pct", 5.0),
                        min_value=0.5, max_value=25.0, step=0.5, key="wiz_pos")
        st.number_input(t("risk.max_loss") + " %", value=risk.get("max_loss_pct", 2.0),
                        min_value=0.5, max_value=10.0, step=0.5, key="wiz_loss")
        st.number_input(t("risk.portfolio_value"), value=risk.get("portfolio_value", 10000),
                        min_value=100, step=1000, key="wiz_portfolio")

        col_back, col_next = st.columns(2)
        with col_back:
            if st.button(t("wizard.back"), key="wiz_back_4"):
                st.session_state.wizard_step = 3
                st.rerun()
        with col_next:
            if st.button(t("wizard.next"), key="wiz_next_4"):
                cfg["risk"]["max_position_pct"] = st.session_state.wiz_pos
                cfg["risk"]["max_loss_pct"] = st.session_state.wiz_loss
                cfg["risk"]["portfolio_value"] = st.session_state.wiz_portfolio
                save_config(cfg)
                st.session_state.wizard_step = 5
                st.rerun()

    elif step == 5:
        # Done
        st.markdown(f"### {t('wizard.step_done')}")
        st.balloons()
        if st.button(t("wizard.finish"), key="wiz_finish"):
            cfg["wizard_completed"] = True
            save_config(cfg)
            del st.session_state["wizard_step"]
            st.rerun()


# ── Main ───────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="ATM Engine",
        page_icon="$",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # Load language from config
    _load_lang_from_config()

    st.markdown(_build_css(), unsafe_allow_html=True)

    # Auto-refresh every 10 seconds (only when browser tab is visible)
    st_autorefresh(interval=10_000, limit=None, key="auto_refresh")

    # First-run wizard check
    if not wizard_completed():
        render_wizard()
        return

    render_nav()

    if not db_exists():
        st.markdown(
            f'<div class="empty-state">'
            f'<div class="empty-text" style="font-size:16px;color:#5a6a7a">'
            f'{t("misc.no_db")}'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        return

    # Tab navigation
    tab_overview, tab_detail, tab_trade_log, tab_settings = st.tabs([
        t("page.overview"), t("page.detail"),
        t("page.trade_log"), t("page.settings"),
    ])

    with tab_overview:
        render_overview()
        col_left, col_right = st.columns([3, 2])
        with col_left:
            render_candidates()
        with col_right:
            render_alerts()

    with tab_detail:
        render_detail()

    with tab_trade_log:
        render_trade_log()

    with tab_settings:
        render_settings()


main()
