# VPS + IB Gateway: Always-On Engine — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Containerize the ATM engine and deploy it alongside IB Gateway on a Hetzner VPS for 24/7 operation.

**Architecture:** Two Docker containers (IB Gateway + engine) on a Hetzner CX22 VPS, connected via Docker bridge network. Engine connects to Gateway's socat port 4004 (paper). Railway PG and Vercel dashboard unchanged.

**Tech Stack:** Docker, Docker Compose, gnzsnz/ib-gateway image, Python 3.12-slim, Hetzner Cloud

**Spec:** `docs/superpowers/specs/2026-04-28-vps-ib-gateway-design.md`

---

## Chunk 1: Code Changes (local — no VPS needed)

### Task 1: Merge Eldar's L2 slot reservation branch

**Files:**
- Modify: `src/broker/ibkr.py:27-30,46,217-226`
- Modify: `config/settings.py:18`
- Modify: `tests/test_ibkr_contract.py:56`

- [ ] **Step 1: Merge the branch**

```bash
git merge origin/fix/l2-reserve-slot-for-tws --no-edit
```

- [ ] **Step 2: Run tests to verify merge is clean**

Run: `cd /Users/shay/otc && .venv/bin/pytest tests/ -x -q`
Expected: All tests pass (360+)

- [ ] **Step 3: Commit merge** (git merge already commits)

Verify with `git log --oneline -3` — should show merge commit.

---

### Task 2: Fix reconnect loop — add max attempts with sys.exit

**Files:**
- Modify: `src/broker/ibkr.py:20,376-395`
- Create: `tests/test_reconnect_limit.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_reconnect_limit.py`:

```python
"""Tests for IBAdapter reconnect loop max attempts."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.event_bus import EventBus


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def adapter(bus):
    with patch("src.broker.ibkr.get_settings") as mock_settings:
        mock_settings.return_value.ibkr.host = "127.0.0.1"
        mock_settings.return_value.ibkr.port = 7497
        mock_settings.return_value.ibkr.client_id_data = 1
        mock_settings.return_value.ibkr.timeout = 10
        mock_settings.return_value.ibkr.max_l2_subscriptions = 2

        from src.broker.ibkr import IBAdapter
        a = IBAdapter(event_bus=bus)
    return a


@pytest.mark.asyncio
async def test_reconnect_exits_after_max_attempts(adapter):
    """Engine should sys.exit(1) after _MAX_RECONNECT_ATTEMPTS failures."""
    # Make every connectAsync call fail
    adapter._ib.connectAsync = AsyncMock(side_effect=ConnectionError("refused"))
    adapter._ib.isConnected = MagicMock(return_value=False)

    with pytest.raises(SystemExit) as exc_info:
        await adapter._reconnect_loop()

    assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_reconnect_succeeds_before_max(adapter):
    """Engine should reconnect if connection succeeds within limit."""
    call_count = 0

    async def connect_eventually(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("refused")
        # Success on 3rd try — make isConnected return True
        adapter._ib.isConnected = MagicMock(return_value=True)

    adapter._ib.connectAsync = AsyncMock(side_effect=connect_eventually)
    adapter._ib.isConnected = MagicMock(return_value=False)
    adapter._resubscribe_all = AsyncMock()

    # Should NOT exit
    await adapter._reconnect_loop()

    assert call_count == 3
    adapter._resubscribe_all.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_reconnect_limit.py -v`
Expected: FAIL — `_reconnect_loop` never exits, test hangs or no SystemExit raised.

**Important:** This test will hang because the current loop is infinite. Kill it after 5 seconds with Ctrl+C. That confirms the bug exists.

- [ ] **Step 3: Implement the fix**

In `src/broker/ibkr.py`, add the constant after line 20 (`_MAX_BACKOFF = 60`):

```python
_MAX_RECONNECT_ATTEMPTS = 50
```

Replace the `_reconnect_loop` method (lines 376-395) with:

