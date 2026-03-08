"""Tests for the unified sync runner (scripts/sync_all.py)."""

from unittest.mock import patch, MagicMock

import pytest

from tests.conftest import TestSettings


@pytest.fixture
def mock_settings(test_settings):
    """Provide patched settings for sync_all tests."""
    with patch("scripts.sync_all.settings", test_settings):
        yield test_settings


@pytest.fixture
def mock_init_db():
    """Stub out init_db so no real DB is created."""
    with patch("scripts.sync_all.init_db") as m:
        yield m


def test_sync_all_continues_on_failure(mock_settings, mock_init_db):
    """If one sync raises, the others still run and results include the error."""
    mock_oura = MagicMock(side_effect=RuntimeError("oura is down"))
    mock_garmin = MagicMock(return_value={"activities": 2, "sleep": 1})
    mock_strava = MagicMock(return_value={"activities": 3})
    mock_renpho = MagicMock(return_value={"weight": 1})

    with (
        patch("scripts.sync_all.sync_oura", mock_oura),
        patch("scripts.sync_all.sync_garmin", mock_garmin),
        patch("scripts.sync_all.sync_strava", mock_strava),
        patch("scripts.sync_all.sync_renpho", mock_renpho),
    ):
        from scripts.sync_all import sync_all

        results = sync_all()

    user_id = mock_settings.user_telegram_ids[0]
    user_results = results[user_id]

    # Oura failed — should have error key
    assert "error" in user_results["oura"]
    assert "oura is down" in user_results["oura"]["error"]

    # Other syncs should have succeeded
    assert user_results["garmin"] == {"activities": 2, "sleep": 1}
    assert user_results["strava"] == {"activities": 3}
    assert user_results["renpho"] == {"weight": 1}

    # All four sync functions were called
    mock_oura.assert_called_once_with(user_id)
    mock_garmin.assert_called_once_with(user_id)
    mock_strava.assert_called_once_with(user_id)
    mock_renpho.assert_called_once_with(user_id)


def test_sync_all_returns_results(mock_settings, mock_init_db):
    """All syncs succeed — results contain their return dicts."""
    mock_oura = MagicMock(return_value={"sleep": 5, "readiness": 5})
    mock_garmin = MagicMock(return_value={"activities": 0, "sleep": 0})
    mock_strava = MagicMock(return_value={"activities": 1})
    mock_renpho = MagicMock(return_value={"weight": 2})

    with (
        patch("scripts.sync_all.sync_oura", mock_oura),
        patch("scripts.sync_all.sync_garmin", mock_garmin),
        patch("scripts.sync_all.sync_strava", mock_strava),
        patch("scripts.sync_all.sync_renpho", mock_renpho),
    ):
        from scripts.sync_all import sync_all

        results = sync_all()

    user_id = mock_settings.user_telegram_ids[0]
    assert user_id in results
    user_results = results[user_id]

    assert set(user_results.keys()) == {"oura", "garmin", "strava", "renpho"}
    assert user_results["oura"] == {"sleep": 5, "readiness": 5}
    assert user_results["garmin"] == {"activities": 0, "sleep": 0}
    assert user_results["strava"] == {"activities": 1}
    assert user_results["renpho"] == {"weight": 2}
