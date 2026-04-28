# VPS + IB Gateway: Always-On ATM Engine

**Date:** 2026-04-28
**Status:** Design
**Goal:** Move the ATM engine from Eldar's laptop to a cloud VPS with IB Gateway, enabling 24/7 scanning and scoring without human presence.

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│  Hetzner VPS (CX22 — 2 vCPU, 4GB RAM, €4.5/mo)  │
│  Ashburn, VA (US East) — low latency to IBKR      │
│                                                    │
│  docker compose up -d                              │
│                                                    │
│  ┌──────────────────┐   ┌───────────────────────┐ │
│  │  ib-gateway       │   │  atm-engine           │ │
│  │                   │   │                       │ │
│  │  Image: ghcr.io/  │   │  Image: built from    │ │
│  │  gnzsnz/ib-       │   │  repo Dockerfile      │ │
│  │  gateway:stable   │   │                       │ │
│  │                   │   │  scripts/run_system.py │ │
│  │  IB Gateway 10.37 │   │  Python 3.12          │ │
│  │  IBC 3.23         │   │                       │ │
│  │                   │   │                       │ │
│  │  API: 4003 (live) │──▶│  IBKR_HOST=ib-gateway │ │
│  │  API: 4004 (paper)│   │  IBKR_PORT=4004       │ │
│  │  VNC: 5900        │   │  DATABASE_URL=railway  │ │
│  └──────────────────┘   └───────────────────────┘ │
│                                                    │
└──────────────────────────────────────────────────┘
         │                        │
         │                        ▼
         │              [Railway PostgreSQL]
         │                        ▲
         │                        │
         │              [Vercel Dashboard]
         │
    [Eldar VNC tunnel for debug]
```

### What stays the same
- Railway PostgreSQL — no migration
- Vercel dashboard — no changes
- All engine code — zero modifications to scoring, analysis, or persistence

### What changes
- Engine connects to `ib-gateway:4004` (paper) or `ib-gateway:4003` (live) instead of `127.0.0.1:7497`
- IBKR_HOST and IBKR_PORT env vars point to the Gateway container
- Engine runs in a Docker container with its own Dockerfile
- IB Gateway handles authentication, 2FA, and connection lifecycle

---

## Docker Compose

```yaml
name: atm-engine