```python
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
                import sys
                sys.exit(1)
            logger.info("ibkr_reconnecting", backoff=self._backoff, attempt=attempts)
            try:
                await self._ib.connectAsync(
                    host=self._settings.host,
                    port=self._settings.port,
                    clientId=self._settings.client_id_data,
                    timeout=self._settings.timeout,
                )
                self._backoff = 1
                logger.info("ibkr_reconnected", after_attempts=attempts)
                await self._resubscribe_all()
                return
            except Exception:
                logger.warning("ibkr_reconnect_failed", backoff=self._backoff, attempt=attempts)
                await asyncio.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, _MAX_BACKOFF)
        self._reconnecting = False
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_reconnect_limit.py -v`
Expected: 2 passed

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/broker/ibkr.py tests/test_reconnect_limit.py
git commit -m "fix: add max reconnect attempts (50), sys.exit for Docker restart"
```

---

### Task 3: Create Dockerfile

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

Create `.dockerignore`:

```
.git
.gitignore
.env
.env.*
!.env.example
tests/
docs/
logs/
data/
*.egg-info/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
dashboard/
README.md
CLAUDE.md
ruff.toml
setup.sh
start.sh
```

- [ ] **Step 2: Create `Dockerfile`**

Create `Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# System deps for asyncpg/greenlet compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python deps — cached layer unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY config/ config/
COPY src/ src/
COPY scripts/ scripts/
COPY shared/ shared/

# Runtime dirs (ephemeral — not mounted as volumes)
RUN mkdir -p data logs

CMD ["python", "scripts/run_system.py"]
```

- [ ] **Step 3: Test Docker build locally**

Run: `cd /Users/shay/otc && docker build -t atm-engine:test .`
Expected: Build succeeds, final image ~250MB

- [ ] **Step 4: Verify the image runs (will fail on IBKR connect — that's expected)**

Run: `docker run --rm -e DATABASE_URL=sqlite+aiosqlite:///data/atm.db atm-engine:test`
Expected: Starts, logs "ibkr_connecting", fails with connection refused (no Gateway). Ctrl+C to stop. This proves the image boots and imports work.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: add Dockerfile for engine containerization"
```

---

### Task 4: Create docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
name: atm-engine

services:
  ib-gateway:
    image: ghcr.io/gnzsnz/ib-gateway:stable
    restart: always
    env_file:
      - .env.gateway
    ports:
      - "127.0.0.1:5900:5900"
    volumes:
      - ib-gateway-settings:/home/ibgateway/Jts
    networks:
      - atm-net
    healthcheck:
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
      IBKR_HOST: ib-gateway
      IBKR_PORT: 4004
    networks:
      - atm-net

volumes:
  ib-gateway-settings:

networks:
  atm-net:
    driver: bridge
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add docker-compose for IB Gateway + engine stack"
```

---

### Task 5: Create environment file templates

**Files:**
- Create: `.env.production.example`
- Create: `.env.gateway.example`
- Modify: `.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Create `.env.production.example`**

```env
# ATM Engine — Production (VPS)
# Copy to .env.production and fill in values

# IBKR connection — overridden by docker-compose environment block
# IBKR_HOST=ib-gateway  (set in docker-compose.yml)
# IBKR_PORT=4004         (set in docker-compose.yml — socat paper port)
IBKR_CLIENT_ID_DATA=2
IBKR_TIMEOUT=30

# Database — Railway PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@HOST.proxy.rlwy.net:PORT/railway

# Telegram Alerts
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Risk
RISK_MAX_POSITION_PCT=0.05
RISK_MAX_LOSS_PCT=0.02
RISK_PORTFOLIO_VALUE=10000

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

- [ ] **Step 2: Create `.env.gateway.example`**

