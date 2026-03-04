"""ATM Trading Engine — Streamlit Dashboard.

Three pages:
  1. Candidates — table with ATM scores, status, price tier (sortable)
  2. Alerts — live feed with severity color coding
  3. Stock Detail — daily scores, L2 snapshots, volume history for one ticker

Reads directly from the SQLite database via sqlite3 (sync).
"""

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "atm.db"


def get_db_path() -> str:
    return st.session_state.get("db_path", str(_DEFAULT_DB))


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    return sqlite3.connect(path)


def query_df(sql: str, params: tuple = (), db_path: str | None = None) -> pd.DataFrame:
    """Run a query and return a DataFrame."""
    conn = get_connection(db_path)
    try:
        df = pd.read_sql_query(sql, conn, params=params)
        return df
    finally:
        conn.close()


def db_exists(db_path: str | None = None) -> bool:
    path = db_path or get_db_path()
    p = Path(path)
    return p.exists() and p.stat().st_size > 0


# ── Severity color mapping ──────────────────────────────────────

_SEVERITY_COLORS = {
    "CRITICAL": "#ff4444",
    "HIGH": "#ff8800",
    "WARNING": "#ffcc00",
    "INFO": "#4488ff",
}

_STATUS_COLORS = {
    "active": "#44bb44",
    "watching": "#4488ff",
    "rejected": "#ff4444",
    "trading": "#ffcc00",
}


# ── Page: Candidates ────────────────────────────────────────────

def page_candidates():
    st.header("Candidates")

    if not db_exists():
        st.info("No database found. Run the system to generate data.")
        return

    df = query_df("""
        SELECT
            ticker,
            price_tier,
            CAST(atm_score AS REAL) as atm_score,
            status,
            first_seen,
            last_scored,
            rejection_reason
        FROM candidates
        ORDER BY atm_score DESC NULLS LAST
    """)

    if df.empty:
        st.info("No candidates in the database yet.")
        return

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        statuses = ["All", *sorted(df["status"].dropna().unique().tolist())]
        status_filter = st.selectbox("Status", statuses)
    with col2:
        tiers = ["All", *sorted(df["price_tier"].dropna().unique().tolist())]
        tier_filter = st.selectbox("Price Tier", tiers)

    filtered = df.copy()
    if status_filter != "All":
        filtered = filtered[filtered["status"] == status_filter]
    if tier_filter != "All":
        filtered = filtered[filtered["price_tier"] == tier_filter]

    # Summary metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total", len(filtered))
    m2.metric("Active", len(filtered[filtered["status"] == "active"]))
    avg_score = filtered["atm_score"].mean()
    m3.metric("Avg Score", f"{avg_score:.1f}" if pd.notna(avg_score) else "—")
    trade_ready = len(filtered[filtered["atm_score"] >= 80]) if not filtered.empty else 0
    m4.metric("Trade Ready (>=80)", trade_ready)

    # Color-coded table
    def color_score(val):
        if pd.isna(val):
            return ""
        if val >= 80:
            return "background-color: #1a472a; color: #44ff44"
        if val >= 70:
            return "background-color: #2a3a1a; color: #aaff44"
        return "background-color: #3a1a1a; color: #ff8888"

    def color_status(val):
        color = _STATUS_COLORS.get(val, "#888888")
        return f"color: {color}; font-weight: bold"

    styled = filtered.style.applymap(
        color_score, subset=["atm_score"]
    ).applymap(
        color_status, subset=["status"]
    )

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn("Ticker", width="small"),
            "price_tier": st.column_config.TextColumn("Tier", width="small"),
            "atm_score": st.column_config.NumberColumn("ATM Score", format="%.1f"),
            "status": st.column_config.TextColumn("Status", width="small"),
            "first_seen": st.column_config.DatetimeColumn("First Seen", width="medium"),
            "last_scored": st.column_config.DatetimeColumn("Last Scored", width="medium"),
        },
    )

    # Click to view detail
    tickers = filtered["ticker"].tolist()
    if tickers:
        selected = st.selectbox(
            "Select ticker for detail view",
            ["", *tickers],
            key="candidate_select",
        )
        if selected:
            st.session_state["detail_ticker"] = selected
            st.info(f"Switch to 'Stock Detail' page to view {selected}")


# ── Page: Alerts ────────────────────────────────────────────────

