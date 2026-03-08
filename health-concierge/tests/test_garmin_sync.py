"""Tests for Garmin Connect data sync."""

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.db import get_device_data, init_db, save_device_data


# --- Mock Garmin API response factories ---

def _activities_response() -> list[dict]:
    return [
        {
            "activityId": 12345,
            "activityName": "Morning Run",
            "activityType": {"typeKey": "running"},
            "startTimeLocal": "2026-03-06 07:30:00",
            "duration": 1800.0,
            "distance": 5000.0,
            "averageHR": 145,
            "maxHR": 172,
            "calories": 350,
            "averageSpeed": 2.78,
        },
        {
            "activityId": 12346,
            "activityName": "Evening Walk",
            "activityType": {"typeKey": "walking"},
            "startTimeLocal": "2026-03-06 18:00:00",
            "duration": 2400.0,
            "distance": 3000.0,
            "averageHR": 95,
            "maxHR": 110,
            "calories": 150,
            "averageSpeed": 1.25,
        },
    ]


def _sleep_response() -> dict:
    return {
        "dailySleepDTO": {
            "sleepStartTimestampLocal": 1741212000000,
            "sleepEndTimestampLocal": 1741240800000,
            "sleepTimeInSeconds": 28800,
            "deepSleepSeconds": 5400,
            "lightSleepSeconds": 14400,
            "remSleepSeconds": 7200,
            "awakeSleepSeconds": 1800,
        }
    }


def _stress_response() -> dict:
    return {
        "overallStressLevel": 35,
        "maxStressLevel": 72,
        "restStressDuration": 28800,
        "lowStressDuration": 18000,
        "mediumStressDuration": 7200,
        "highStressDuration": 1800,
        "bodyBatteryHighestValue": 95,
        "bodyBatteryLowestValue": 25,
    }


def _steps_response() -> list[dict]:
    return [
        {"steps": 5000, "primaryActivityLevel": {"distance": 3500}},
        {"steps": 3500, "primaryActivityLevel": {"distance": 2500}},
    ]


def _heart_rate_response() -> dict:
    return {
        "restingHeartRate": 58,
        "minHeartRate": 48,
        "maxHeartRate": 165,
    }


def _make_mock_client(
    activities=None,
    sleep=None,
    stress=None,
    steps=None,
    heart_rate=None,
) -> MagicMock:
    """Create a mock Garmin client with configured responses."""
    client = MagicMock()
    client.get_activities_by_date.return_value = activities if activities is not None else []
    client.get_sleep_data.return_value = sleep if sleep is not None else {}
    client.get_stress_data.return_value = stress if stress is not None else {}
    client.get_steps_data.return_value = steps if steps is not None else []
    client.get_heart_rates.return_value = heart_rate if heart_rate is not None else {}
    client.garth = MagicMock()
    return client


# --- Tests ---