```env
# IB Gateway — Credentials (VPS)
# Copy to .env.gateway and fill in values
# See: https://github.com/gnzsnz/ib-gateway-docker

TWS_USERID=
TWS_PASSWORD=
TRADING_MODE=paper
VNC_SERVER_PASSWORD=
TWOFA_TIMEOUT_ACTION=restart
RELOGIN_AFTER_TWOFA_TIMEOUT=yes
TWOFA_EXIT_INTERVAL=60
EXISTING_SESSION_DETECTED_ACTION=primary
READ_ONLY_API=yes
AUTO_RESTART_TIME=11:55 PM
TIME_ZONE=America/New_York
```

- [ ] **Step 3: Update `.env.example`**

Replace the full content of `.env.example`:

```env
# ATM Engine — Local Development (TWS on localhost)
# Copy to .env and fill in values

# IBKR Connection (TWS)
IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID_SCANNER=1
IBKR_CLIENT_ID_DATA=2
IBKR_MAX_L2_SUBSCRIPTIONS=2

# For VPS deployment with IB Gateway, use docker-compose.yml which sets:
#   IBKR_HOST=ib-gateway
#   IBKR_PORT=4004  (paper, socat) or 4003 (live, socat)

# Telegram Alerts
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Database — Railway PostgreSQL
# Engine: postgresql+asyncpg://user:pass@host:port/db
# Dashboard: postgresql://user:pass@host:port/db (no +asyncpg)
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@HOST.railway.app:PORT/railway

# Risk
RISK_MAX_POSITION_PCT=0.05
RISK_MAX_LOSS_PCT=0.02
RISK_PORTFOLIO_VALUE=10000

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

- [ ] **Step 4: Update `.gitignore`**

Add these lines to `.gitignore` if not already present:

```
.env.production
.env.gateway
```

- [ ] **Step 5: Commit**

```bash
git add .env.production.example .env.gateway.example .env.example .gitignore
git commit -m "feat: add VPS env templates, update .env.example for Gateway ports"
```

---

### Task 6: Update CLAUDE.md with IB Gateway details

**Files:**
- Modify: `CLAUDE.md` (IBKR Connection Details section, ~line 537-549)
- Modify: `CLAUDE.md` (Running the System section, ~line 856)
- Modify: `CLAUDE.md` (Build Progress section — add Phase 14)

- [ ] **Step 1: Add Gateway ports to IBKR Connection Details**

After the existing TWS port lines (`Paper port: 7497`, `Live port: 7496`), add:

```
- **IB Gateway (Docker)**: Paper socat port: 4004, Live socat port: 4003. The gnzsnz/ib-gateway image uses socat to remap internal ports (4001/4002) to external (4003/4004). Container-to-container connections use socat ports.
- **Docker deployment**: `docker-compose.yml` at repo root. IB Gateway + engine. See `docs/superpowers/specs/2026-04-28-vps-ib-gateway-design.md`.
```

- [ ] **Step 2: Add Docker run commands to Running the System**

After the existing run commands, add:

```bash
# Docker deployment (VPS — IB Gateway + Engine)
docker compose up -d              # start both containers
docker compose logs -f atm-engine # follow engine logs
docker compose down               # stop everything
```

- [ ] **Step 3: Add Phase 14 to Build Progress**

Add after Phase 13:

```markdown
### Phase 14 — VPS + IB Gateway Containerization (2026-04-28)

Always-on deployment: engine containerized with Docker, runs alongside IB Gateway on Hetzner VPS.

**Code changes:**
- `Dockerfile` — Python 3.12-slim engine image
- `docker-compose.yml` — IB Gateway (gnzsnz/ib-gateway:stable) + engine, bridge network, healthcheck
- `.dockerignore` — excludes tests, docs, dashboard, data
- `.env.production.example` + `.env.gateway.example` — VPS env templates
- `src/broker/ibkr.py` — max reconnect attempts (50), sys.exit(1) for Docker restart
- Merged `fix/l2-reserve-slot-for-tws` — L2 slots configurable via `IBKR_MAX_L2_SUBSCRIPTIONS` (default 2)

