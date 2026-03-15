"""User configuration persistence — loads/saves data/user_config.json.

Merges user overrides on top of constants.py / settings.py defaults.
The dashboard reads/writes this file; changes take effect immediately
on Streamlit rerun.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "user_config.json"

_DEFAULTS: dict[str, Any] = {
    "language": "en",
    "ibkr": {
        "host": "127.0.0.1",
        "port": 7497,
        "client_id": 1,
    },
    "telegram": {
        "bot_token": "",
        "chat_id": "",
        "enabled": False,
    },
    "risk": {
        "max_position_pct": 5.0,
        "max_loss_pct": 2.0,
        "portfolio_value": 10000,
        "max_hold_hours_trips": 4,
        "max_hold_days_dubs": 2,
        "max_hold_days_pennies": 5,
        "ohi_strong": 65,
        "ohi_neutral_low": 40,
        "atm_min_trade": 80,
        "atm_min_watchlist": 70,
        "l2_imbalance_min": 3.0,
        "dilution_exit_trigger": 3,
    },
    "wizard_completed": False,
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def get_config_path() -> Path:
    """Return the path to user_config.json."""
    return _CONFIG_PATH


def config_exists() -> bool:
    """Check whether user_config.json exists and is valid JSON."""
    if not _CONFIG_PATH.exists():
        return False
    try:
        json.loads(_CONFIG_PATH.read_text())
        return True
    except (json.JSONDecodeError, OSError):
        return False


def load_config() -> dict[str, Any]:
    """Load config from disk, merged on top of defaults.

    Returns defaults if file doesn't exist or is invalid.
    """
    base = json.loads(json.dumps(_DEFAULTS))  # deep copy
    if not _CONFIG_PATH.exists():
        return base
    try:
        user_data = json.loads(_CONFIG_PATH.read_text())
        return _deep_merge(base, user_data)
    except (json.JSONDecodeError, OSError):
        return base


def save_config(config: dict[str, Any]) -> None:
    """Save config dict to data/user_config.json."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False))


def update_config(**kwargs: Any) -> dict[str, Any]:
    """Load config, update top-level keys, save, and return the result."""
    cfg = load_config()
    for key, val in kwargs.items():
        if key in cfg and isinstance(cfg[key], dict) and isinstance(val, dict):
            cfg[key] = _deep_merge(cfg[key], val)
        else:
            cfg[key] = val
    save_config(cfg)
    return cfg


def wizard_completed() -> bool:
    """Check if the first-run wizard has been completed."""
    return load_config().get("wizard_completed", False)
