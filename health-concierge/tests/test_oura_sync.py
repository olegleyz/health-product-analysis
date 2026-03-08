"""Tests for Oura Ring data sync."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.db import get_device_data, init_db, save_device_data


# --- Mock API response factories ---

def _sleep_response(day: str = "2026-03-06") -> dict:
    return {
        "data": [
            {
                "day": day,
                "score": 85,
                "total_sleep_duration": 28800,
                "efficiency": 92,
                "latency": 600,
                "deep_sleep_duration": 5400,
                "rem_sleep_duration": 7200,
                "light_sleep_duration": 16200,
                "time_in_bed": 31200,
                "bedtime_start": f"{day}T23:00:00+02:00",
                "bedtime_end": f"{day}T06:40:00+02:00",
                "contributors": {
                    "deep_sleep": 80,
                    "efficiency": 90,
                    "latency": 95,
                    "rem_sleep": 85,
                    "restfulness": 78,
                    "timing": 88,
                    "total_sleep": 82,
                },
            }
        ]
    }


def _readiness_response(day: str = "2026-03-06") -> dict:
    return {
        "data": [
            {
                "day": day,
                "score": 82,
                "contributors": {
                    "activity_balance": 80,
                    "body_temperature": 90,
                    "hrv_balance": 75,
                    "previous_day_activity": 85,
                    "previous_night": 88,
                    "recovery_index": 78,
                    "resting_heart_rate": 82,
                    "sleep_balance": 79,
                },
            }
        ]
    }


def _activity_response(day: str = "2026-03-06") -> dict:
    return {
        "data": [
            {
                "day": day,
                "steps": 8500,
                "active_calories": 450,
                "total_calories": 2200,
                "sedentary_time": 28800,
            }
        ]
    }


def _heartrate_response() -> dict:
    return {
        "data": [
            {
                "timestamp": "2026-03-06T08:00:00+00:00",
                "bpm": 62,
                "source": "rest",
            }
        ]
    }


def _empty_response() -> dict:
    return {"data": []}


def _mock_get_side_effect(url: str, **kwargs) -> MagicMock:
    """Return mock responses based on URL endpoint."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    if "daily_sleep" in url:
        mock_resp.json.return_value = _sleep_response()
    elif "daily_readiness" in url:
        mock_resp.json.return_value = _readiness_response()
    elif "daily_activity" in url:
        mock_resp.json.return_value = _activity_response()
    elif "heartrate" in url:
        mock_resp.json.return_value = _heartrate_response()
    else:
        mock_resp.json.return_value = _empty_response()

    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _mock_get_empty(url: str, **kwargs) -> MagicMock:
    """Return empty responses for all endpoints."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _empty_response()
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# --- Tests ---

@patch("src.sync.oura_sync.settings")
@patch("src.sync.oura_sync.requests.get", side_effect=_mock_get_side_effect)
def test_sync_saves_sleep_data(mock_get, mock_settings, tmp_db_path: Path) -> None:
    mock_settings.oura_access_token = "test-token"
    init_db(str(tmp_db_path))

    from src.sync.oura_sync import sync_oura
    result = sync_oura("user1")

    assert result["sleep"] == 1
    records = get_device_data("user1", source="oura", data_type="sleep")
    assert len(records) == 1
    assert records[0]["data"]["score"] == 85
    assert records[0]["data"]["total_sleep_duration"] == 28800
    assert records[0]["recorded_at"] == "2026-03-06T00:00:00+00:00"


@patch("src.sync.oura_sync.settings")
@patch("src.sync.oura_sync.requests.get", side_effect=_mock_get_side_effect)
def test_sync_saves_readiness_data(mock_get, mock_settings, tmp_db_path: Path) -> None:
    mock_settings.oura_access_token = "test-token"
    init_db(str(tmp_db_path))

    from src.sync.oura_sync import sync_oura
    result = sync_oura("user1")

    assert result["readiness"] == 1
    records = get_device_data("user1", source="oura", data_type="readiness")
    assert len(records) == 1
    assert records[0]["data"]["score"] == 82
    assert "contributors" in records[0]["data"]


@patch("src.sync.oura_sync.settings")
@patch("src.sync.oura_sync.requests.get", side_effect=_mock_get_side_effect)
def test_sync_saves_activity_data(mock_get, mock_settings, tmp_db_path: Path) -> None:
    mock_settings.oura_access_token = "test-token"
    init_db(str(tmp_db_path))

    from src.sync.oura_sync import sync_oura
    result = sync_oura("user1")

    assert result["activity"] == 1
    records = get_device_data("user1", source="oura", data_type="activity")
    assert len(records) == 1
    assert records[0]["data"]["steps"] == 8500
    assert records[0]["data"]["active_calories"] == 450


@patch("src.sync.oura_sync.settings")
@patch("src.sync.oura_sync.requests.get", side_effect=_mock_get_side_effect)
def test_sync_is_idempotent(mock_get, mock_settings, tmp_db_path: Path) -> None:
    mock_settings.oura_access_token = "test-token"
    init_db(str(tmp_db_path))

    from src.sync.oura_sync import sync_oura

    # First sync
    result1 = sync_oura("user1")
    assert result1["sleep"] == 1
    assert result1["readiness"] == 1
    assert result1["activity"] == 1

    # Second sync with same data — should not create duplicates
    result2 = sync_oura("user1")
    assert result2["sleep"] == 0
    assert result2["readiness"] == 0
    assert result2["activity"] == 0

    # Verify no duplicates in DB
    sleep_records = get_device_data("user1", source="oura", data_type="sleep")
    assert len(sleep_records) == 1
    readiness_records = get_device_data("user1", source="oura", data_type="readiness")
    assert len(readiness_records) == 1


@patch("src.sync.oura_sync.settings")
@patch("src.sync.oura_sync.requests.get")
def test_sync_handles_api_error(mock_get, mock_settings, tmp_db_path: Path) -> None:
    mock_settings.oura_access_token = "test-token"
    init_db(str(tmp_db_path))

    import requests as req
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = req.HTTPError("500 Server Error")
    mock_get.return_value = mock_resp

    from src.sync.oura_sync import sync_oura
    result = sync_oura("user1")

    # Should not crash, returns zeros
    assert result["sleep"] == 0
    assert result["readiness"] == 0
    assert result["activity"] == 0
    assert result["heart_rate"] == 0


@patch("src.sync.oura_sync.settings")
@patch("src.sync.oura_sync.requests.get", side_effect=_mock_get_empty)
def test_sync_handles_empty_response(mock_get, mock_settings, tmp_db_path: Path) -> None:
    mock_settings.oura_access_token = "test-token"
    init_db(str(tmp_db_path))

    from src.sync.oura_sync import sync_oura
    result = sync_oura("user1")

    assert result["sleep"] == 0
    assert result["readiness"] == 0
    assert result["activity"] == 0
    assert result["heart_rate"] == 0

    records = get_device_data("user1", source="oura")
    assert len(records) == 0


@patch("src.sync.oura_sync.settings")
@patch("src.sync.oura_sync.requests.get", side_effect=_mock_get_side_effect)
def test_sync_uses_last_sync_date(mock_get, mock_settings, tmp_db_path: Path) -> None:
    mock_settings.oura_access_token = "test-token"
    init_db(str(tmp_db_path))

    # Insert existing data with a known date
    save_device_data(
        user_id="user1",
        source="oura",
        data_type="sleep",
        data={"score": 80},
        recorded_at="2026-03-04T00:00:00+00:00",
    )

    from src.sync.oura_sync import sync_oura
    sync_oura("user1")

    # Verify all API calls used 2026-03-04 as start_date (the latest recorded_at date)
    for call in mock_get.call_args_list:
        params = call.kwargs.get("params", {})
        assert params.get("start_date") == "2026-03-04", (
            f"Expected start_date=2026-03-04, got {params.get('start_date')}"
        )