**Topology:**
- Engine: Hetzner VPS Docker container → connects to IB Gateway container on socat port 4004 (paper)
- Database: Railway PostgreSQL (unchanged)
- Dashboard: Vercel (unchanged)
- Eldar's laptop: optional — uses dashboard + TWS for manual trading
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for Phase 14 — VPS + IB Gateway"
```

---

## Chunk 2: VPS Provisioning & Deployment

### Task 7: Provision Hetzner VPS

This task is done in the browser/Hetzner console, not in code.

- [ ] **Step 1: Create Hetzner Cloud account** (if not already)

Go to https://console.hetzner.cloud — sign up or log in.

- [ ] **Step 2: Create CX22 server**

- Location: Ashburn, VA (us-east)
- Image: Ubuntu 24.04
- Type: CX22 (2 vCPU, 4GB RAM, 40GB disk — €4.51/mo)
- SSH key: add Shay's public key
- Name: `atm-engine`

- [ ] **Step 3: SSH in and install Docker**

```bash
ssh root@<vps-ip>
curl -fsSL https://get.docker.com | sh
```

- [ ] **Step 4: Clone repo**

```bash
git clone https://github.com/Shaygr34/OTC.git /opt/atm-engine
cd /opt/atm-engine
```

- [ ] **Step 5: Create env files from templates**

```bash
cp .env.production.example .env.production
cp .env.gateway.example .env.gateway
nano .env.production  # fill in Railway PG URL, Telegram tokens
nano .env.gateway     # fill in Eldar's IBKR credentials
```

---

### Task 8: Deploy and verify

- [ ] **Step 1: Pull IB Gateway image and build engine**

```bash
cd /opt/atm-engine
docker compose pull ib-gateway
docker compose build atm-engine
```

- [ ] **Step 2: Start the stack**

```bash
docker compose up -d
```

- [ ] **Step 3: Watch IB Gateway login**

```bash
docker compose logs -f ib-gateway
```

Expected: IBC starts, authenticates with IBKR, Gateway API becomes available. Look for "IB Gateway is ready" or similar.

If 2FA prompt appears: Eldar needs to approve on IBKR Mobile app.

- [ ] **Step 4: Watch engine start**

```bash
docker compose logs -f atm-engine
```

Expected: `ibkr_connected`, `system_started`, `db_candidates_loaded`. Should see the same startup sequence as when running on Eldar's machine.

- [ ] **Step 5: Verify data in dashboard**

Open https://dashboard-bay-delta-68.vercel.app — should show "Engine Online" (or at least new data timestamps).

- [ ] **Step 6: VNC tunnel for debugging (optional)**

From local machine:
```bash
ssh -L 5900:localhost:5900 root@<vps-ip>
```
Then connect VNC viewer to `localhost:5900` with the password from `.env.gateway`.

---

### Task 9: Push all changes to main

- [ ] **Step 1: Push to GitHub**

```bash
cd /Users/shay/otc
git push origin main
```

- [ ] **Step 2: Pull on VPS**

```bash
ssh root@<vps-ip> "cd /opt/atm-engine && git pull && docker compose up -d --build atm-engine"
```

---

## Summary

| Task | What | Where |
|------|------|-------|
| 1 | Merge Eldar's L2 branch | Local |
| 2 | Fix reconnect loop + tests | Local |
| 3 | Dockerfile + .dockerignore | Local |
| 4 | docker-compose.yml | Local |
| 5 | Env templates + .gitignore | Local |
| 6 | Update CLAUDE.md (Phase 14) | Local |
| 7 | Provision Hetzner VPS | Browser |
| 8 | Deploy and verify | VPS |
| 9 | Push to main | Local + VPS |

Tasks 1-6 are code changes that can be done now. Tasks 7-8 require Hetzner account + Eldar's IBKR credentials. Task 9 ties it together.
