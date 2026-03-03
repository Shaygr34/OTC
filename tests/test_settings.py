"""Tests for config/settings.py — defaults and env override."""

from decimal import Decimal

from config.settings import Settings, _reset_settings, get_settings


class TestSettingsDefaults:
    def test_ibkr_defaults(self):
        s = Settings()
        assert s.ibkr.host == "127.0.0.1"
        assert s.ibkr.port == 7497
        assert s.ibkr.client_id_scanner == 1
        assert s.ibkr.client_id_data == 2

    def test_telegram_defaults(self):
        s = Settings()
        assert s.telegram.bot_token == ""
        assert s.telegram.enabled is False

    def test_database_defaults(self):
        s = Settings()
        assert s.database.url == "sqlite+aiosqlite:///data/atm.db"

    def test_risk_defaults(self):
        s = Settings()
        assert s.risk.max_position_pct == Decimal("0.05")
        assert s.risk.max_loss_pct == Decimal("0.02")
        assert s.risk.portfolio_value == Decimal("10000")

    def test_log_defaults(self):
        s = Settings()
        assert s.log.level == "INFO"
        assert s.log.format == "json"


class TestSettingsEnvOverride:
    def test_ibkr_port_override(self, monkeypatch):
        monkeypatch.setenv("IBKR_PORT", "7496")
        s = Settings()
        assert s.ibkr.port == 7496

    def test_risk_portfolio_override(self, monkeypatch):
        monkeypatch.setenv("RISK_PORTFOLIO_VALUE", "50000")
        s = Settings()
        assert s.risk.portfolio_value == Decimal("50000")

    def test_database_url_override(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///test.db")
        s = Settings()
        assert s.database.url == "sqlite+aiosqlite:///test.db"


class TestGetSettings:
    def test_singleton(self):
        _reset_settings()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_reset(self):
        _reset_settings()
        s1 = get_settings()
        _reset_settings()
        s2 = get_settings()
        # After reset, a new instance is created
        assert s1 is not s2