services:
  ib-gateway:
    image: ghcr.io/gnzsnz/ib-gateway:stable
    restart: always
    env_file:
      - .env.gateway
    ports:
      - "127.0.0.1:5900:5900"  # VNC — SSH tunnel only
    volumes:
      - ib-gateway-settings:/home/ibgateway/Jts
    networks:
      - atm-net
    healthcheck:
      # socat exposes API on 4003 (live) / 4004 (paper) inside container
      test: ["CMD-SHELL", "bash -c '</dev/tcp/localhost/4004'"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 120s

  atm-engine:
    build:
      context: .
      dockerfile: Dockerfile
    restart: always
    depends_on:
      ib-gateway:
        condition: service_healthy
    env_file:
      - .env.production
    environment:
      # socat ports: 4003 = live, 4004 = paper (NOT 4001/4002)
      IBKR_HOST: ib-gateway
      IBKR_PORT: 4004  # paper; change to 4003 for live
    networks:
      - atm-net

volumes:
  ib-gateway-settings:

networks:
  atm-net:
    driver: bridge
```

### Key design decisions

**`TRADING_MODE=paper`** — Start on paper. Switch to live by changing to `TRADING_MODE=live` and `IBKR_PORT=4003`.

**`env_file: .env.gateway`** on ib-gateway service — Credentials loaded from a separate file, not inlined in compose. Keeps secrets isolated.

**`READ_ONLY_API=yes`** — The engine is decision-support only, no order execution. This prevents accidental trades via API. Remove when we reach v3 (semi-automated execution).

**`TWOFA_TIMEOUT_ACTION=restart`** + **`RELOGIN_AFTER_TWOFA_TIMEOUT=yes`** — If 2FA times out, Gateway restarts and tries again. IBC handles IBKR's mobile 2FA notification automatically if the IBKR Mobile app is configured for auto-confirm.

**`AUTO_RESTART_TIME=11:55 PM`** — IBKR forces a daily restart. Schedule it during off-market hours (ET). Gateway reconnects automatically after restart.

**`EXISTING_SESSION_DETECTED_ACTION=primary`** — If Eldar opens TWS on his laptop while Gateway is running, Gateway takes priority. Eldar can still use TWS read-only, or we flip this to `secondary` if needed.

**`restart: always`** on both services — Docker restarts crashed containers automatically. Combined with the engine's reconnect loop (with the max-attempts fix), this creates multi-layer resilience.

**Healthcheck on ib-gateway** — Engine waits for Gateway to be healthy (socat port 4004 accepting connections) before starting. 120s start period gives Gateway time to authenticate. Uses `bash /dev/tcp` test since `nc` may not be installed in the image.

---

## Engine Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY config/ config/
COPY src/ src/
COPY scripts/ scripts/
COPY shared/ shared/

# Create data/logs dirs
RUN mkdir -p data logs

CMD ["python", "scripts/run_system.py"]
```

Minimal image. No dev dependencies. `gcc` needed for some asyncpg/greenlet compilation. Image size ~250MB.

---

## Environment Files

### `.env.production` (on VPS, gitignored)

```env
# IBKR — set via docker-compose environment override
# IBKR_HOST=ib-gateway (set in compose)
# IBKR_PORT=4002 (set in compose)
IBKR_CLIENT_ID_DATA=2
IBKR_TIMEOUT=30

# Database — Railway PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@centerbeam.proxy.rlwy.net:35200/railway

# Telegram
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_CHAT_ID=<chat_id>

# Risk
RISK_MAX_POSITION_PCT=0.05
RISK_MAX_LOSS_PCT=0.02
RISK_PORTFOLIO_VALUE=10000

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### `.env.gateway` (on VPS, gitignored)

```env
TWS_USERID=<eldar_username>
TWS_PASSWORD=<eldar_password>
TRADING_MODE=paper
VNC_SERVER_PASSWORD=<vnc_password>
TWOFA_TIMEOUT_ACTION=restart
RELOGIN_AFTER_TWOFA_TIMEOUT=yes
READ_ONLY_API=yes
AUTO_RESTART_TIME=11:55 PM
TIME_ZONE=America/New_York
```

---

## Bug Fixes Included in This Deploy

### Bug #1: Reconnect loop has no limit (Critical)

The engine retried 694 times over 3.5 days. Add max reconnect attempts to `IBAdapter._reconnect_loop()`:

```python
_MAX_RECONNECT_ATTEMPTS = 50

async def _reconnect_loop(self) -> None:
    self._reconnecting = True
    attempts = 0
    while self._reconnecting and not self._ib.isConnected():
        attempts += 1
        if attempts > _MAX_RECONNECT_ATTEMPTS:
            logger.critical(
                "ibkr_reconnect_exhausted",
                attempts=attempts,
                msg="Max reconnect attempts reached. Exiting.",
            )
            self._reconnecting = False
            # Exit process — Docker restart: always will relaunch us
            import sys
            sys.exit(1)
        # ... rest of existing loop
```

Docker's `restart: always` creates a clean retry cycle: engine exits -> Docker restarts it -> Gateway healthcheck gates startup -> clean reconnect. No infinite loop.

### Bug #2: Merge Eldar's L2 slot reservation branch

Merge `origin/fix/l2-reserve-slot-for-tws` before deploying. Reduces engine L2 slots from 3 to 2, configurable via `IBKR_MAX_L2_SUBSCRIPTIONS`.

---

## Code Changes Required

### 1. `config/settings.py` — IBKR port default

Current default is `7497` (TWS). IB Gateway socat ports are `4004` (paper) / `4003` (live). The env var `IBKR_PORT` already overrides this, so no code change needed for the VPS deploy — just set the env var. Keep the default at `7497` so local TWS development still works without setting env vars.

**Important:** The gnzsnz/ib-gateway image uses socat to remap ports. Inside the container, IB Gateway listens on 4001/4002, but socat re-exposes them as 4003 (live) / 4004 (paper). Container-to-container traffic on the Docker bridge network hits the socat ports.

### 2. `src/broker/ibkr.py` — Max reconnect attempts

Add `_MAX_RECONNECT_ATTEMPTS = 50` and the exit logic described above.

### 3. New files

- `Dockerfile` — Engine container (see above)
- `docker-compose.yml` — Full stack (see above)
- `.dockerignore` — Exclude tests, docs, data, logs, .env, .git, atm_trading_engine.egg-info
- `.env.production.example` — Template for VPS env vars
- `.env.gateway.example` — Template for IB Gateway credentials
- Update `.env.example` — Remove stale `ATM_USE_IBKR` reference, document both TWS and Gateway port options
- Update `CLAUDE.md` — Add IB Gateway ports (4003/4004) alongside TWS ports (7496/7497) in IBKR Connection Details

---

## Deployment Steps

### One-time setup (Hetzner)

1. Create CX22 server (Ashburn, VA), Ubuntu 24.04, SSH key
2. Install Docker + Docker Compose
3. Clone repo: `git clone git@github.com:Shaygr34/OTC.git`
4. Copy `.env.production` and `.env.gateway` with real credentials
5. `docker compose up -d`
6. Verify via VNC tunnel: `ssh -L 5900:localhost:5900 root@<vps-ip>` then connect VNC viewer
7. Check logs: `docker compose logs -f atm-engine`
8. Verify data flowing to Railway PG via dashboard

### Ongoing deployment (code updates)

**Option A (simple):** SSH into VPS, `git pull && docker compose up -d --build atm-engine`

**Option B (automated):** GitHub Actions workflow on push to main:
1. Build engine Docker image
2. Push to GitHub Container Registry
3. SSH into VPS and `docker compose pull && docker compose up -d`

Start with Option A. Add automation later when the manual process gets annoying.

### Switching paper → live

1. Change `.env.gateway`: `TRADING_MODE=live`
2. Change `docker-compose.yml` or `.env.production`: `IBKR_PORT=4003` (socat live port)
3. Update healthcheck port to `4003` in docker-compose.yml
4. Remove `READ_ONLY_API=yes` (only when ready for execution)
5. `docker compose up -d`

---

## Monitoring & Alerting

### Health signals

- **Engine heartbeat** — existing `engine_status.json` writes every 10s. Adapt to write a health endpoint or DB heartbeat row that the dashboard can read.
- **Docker healthcheck** — Gateway exposes socat port 4004 (paper), engine depends on it.
- **Dashboard "Engine Offline"** — already shows this when no recent data. Works as-is.

### What to add later

- Telegram alert when engine starts/stops/reconnects
- Dashboard shows "last data received" timestamp
- Uptime monitoring (UptimeRobot or similar on the VNC port or a /health endpoint)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| IBKR 2FA blocks auto-login | Configure IBKR Mobile for auto-confirm. TOTP fallback via IBC. `RELOGIN_AFTER_TWOFA_TIMEOUT=yes` retries. |
| Gateway crashes mid-session | `restart: always` + engine reconnect loop. Data already persisted to PG is safe. |
| Hetzner VPS goes down | Rare (<0.1% monthly), but add UptimeRobot alert. No data loss — PG is on Railway. |
| Eldar opens TWS while Gateway runs | `EXISTING_SESSION_DETECTED_ACTION=primary` — Gateway keeps priority. Eldar uses dashboard. |
| Railway PG connection from Hetzner | Already works — dashboard on Vercel connects from a different cloud too. Test latency. |
| Engine image gets stale | Manual `git pull + rebuild` for now. GitHub Actions later. |

---

## Out of Scope (Next Steps)

- Scanner (`reqScannerSubscription`) — separate feature, builds on this infra
- Tier-specific scoring — Eldar's spec needed first
- Vision-based chart analysis — depends on Ziva TA port + Eldar's spec
- T&S rotation manager — bug fix, not infra
- Telegram actionable alerts — feature, not infra
