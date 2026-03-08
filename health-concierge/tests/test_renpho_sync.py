"""Tests for Renpho body composition sync."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.db import get_device_data, init_db
from src.sync.renpho_sync import sync_renpho

MOCK_RENPHO_LOGIN_RESPONSE = {
    "terminal_user_session_key": "fake-session-token-123",
}

MOCK_RENPHO_MEASUREMENTS = {
    "last_ary": [
        {
            "weight": 82.5,
            "bodyfat": 18.2,
            "muscle": 35.0,
            "bmi": 24.1,
            "water": 55.0,
            "bone": 3.2,
            "time_stamp": 1709856000,  # 2024-03-08T00:00:00Z
        },
        {
            "weight": 82.0,
            "bodyfat": 18.0,
            "muscle": 35.2,
            "bmi": 24.0,
            "water": 55.5,
            "bone": 3.2,
            "time_stamp": 1709769600,  # 2024-03-07T00:00:00Z
        },
        {
            "weight": 83.1,
            "bodyfat": 18.5,
            "muscle": 34.8,
            "bmi": 24.3,
            "water": 54.8,
            "bone": 3.1,
            "time_stamp": 1709683200,  # 2024-03-06T00:00:00Z
        },
    ]
}

MOCK_GARMIN_BODY_COMP = {
    "dateWeightList": [
        {
            "weight": 82500,  # grams
            "bodyFat": 18.2,
            "muscleMass": 35000,
            "bmi": 24.1,
            "calendarDate": "2024-03-08",
        },
    ]
}


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    """Initialize a fresh test database for each test."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)


def _mock_renpho_post(url, **kwargs):
    """Mock requests.post for Renpho login."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = MOCK_RENPHO_LOGIN_RESPONSE
    resp.raise_for_status.return_value = None
    return resp


def _mock_renpho_get(url, **kwargs):
    """Mock requests.get for Renpho measurements."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = MOCK_RENPHO_MEASUREMENTS
    resp.raise_for_status.return_value = None
    return resp


class TestSyncSavesWeightData:
    """test_sync_saves_weight_data — mock Renpho API success."""

    @patch("src.sync.renpho_sync.requests.get", side_effect=_mock_renpho_get)
    @patch("src.sync.renpho_sync.requests.post", side_effect=_mock_renpho_post)
    @patch("src.sync.renpho_sync.settings")
    def test_sync_saves_weight_data(self, mock_settings, mock_post, mock_get):
        mock_settings.renpho_email = "test@example.com"
        mock_settings.renpho_password = "password123"

        result = sync_renpho("user1")

        assert result["weight"] == 3
        records = get_device_data("user1", source="renpho", data_type="weight")
        assert len(records) == 3
        # Verify source is renpho
        assert all(r["source"] == "renpho" for r in records)
        assert all(r["data_type"] == "weight" for r in records)


class TestSyncSavesBodyComposition:
    """test_sync_saves_body_composition — verify full body comp fields saved."""

    @patch("src.sync.renpho_sync.requests.get", side_effect=_mock_renpho_get)
    @patch("src.sync.renpho_sync.requests.post", side_effect=_mock_renpho_post)
    @patch("src.sync.renpho_sync.settings")
    def test_sync_saves_body_composition(self, mock_settings, mock_post, mock_get):
        mock_settings.renpho_email = "test@example.com"
        mock_settings.renpho_password = "password123"

        sync_renpho("user1")

        records = get_device_data("user1", source="renpho", data_type="weight")
        assert len(records) == 3

        # Check the first measurement (most recent by recorded_at DESC)
        data = records[0]["data"]
        assert data["weight_kg"] == 82.5
        assert data["body_fat_pct"] == 18.2
        assert data["muscle_mass_kg"] == 35.0
        assert data["bmi"] == 24.1
        assert data["water_pct"] == 55.0
        assert data["bone_mass_kg"] == 3.2


class TestSyncIsIdempotent:
    """test_sync_is_idempotent — run twice, no dupes."""

    @patch("src.sync.renpho_sync.requests.get", side_effect=_mock_renpho_get)
    @patch("src.sync.renpho_sync.requests.post", side_effect=_mock_renpho_post)
    @patch("src.sync.renpho_sync.settings")
    def test_sync_is_idempotent(self, mock_settings, mock_post, mock_get):
        mock_settings.renpho_email = "test@example.com"
        mock_settings.renpho_password = "password123"

        result1 = sync_renpho("user1")
        assert result1["weight"] == 3

        result2 = sync_renpho("user1")
        assert result2["weight"] == 0

        records = get_device_data("user1", source="renpho", data_type="weight")
        assert len(records) == 3


class TestSyncFallbackToGarmin:
    """test_sync_fallback_to_garmin — mock Renpho failure, Garmin success."""

    @patch("src.sync.renpho_sync.settings")
    def test_sync_fallback_to_garmin(self, mock_settings):
        mock_settings.renpho_email = "test@example.com"
        mock_settings.renpho_password = "password123"
        mock_settings.garmin_email = "garmin@example.com"
        mock_settings.garmin_password = "garminpass"

        # Build a mock garminconnect module with a mock Garmin class
        mock_garmin_instance = MagicMock()
        mock_garmin_instance.get_body_composition.return_value = MOCK_GARMIN_BODY_COMP
        mock_garmin_cls = MagicMock(return_value=mock_garmin_instance)
        mock_garminconnect = MagicMock(Garmin=mock_garmin_cls)

        # Renpho login fails, fallback to Garmin via sys.modules mock
        with patch("src.sync.renpho_sync.requests.post", side_effect=Exception("connection refused")):
            with patch.dict("sys.modules", {"garminconnect": mock_garminconnect}):
                result = sync_renpho("user1")

        assert result["weight"] == 1
        records = get_device_data("user1", source="garmin", data_type="weight")
        assert len(records) == 1

        data = records[0]["data"]
        assert data["weight_kg"] == 82.5
        assert data["body_fat_pct"] == 18.2
        assert data["bmi"] == 24.1


class TestSyncHandlesTotalFailure:
    """test_sync_handles_total_failure — both sources fail, no crash, returns error info."""

    @patch("src.sync.renpho_sync.settings")
    def test_sync_handles_total_failure(self, mock_settings):
        mock_settings.renpho_email = "test@example.com"
        mock_settings.renpho_password = "password123"
        mock_settings.garmin_email = "garmin@example.com"
        mock_settings.garmin_password = "garminpass"

        with patch("src.sync.renpho_sync.requests.post", side_effect=Exception("renpho down")):
            mock_garmin_cls = MagicMock()
            mock_garmin_cls.return_value.login.side_effect = Exception("garmin down")

            with patch.dict("sys.modules", {"garminconnect": MagicMock(Garmin=mock_garmin_cls)}):
                result = sync_renpho("user1")

        assert result["weight"] == 0
        assert "error" in result
        records = get_device_data("user1", data_type="weight")
        assert len(records) == 0
