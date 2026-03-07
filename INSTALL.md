# Local Installation Guide (Windows)

Complete setup guide for running the ATM Trading Engine on a fresh Windows machine.

---

## Prerequisites

Install these 3 programs first. Download each from your browser, run the installer.

| # | Software | Download Link | Notes |
|---|----------|---------------|-------|
| 1 | **Node.js 18+** | https://nodejs.org | Click the LTS button, run the `.msi` installer |
| 2 | **Python 3.12+** | https://www.python.org/downloads/ | **CHECK "Add python.exe to PATH"** on the first installer screen |
| 3 | **Git** | https://git-scm.com/download/win | Keep all default options |

> **Important:** After installing all 3, close your terminal and open a new one.

Verify everything works:

```cmd
node --version
python --version
git --version
```

All 3 should print version numbers.

---

## Step 1: Install Claude Code CLI

```cmd
npm install -g @anthropic-ai/claude-code
```

Verify:

```cmd
claude --version
```

---

## Step 2: Install GitHub CLI

```cmd
winget install GitHub.cli
```

If `winget` is not available, download from: https://cli.github.com/

Then authenticate with your GitHub account:

```cmd
gh auth login
```

Follow the prompts (browser-based OAuth is easiest).

---

## Step 3: Clone the Repository

```cmd
gh repo clone Shaygr34/OTC
cd OTC
```

---

## Step 4: Set Up Python Environment

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
```

Edit `.env` with your settings if needed (IBKR ports, Telegram token, etc.).

---

## Step 5: Verify Installation

Run the test suite:

```cmd
pytest
```

All 293 tests should pass.

Run the engine (uses MockAdapter by default, no IBKR needed):

```cmd
python scripts\run_system.py
```

---

## Step 6: Use Claude Code

From inside the project directory:

```cmd
cd OTC
claude
```

This opens an interactive Claude Code session with full project context.

---

## Troubleshooting

### "X is not recognized as an internal or external command"

You need to close and reopen your terminal after installing software. The old terminal
does not know about newly installed programs.

### Python says "python is not recognized"

You did not check "Add python.exe to PATH" during installation. Uninstall Python,
reinstall, and make sure to check that box on the first screen.

### `pip install` fails with permission errors

Make sure your virtual environment is activated. You should see `(.venv)` at the
start of your terminal prompt. Run `.venv\Scripts\activate` first.

---

## For Mac/Linux Users

Replace Windows-specific commands:

| Windows | Mac/Linux |
|---------|-----------|
| `.venv\Scripts\activate` | `source .venv/bin/activate` |
| `copy .env.example .env` | `cp .env.example .env` |
| `python scripts\run_system.py` | `python scripts/run_system.py` |
| `winget install GitHub.cli` | `brew install gh` (Mac) or `sudo apt install gh` (Linux) |
