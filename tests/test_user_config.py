"""Tests for config/user_config.py — user configuration persistence."""

import json
from pathlib import Path
from unittest.mock import patch

from config.user_config import (
    _deep_merge,
    config_exists,
    load_config,
    save_config,
    update_config,
    wizard_completed,
)


def test_deep_merge_simple():
    base = {"a": 1, "b": 2}
    override = {"b": 3, "c": 4}
    assert _deep_merge(base, override) == {"a": 1, "b": 3, "c": 4}


def test_deep_merge_nested():
    base = {"x": {"a": 1, "b": 2}, "y": 3}
    override = {"x": {"b": 99}}
    result = _deep_merge(base, override)
    assert result == {"x": {"a": 1, "b": 99}, "y": 3}


def test_load_config_returns_defaults_when_no_file(tmp_path):
    fake_path = tmp_path / "user_config.json"
    with patch("config.user_config._CONFIG_PATH", fake_path):
        cfg = load_config()
    assert cfg["language"] == "en"
    assert cfg["ibkr"]["host"] == "127.0.0.1"
    assert cfg["risk"]["max_position_pct"] == 5.0


def test_save_and_load_roundtrip(tmp_path):
    fake_path = tmp_path / "user_config.json"
    with patch("config.user_config._CONFIG_PATH", fake_path):
        save_config({"language": "he", "wizard_completed": True})
        cfg = load_config()
    assert cfg["language"] == "he"
    assert cfg["wizard_completed"] is True
    # Defaults should be merged in
    assert cfg["ibkr"]["host"] == "127.0.0.1"


def test_config_exists_false_when_missing(tmp_path):
    fake_path = tmp_path / "user_config.json"
    with patch("config.user_config._CONFIG_PATH", fake_path):
        assert config_exists() is False


def test_config_exists_true_when_valid(tmp_path):
    fake_path = tmp_path / "user_config.json"
    fake_path.write_text('{"language": "en"}')
    with patch("config.user_config._CONFIG_PATH", fake_path):
        assert config_exists() is True


def test_update_config(tmp_path):
    fake_path = tmp_path / "user_config.json"
    with patch("config.user_config._CONFIG_PATH", fake_path):
        cfg = update_config(language="he", ibkr={"port": 7496})
    assert cfg["language"] == "he"
    assert cfg["ibkr"]["port"] == 7496
    assert cfg["ibkr"]["host"] == "127.0.0.1"  # default preserved


def test_wizard_completed_default_false(tmp_path):
    fake_path = tmp_path / "user_config.json"
    with patch("config.user_config._CONFIG_PATH", fake_path):
        assert wizard_completed() is False


def test_wizard_completed_true_after_save(tmp_path):
    fake_path = tmp_path / "user_config.json"
    with patch("config.user_config._CONFIG_PATH", fake_path):
        save_config({"wizard_completed": True})
        assert wizard_completed() is True
