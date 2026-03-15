"""ATM Trading Engine — Dashboard.

Dark trading terminal UI. Single-page overview with expandable detail views.
Reads from SQLite via sqlite3 (sync). Auto-refreshes every 5 seconds.
"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "atm.db"


# ── Theme & CSS ────────────────────────────────────────────────

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700&display=swap');

/* Global overrides */
.stApp { background-color: #0a0e17; }
[data-testid="stSidebar"] { display: none; }
[data-testid="stHeader"] { background-color: #0a0e17; height: 0 !important; }
[data-testid="stAppViewBlockContainer"] { padding-top: 24px; }
.block-container { padding-top: 24px; max-width: 1400px; }
h1, h2, h3, h4 { font-family: 'Inter', sans-serif !important; }

/* Top nav bar */
.nav-bar {
    display: flex; align-items: center; gap: 8px;
    padding: 16px 0 12px; margin-bottom: 20px;
    border-bottom: 1px solid #1a2332;
}
.nav-logo {
    font-family: 'JetBrains Mono', monospace;
    font-size: 18px; font-weight: 700;
    color: #00d4aa; margin-right: 24px;
    letter-spacing: -0.5px;
}
.nav-status {
    margin-left: auto; display: flex; align-items: center; gap: 12px;
    font-family: 'Inter', sans-serif; font-size: 12px; color: #5a6a7a;
}
.nav-dot {
    width: 8px; height: 8px; border-radius: 50%;
    display: inline-block; margin-right: 4px;
}
.nav-dot.live { background: #00d4aa; box-shadow: 0 0 6px #00d4aa; }
.nav-dot.off { background: #ff4455; }

/* Metric cards */
.metric-card {
    background: linear-gradient(135deg, #111827 0%, #0d1321 100%);
    border: 1px solid #1a2332; border-radius: 12px;
    padding: 20px; position: relative; overflow: hidden;
}
.metric-card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0;
    height: 3px; border-radius: 12px 12px 0 0;
}
.metric-card.cyan::before { background: linear-gradient(90deg, #00d4aa, #00b4d8); }
.metric-card.blue::before { background: linear-gradient(90deg, #3b82f6, #6366f1); }
.metric-card.amber::before { background: linear-gradient(90deg, #f59e0b, #ef4444); }
.metric-card.green::before { background: linear-gradient(90deg, #10b981, #34d399); }
.metric-label {
    font-family: 'Inter', sans-serif; font-size: 11px;
    font-weight: 600; color: #5a6a7a; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 8px;
}
.metric-value {
    font-family: 'JetBrains Mono', monospace; font-size: 28px;
    font-weight: 700; color: #e2e8f0; line-height: 1;
}
.metric-sub {
    font-family: 'Inter', sans-serif; font-size: 11px;
    color: #4a5568; margin-top: 6px;
}

/* Score badge */
.score-badge {
    display: inline-block; padding: 4px 12px; border-radius: 6px;
    font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700;
}
.score-trade { background: #052e1c; color: #00d4aa; border: 1px solid #00d4aa33; }
.score-watch { background: #1a2000; color: #84cc16; border: 1px solid #84cc1633; }
.score-pass { background: #1c0a0a; color: #ef4444; border: 1px solid #ef444433; }

/* Candidate row */
.candidate-row {
    background: #111827; border: 1px solid #1a2332; border-radius: 10px;
    padding: 16px 20px; margin-bottom: 8px;
    display: flex; align-items: center; gap: 20px;
    transition: border-color 0.2s;
}
.candidate-row:hover { border-color: #00d4aa44; }
.candidate-ticker {
    font-family: 'JetBrains Mono', monospace; font-size: 16px;
    font-weight: 700; color: #e2e8f0; min-width: 70px;
}
.candidate-tier {
    font-family: 'Inter', sans-serif; font-size: 11px; font-weight: 600;
    color: #5a6a7a; text-transform: uppercase; letter-spacing: 0.5px;
    min-width: 80px;
}
.candidate-bar-wrap {
    flex: 1; display: flex; align-items: center; gap: 10px;
}
.candidate-bar-bg {
    flex: 1; height: 6px; background: #1a2332; border-radius: 3px;
    overflow: hidden;
}
.candidate-bar-fill {
    height: 100%; border-radius: 3px;
    transition: width 0.5s ease;
}

/* Alert card */
.alert-card {
    background: #111827; border-radius: 10px; padding: 14px 18px;
    margin-bottom: 6px; display: flex; align-items: flex-start; gap: 12px;
    border-left: 3px solid;
}
.alert-card.critical { border-left-color: #ef4444; }
.alert-card.high { border-left-color: #f59e0b; }
.alert-card.warning { border-left-color: #eab308; }
.alert-card.info { border-left-color: #3b82f6; }
.alert-severity {
    font-family: 'JetBrains Mono', monospace; font-size: 10px;
    font-weight: 700; padding: 2px 8px; border-radius: 4px;
    text-transform: uppercase; letter-spacing: 0.5px; white-space: nowrap;
}
.sev-critical { background: #450a0a; color: #ef4444; }
.sev-high { background: #451a03; color: #f59e0b; }
.sev-warning { background: #422006; color: #eab308; }
.sev-info { background: #0c1929; color: #3b82f6; }
.alert-body {
    flex: 1; font-family: 'Inter', sans-serif; font-size: 13px; color: #94a3b8;
}
.alert-ticker {
    font-family: 'JetBrains Mono', monospace; font-weight: 700;
    color: #e2e8f0; margin-right: 6px;
}
.alert-time {
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
    color: #374151; margin-left: auto; white-space: nowrap;
}

/* Section header */
.section-header {
    font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 600;
    color: #5a6a7a; text-transform: uppercase; letter-spacing: 1.5px;
    padding: 12px 0 8px; border-bottom: 1px solid #1a2332;
    margin-bottom: 12px; margin-top: 24px;
}

/* Detail cards */
.detail-card {
    background: #111827; border: 1px solid #1a2332;
    border-radius: 10px; padding: 16px;
}

/* Component score bars */
.comp-row {
    display: flex; align-items: center; gap: 10px;
    padding: 6px 0; border-bottom: 1px solid #0d1321;
}
.comp-label {
    font-family: 'Inter', sans-serif; font-size: 12px;
    color: #5a6a7a; min-width: 100px;
}
.comp-bar-bg {
    flex: 1; height: 8px; background: #0d1321; border-radius: 4px;
    overflow: hidden;
}
.comp-bar-fill {
    height: 100%; border-radius: 4px;
}
.comp-value {
    font-family: 'JetBrains Mono', monospace; font-size: 12px;
    color: #94a3b8; min-width: 40px; text-align: right;
}

/* L2 depth visualization */
.depth-row {
    display: flex; align-items: center; height: 28px;
    margin-bottom: 2px; font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
}
.depth-bid-bar {
    background: #052e1c; height: 100%; border-radius: 3px 0 0 3px;
    display: flex; align-items: center; justify-content: flex-end;
    padding-right: 8px; color: #00d4aa;
}
.depth-ask-bar {
    background: #2d0a0a; height: 100%; border-radius: 0 3px 3px 0;
    display: flex; align-items: center; padding-left: 8px;
    color: #ef4444;
}
.depth-price {
    min-width: 80px; text-align: center; color: #e2e8f0;
    font-weight: 500; padding: 0 8px;
}

/* Empty state */
.empty-state {
    text-align: center; padding: 60px 20px; color: #374151;
    font-family: 'Inter', sans-serif;
}
.empty-icon { font-size: 48px; margin-bottom: 16px; opacity: 0.3; }
.empty-text { font-size: 14px; }

/* Hide default streamlit elements */
footer { display: none !important; }
#MainMenu { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }
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


def db_exists() -> bool:
    p = Path(get_db_path())
    return p.exists() and p.stat().st_size > 0


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


# ── Nav bar ────────────────────────────────────────────────────

def render_nav():
    db_ok = db_exists()
    counts = {}
    if db_ok:
        for table in ["candidates", "trades", "l2_snapshots", "alerts"]:
            r = query_df(f"SELECT count(*) as c FROM {table}")
            counts[table] = int(r.iloc[0]["c"]) if not r.empty else 0

    dot_class = "live" if db_ok and sum(counts.values()) > 0 else "off"
    status_label = "LIVE" if dot_class == "live" else "NO DATA"

    st.markdown(
        f'<div class="nav-bar">'
        f'<span class="nav-logo">ATM ENGINE</span>'
        f'<div class="nav-status">'
        f'<span><span class="nav-dot {dot_class}"></span>{status_label}</span>'
        + (
            f'<span>{counts.get("candidates", 0)} candidates</span>'
            f'<span>{counts.get("trades", 0)} trades</span>'
            f'<span>{counts.get("alerts", 0)} alerts</span>'
            if db_ok else ""
        )
        + '</div></div>',
        unsafe_allow_html=True,
    )


# ── Overview section ───────────────────────────────────────────

def render_overview():
    if not db_exists():
        st.markdown(
            '<div class="empty-state">'
            '<div class="empty-icon">_</div>'
            '<div class="empty-text">No database found. Start the engine to see data.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # Top metrics
    candidates_df = query_df(
        "SELECT count(*) as total, "
        "sum(case when status='active' then 1 else 0 end) as active "
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

    total = int(candidates_df.iloc[0]["total"]) if not candidates_df.empty else 0
    active = int(candidates_df.iloc[0]["active"]) if not candidates_df.empty else 0
    avg = avg_score_df.iloc[0]["avg_score"] if not avg_score_df.empty else None
    tc = int(trades_count.iloc[0]["c"]) if not trades_count.empty else 0
    lc = int(l2_count.iloc[0]["c"]) if not l2_count.empty else 0
    ac = int(alerts_count.iloc[0]["c"]) if not alerts_count.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Candidates", str(active), f"{total} total tracked", "cyan")
    with c2:
        avg_str = f"{avg:.0f}" if avg and pd.notna(avg) else "--"
        metric_card("Avg ATM Score", avg_str, "across active", "blue")
    with c3:
        metric_card("Data Points", f"{tc + lc:,}", f"{tc:,} trades / {lc:,} L2", "green")
    with c4:
        metric_card("Critical Alerts", str(ac), "HIGH + CRITICAL", "amber")


# ── Candidates section ─────────────────────────────────────────

def render_candidates():
    st.markdown('<div class="section-header">Candidates</div>', unsafe_allow_html=True)

    df = query_df("""
        SELECT c.ticker, c.price_tier,
            CAST(d.atm_score AS REAL) as atm_score,
            c.status, c.first_seen, c.last_scored
        FROM candidates c
        LEFT JOIN daily_scores d ON c.ticker = d.ticker
            AND d.date = (SELECT max(date) FROM daily_scores WHERE ticker = c.ticker)
        ORDER BY d.atm_score DESC NULLS LAST
    """)

    if df.empty:
        st.markdown(
            '<div class="empty-state"><div class="empty-text">'
            'No candidates yet. Start the engine and push market data.</div></div>',
            unsafe_allow_html=True,
        )
        return

    for _, row in df.iterrows():
        score = row["atm_score"]
        score_val = score if pd.notna(score) else 0
        pct = min(score_val, 100)
        fill_color = bar_color(score_val)
        badge = score_badge(score)
        tier = row["price_tier"] or "—"
        seen = format_time_ago(row.get("first_seen", ""))

        st.markdown(
            f'<div class="candidate-row">'
            f'<span class="candidate-ticker">{row["ticker"]}</span>'
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


# ── Alerts section ─────────────────────────────────────────────

def render_alerts():
    st.markdown('<div class="section-header">Recent Alerts</div>', unsafe_allow_html=True)

    df = query_df("""
        SELECT ticker, timestamp, alert_type, severity, message
        FROM alerts ORDER BY timestamp DESC LIMIT 25
    """)

    if df.empty:
        st.markdown(
            '<div class="empty-state"><div class="empty-text">'
            'No alerts recorded.</div></div>',
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
    st.markdown('<div class="section-header">Stock Detail</div>', unsafe_allow_html=True)

    tickers_df = query_df("SELECT DISTINCT ticker FROM candidates ORDER BY ticker")
    if tickers_df.empty:
        return

    tickers = tickers_df["ticker"].tolist()
    ticker = st.selectbox(
        "Select", tickers, label_visibility="collapsed",
        key="detail_select",
    )
    if not ticker:
        return

    # Header card
    info = query_df("SELECT * FROM candidates WHERE ticker = ? LIMIT 1", (ticker,))
    if not info.empty:
        row = info.iloc[0]
        score = row.get("atm_score")
        score_f = float(score) if score and pd.notna(score) else None

        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            metric_card("Ticker", row["ticker"], row.get("price_tier", ""), "cyan")
        with c2:
            s_str = f"{score_f:.0f}" if score_f else "--"
            if score_f and score_f >= 80:
                accent = "green"
            elif score_f and score_f >= 70:
                accent = "amber"
            else:
                accent = "blue"
            metric_card("ATM Score", s_str, row.get("status", ""), accent)
        with c3:
            render_component_scores(ticker)

    # L2 depth visualization
    render_l2_depth(ticker)

    # Trade activity
    render_trade_activity(ticker)

    # Alerts for this ticker
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
        "Stability": (15, "#3b82f6"),
        "L2 Imbalance": (45, "#00d4aa"),
        "Volume": (20, "#8b5cf6"),
        "Dilution": (10, "#f59e0b"),
        "T&S Ratio": (10, "#ec4899"),
    }

    html = '<div class="detail-card">'
    if df.empty:
        html += '<div style="color:#374151;font-size:12px;padding:8px">No score data</div>'
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
        f'<div class="section-header">L2 Depth '
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

    # Pair up bids and asks side by side
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
        '<div class="section-header">Trade Activity</div>',
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

    st.markdown('<div class="section-header">Alerts</div>', unsafe_allow_html=True)
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


# ── Main ───────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="ATM Engine",
        page_icon="$",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(_CSS, unsafe_allow_html=True)
    render_nav()

    if not db_exists():
        st.markdown(
            '<div class="empty-state">'
            '<div class="empty-text" style="font-size:16px;color:#5a6a7a">'
            'No database found at <code style="color:#00d4aa">data/atm.db</code><br>'
            '<span style="font-size:13px;color:#374151">'
            'Run the engine to start collecting data</span>'
            '</div></div>',
            unsafe_allow_html=True,
        )
        return

    # Tab navigation
    tab_overview, tab_detail = st.tabs(["Overview", "Stock Detail"])

    with tab_overview:
        render_overview()
        col_left, col_right = st.columns([3, 2])
        with col_left:
            render_candidates()
        with col_right:
            render_alerts()

    with tab_detail:
        render_detail()


if __name__ == "__main__":
    main()