def page_alerts():
    st.header("Alerts Feed")

    if not db_exists():
        st.info("No database found. Run the system to generate data.")
        return

    # Controls
    col1, col2 = st.columns(2)
    with col1:
        limit = st.slider("Show last N alerts", 10, 500, 100)
    with col2:
        severities = st.multiselect(
            "Severity filter",
            ["CRITICAL", "HIGH", "WARNING", "INFO"],
            default=["CRITICAL", "HIGH", "WARNING", "INFO"],
        )

    if not severities:
        st.warning("Select at least one severity level.")
        return

    placeholders = ",".join(["?"] * len(severities))
    df = query_df(
        f"""
        SELECT
            id, ticker, timestamp, alert_type, severity, message, acknowledged
        FROM alerts
        WHERE severity IN ({placeholders})
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (*severities, limit),
    )

    if df.empty:
        st.info("No alerts recorded yet.")
        return

    # Summary
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Shown", len(df))
    critical_count = len(df[df["severity"] == "CRITICAL"])
    m2.metric("Critical", critical_count)
    unacked = len(df[df["acknowledged"] == 0])
    m3.metric("Unacknowledged", unacked)

    # Display alerts with color coding
    for _, row in df.iterrows():
        severity = row["severity"]
        color = _SEVERITY_COLORS.get(severity, "#888888")
        ack_icon = "" if row["acknowledged"] else " [NEW]"

        with st.container():
            st.markdown(
                f'<div style="border-left: 4px solid {color}; '
                f'padding: 8px 12px; margin-bottom: 8px; '
                f'background-color: rgba(0,0,0,0.2); border-radius: 4px;">'
                f'<strong style="color: {color}">{severity}</strong>'
                f'{ack_icon} | '
                f'<strong>{row["ticker"]}</strong> | '
                f'{row["alert_type"]} | '
                f'<small>{row["timestamp"]}</small>'
                f'<br/>{row["message"] or ""}'
                f'</div>',
                unsafe_allow_html=True,
            )


# ── Page: Stock Detail ──────────────────────────────────────────

def page_stock_detail():
    st.header("Stock Detail")

    if not db_exists():
        st.info("No database found. Run the system to generate data.")
        return

    # Get available tickers
    tickers_df = query_df("SELECT DISTINCT ticker FROM candidates ORDER BY ticker")
    if tickers_df.empty:
        st.info("No candidates in the database yet.")
        return

    tickers = tickers_df["ticker"].tolist()
    default_idx = 0
    if "detail_ticker" in st.session_state and st.session_state["detail_ticker"] in tickers:
        default_idx = tickers.index(st.session_state["detail_ticker"])

    ticker = st.selectbox("Select Ticker", tickers, index=default_idx)

    if not ticker:
        return

    # ── Candidate Info ──
    info = query_df(
        "SELECT * FROM candidates WHERE ticker = ? LIMIT 1", (ticker,)
    )
    if not info.empty:
        row = info.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ticker", row["ticker"])
        c2.metric("Tier", row["price_tier"])
        score = row.get("atm_score")
        c3.metric("ATM Score", score if pd.notna(score) else "—")
        c4.metric("Status", row["status"])

    # ── Daily Scores ──
    st.subheader("Daily Scores")
    scores_df = query_df(
        """
        SELECT date,
            CAST(atm_score AS REAL) as atm_score,
            CAST(stability_score AS REAL) as stability,
            CAST(l2_score AS REAL) as l2,
            CAST(volume_score AS REAL) as volume,
            CAST(dilution_score AS REAL) as dilution,
            CAST(ts_score AS REAL) as ts,
            CAST(ohi_score AS REAL) as ohi
        FROM daily_scores
        WHERE ticker = ?
        ORDER BY date DESC
        LIMIT 60
        """,
        (ticker,),
    )

    if scores_df.empty:
        st.info("No daily scores recorded for this ticker.")
    else:
        # ATM score trend chart
        chart_df = scores_df.sort_values("date")
        st.line_chart(
            chart_df.set_index("date")[["atm_score"]],
            use_container_width=True,
        )

        # Component breakdown
        st.dataframe(
            scores_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "date": st.column_config.TextColumn("Date"),
                "atm_score": st.column_config.NumberColumn("ATM", format="%.1f"),
                "stability": st.column_config.NumberColumn("Stability", format="%.1f"),
                "l2": st.column_config.NumberColumn("L2", format="%.1f"),
                "volume": st.column_config.NumberColumn("Volume", format="%.1f"),
                "dilution": st.column_config.NumberColumn("Dilution", format="%.1f"),
                "ts": st.column_config.NumberColumn("T&S", format="%.1f"),
                "ohi": st.column_config.NumberColumn("OHI", format="%.1f"),
            },
        )

    # ── L2 Snapshots ──
    st.subheader("L2 Snapshots")
    l2_df = query_df(
        """
        SELECT
            timestamp,
            CAST(imbalance_ratio AS REAL) as imbalance_ratio,
            total_bid_shares,
            total_ask_shares,
            bid_levels,
            ask_levels
        FROM l2_snapshots
        WHERE ticker = ?
        ORDER BY timestamp DESC
        LIMIT 50
        """,
        (ticker,),
    )

    if l2_df.empty:
        st.info("No L2 snapshots recorded for this ticker.")
    else:
        # Imbalance ratio trend
        l2_chart = l2_df.sort_values("timestamp")
        if l2_chart["imbalance_ratio"].notna().any():
            st.line_chart(
                l2_chart.set_index("timestamp")[["imbalance_ratio"]],
                use_container_width=True,
            )

        # Bid/Ask share comparison
        st.dataframe(
            l2_df[["timestamp", "imbalance_ratio", "total_bid_shares", "total_ask_shares"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "timestamp": st.column_config.TextColumn("Time"),
                "imbalance_ratio": st.column_config.NumberColumn("Ratio", format="%.2f"),
                "total_bid_shares": st.column_config.NumberColumn("Bid Shares", format="%d"),
                "total_ask_shares": st.column_config.NumberColumn("Ask Shares", format="%d"),
            },
        )

    # ── Volume History (from trades table) ──
    st.subheader("Volume History")
    vol_df = query_df(
        """
        SELECT
            DATE(timestamp) as date,
            COUNT(*) as trade_count,
            SUM(size) as total_volume,
            SUM(CASE WHEN side = 'ask' THEN 1 ELSE 0 END) as ask_hits,
            SUM(CASE WHEN side = 'bid' THEN 1 ELSE 0 END) as bid_hits
        FROM trades
        WHERE ticker = ?
        GROUP BY DATE(timestamp)
        ORDER BY date DESC
        LIMIT 30
        """,
        (ticker,),
    )

    if vol_df.empty:
        st.info("No trade history recorded for this ticker.")
    else:
        vol_chart = vol_df.sort_values("date")
        st.bar_chart(
            vol_chart.set_index("date")[["total_volume"]],
            use_container_width=True,
        )

        st.dataframe(
            vol_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "date": st.column_config.TextColumn("Date"),
                "trade_count": st.column_config.NumberColumn("Trades"),
                "total_volume": st.column_config.NumberColumn("Volume", format="%d"),
                "ask_hits": st.column_config.NumberColumn("Buys (Ask)"),
                "bid_hits": st.column_config.NumberColumn("Sells (Bid)"),
            },
        )

    # ── Recent Alerts for this ticker ──
    st.subheader("Recent Alerts")
    alerts_df = query_df(
        """
        SELECT timestamp, alert_type, severity, message
        FROM alerts
        WHERE ticker = ?
        ORDER BY timestamp DESC
        LIMIT 20
        """,
        (ticker,),
    )

    if alerts_df.empty:
        st.info("No alerts for this ticker.")
    else:
        for _, row in alerts_df.iterrows():
            color = _SEVERITY_COLORS.get(row["severity"], "#888888")
            st.markdown(
                f'<div style="border-left: 3px solid {color}; '
                f'padding: 4px 8px; margin-bottom: 4px;">'
                f'<strong style="color: {color}">{row["severity"]}</strong> | '
                f'{row["alert_type"]} | {row["timestamp"]}'
                f'<br/><small>{row["message"] or ""}</small>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ── Main App ────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="ATM Trading Engine",
        page_icon="$",
        layout="wide",
    )

    st.title("ATM Trading Engine")

    # Sidebar navigation
    page = st.sidebar.radio(
        "Navigation",
        ["Candidates", "Alerts", "Stock Detail"],
    )

    # DB path override
    with st.sidebar.expander("Settings"):
        custom_db = st.text_input("Database path", value=get_db_path())
        if custom_db:
            st.session_state["db_path"] = custom_db

        if st.button("Refresh"):
            st.cache_data.clear()
            st.rerun()

    # Route to page
    if page == "Candidates":
        page_candidates()
    elif page == "Alerts":
        page_alerts()
    elif page == "Stock Detail":
        page_stock_detail()


if __name__ == "__main__":
    main()