@patch("src.sync.garmin_sync._get_sync_dates", return_value=["2026-03-06"])
@patch("src.sync.garmin_sync._get_garmin_client")
def test_sync_saves_activities(mock_get_client, mock_dates, tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    mock_get_client.return_value = _make_mock_client(activities=_activities_response())

    from src.sync.garmin_sync import sync_garmin
    result = sync_garmin("user1")

    assert result["activities"] == 2
    records = get_device_data("user1", source="garmin", data_type="activity")
    assert len(records) == 2
    # Check one activity's data
    activity_types = {r["data"]["activity_type"] for r in records}
    assert "running" in activity_types
    assert "walking" in activity_types


@patch("src.sync.garmin_sync._get_sync_dates", return_value=["2026-03-06"])
@patch("src.sync.garmin_sync._get_garmin_client")
def test_sync_saves_sleep_data(mock_get_client, mock_dates, tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    mock_get_client.return_value = _make_mock_client(sleep=_sleep_response())

    from src.sync.garmin_sync import sync_garmin
    result = sync_garmin("user1")

    assert result["sleep"] == 1
    records = get_device_data("user1", source="garmin", data_type="sleep")
    assert len(records) == 1
    assert records[0]["data"]["duration_seconds"] == 28800
    assert records[0]["data"]["deep_seconds"] == 5400


@patch("src.sync.garmin_sync._get_sync_dates", return_value=["2026-03-06"])
@patch("src.sync.garmin_sync._get_garmin_client")
def test_sync_saves_stress_data(mock_get_client, mock_dates, tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    mock_get_client.return_value = _make_mock_client(stress=_stress_response())

    from src.sync.garmin_sync import sync_garmin
    result = sync_garmin("user1")

    assert result["stress"] == 1
    records = get_device_data("user1", source="garmin", data_type="stress")
    assert len(records) == 1
    assert records[0]["data"]["avg_stress"] == 35
    assert records[0]["data"]["body_battery_high"] == 95


@patch("src.sync.garmin_sync._get_sync_dates", return_value=["2026-03-06"])
@patch("src.sync.garmin_sync._get_garmin_client")
def test_sync_saves_steps(mock_get_client, mock_dates, tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    mock_get_client.return_value = _make_mock_client(steps=_steps_response())

    from src.sync.garmin_sync import sync_garmin
    result = sync_garmin("user1")

    assert result["steps"] == 1
    records = get_device_data("user1", source="garmin", data_type="steps")
    assert len(records) == 1
    assert records[0]["data"]["total_steps"] == 8500


@patch("src.sync.garmin_sync._get_sync_dates", return_value=["2026-03-06"])
@patch("src.sync.garmin_sync._get_garmin_client")
def test_sync_is_idempotent(mock_get_client, mock_dates, tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    mock_get_client.return_value = _make_mock_client(
        activities=_activities_response(),
        sleep=_sleep_response(),
        stress=_stress_response(),
        steps=_steps_response(),
        heart_rate=_heart_rate_response(),
    )

    from src.sync.garmin_sync import sync_garmin

    # First sync
    result1 = sync_garmin("user1")
    assert result1["activities"] == 2
    assert result1["sleep"] == 1
    assert result1["stress"] == 1
    assert result1["steps"] == 1
    assert result1["heart_rate"] == 1

    # Second sync — no duplicates
    result2 = sync_garmin("user1")
    assert result2["activities"] == 0
    assert result2["sleep"] == 0
    assert result2["stress"] == 0
    assert result2["steps"] == 0
    assert result2["heart_rate"] == 0

    # Verify counts in DB
    assert len(get_device_data("user1", source="garmin", data_type="activity")) == 2
    assert len(get_device_data("user1", source="garmin", data_type="sleep")) == 1
    assert len(get_device_data("user1", source="garmin", data_type="stress")) == 1


@patch("src.sync.garmin_sync._get_garmin_client")
def test_sync_handles_auth_failure(mock_get_client, tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    from garminconnect import GarminConnectAuthenticationError
    mock_get_client.side_effect = GarminConnectAuthenticationError("Invalid credentials")

    from src.sync.garmin_sync import sync_garmin
    result = sync_garmin("user1")

    assert result["activities"] == 0
    assert result["sleep"] == 0
    assert result["stress"] == 0
    assert result["steps"] == 0
    assert result["heart_rate"] == 0


@patch("src.sync.garmin_sync.Garmin")
def test_sync_caches_session(mock_garmin_cls, tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))

    mock_client = MagicMock()
    mock_client.garth = MagicMock()
    mock_garmin_cls.return_value = mock_client

    from src.sync.garmin_sync import _get_garmin_client

    # Patch TOKEN_STORE to use tmp dir so no real files
    with patch("src.sync.garmin_sync.TOKEN_STORE", str(tmp_db_path.parent / ".garmin_tokens")):
        with patch("src.sync.garmin_sync.Path") as mock_path_cls:
            mock_token_path = MagicMock()
            mock_token_path.exists.return_value = False
            mock_path_cls.return_value = mock_token_path

            _get_garmin_client()

    # Should have called login() without tokenstore (fresh login)
    mock_client.login.assert_called_once_with()
    # Should save tokens
    mock_client.garth.dump.assert_called_once()


@patch("src.sync.garmin_sync._get_sync_dates", return_value=["2026-03-06"])
@patch("src.sync.garmin_sync._get_garmin_client")
def test_sync_handles_no_activities(mock_get_client, mock_dates, tmp_db_path: Path) -> None:
    init_db(str(tmp_db_path))
    mock_get_client.return_value = _make_mock_client(
        activities=[],
        sleep={},
        stress={},
        steps=[],
        heart_rate={},
    )

    from src.sync.garmin_sync import sync_garmin
    result = sync_garmin("user1")

    assert result["activities"] == 0
    assert result["sleep"] == 0
    assert result["stress"] == 0
    assert result["steps"] == 0
    assert result["heart_rate"] == 0

    records = get_device_data("user1", source="garmin")
    assert len(records) == 0
