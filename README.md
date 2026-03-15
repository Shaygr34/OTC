# ATM Trading Engine

Decision-support system for OTC penny stock ATM pattern trading. Scans candidates, analyzes L2 depth, detects dilution, scores ATM probability, and alerts via Telegram.

## Quick Start

```bash
git clone <repo-url> && cd OTC
bash setup.sh        # installs everything + seeds demo data
bash start.sh        # starts engine (mock) + dashboard
```

Open **http://localhost:8501** to see the dashboard.

## Live Mode (with IBKR)

1. Start TWS or IB Gateway (paper trading port **7497**)
2. Edit `.env`:
   ```
   ATM_USE_IBKR=1
   ```
3. Edit `config/watchlist.yaml` - add tickers to monitor:
   ```yaml
   symbols:
     - ticker: ABCD
       exchange: PINK
     - ticker: EFGH
       exchange: GREY
   ```
4. Run:
   ```bash
   bash start.sh --live
   ```

## What It Does

- **Scans** OTC stocks by price tier, stability, and volume
- **Analyzes** L2 depth (imbalance ratio, bad MM detection, wall detection)
- **Monitors** volume anomalies, time & sales flow, dilution signals
- **Scores** each candidate 0-100 (ATM probability)
- **Alerts** via Telegram on critical events (optional)
- **Logs** every event to SQLite for analysis

## Commands

| Command | What it does |
|---------|-------------|
| `bash setup.sh` | First-time setup (venv, deps, demo data) |
| `bash start.sh` | Start engine + dashboard (mock mode) |
| `bash start.sh --live` | Start with real IBKR data |
| `.venv/bin/pytest tests/ -x -q` | Run tests |
| `.venv/bin/python scripts/seed_realistic.py` | Reset demo data |

## Requirements

- Python 3.12+
- TWS or IB Gateway (for live mode only)
