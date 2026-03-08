"""Shared pytest fixtures for the health-concierge test suite."""

from dataclasses import dataclass, field
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Provide a temporary SQLite database path."""
    return tmp_path / "test_concierge.db"


@dataclass
class TestSettings:
    """Dummy settings for tests — no real credentials."""

    telegram_bot_token: str = "test-telegram-token"
    claude_api_key: str = "test-claude-key"
    claude_model: str = "claude-sonnet-4-20250514"
    garmin_email: str = "test@example.com"
    garmin_password: str = "test-password"
    oura_access_token: str = "test-oura-token"
    strava_client_id: str = "12345"
    strava_client_secret: str = "test-strava-secret"
    strava_refresh_token: str = "test-strava-refresh"
    renpho_email: str = ""
    renpho_password: str = ""
    db_path: str = ""
    user_telegram_ids: list[str] = field(default_factory=lambda: ["111111111"])
    log_level: str = "DEBUG"


@pytest.fixture
def test_settings(tmp_db_path: Path) -> TestSettings:
    """Provide test settings with a temporary DB path."""
    s = TestSettings()
    s.db_path = str(tmp_db_path)
    return s
