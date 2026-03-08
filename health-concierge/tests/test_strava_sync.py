"""Tests for Strava data sync."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.db import get_device_data, init_db
from src.sync.strava_sync import sync_strava


@pytest.fixture(autouse=True)
def setup_db(tmp_path):
    """Initialize a fresh test database for each test."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    yield


def _make_activity(
    activity_id=12345,
    activity_type="Run",
    name="Morning Run",
    moving_time_secs=2700,
    distance=5000.0,
    start_date=None,
    average_heartrate=150,
    max_heartrate=175,
    total_elevation_gain=50.0,
    calories=400.0,
    description="Easy run",
):
    """Create a mock Strava activity object."""
    activity = Mock()
    activity.id = activity_id
    activity.type = activity_type
    activity.name = name

    # moving_time: stravalib Duration supports float()
    mt = Mock()
    mt.__float__ = Mock(return_value=float(moving_time_secs))
    mt.__bool__ = Mock(return_value=True)
    activity.moving_time = mt

    # distance: stravalib Distance supports float()
    dist = Mock()
    dist.__float__ = Mock(return_value=distance)
    dist.__bool__ = Mock(return_value=True)
    activity.distance = dist

    # total_elevation_gain
    elev = Mock()
    elev.__float__ = Mock(return_value=total_elevation_gain)
    elev.__bool__ = Mock(return_value=True)
    activity.total_elevation_gain = elev

    activity.start_date = start_date or datetime(2026, 3, 6, 7, 0, tzinfo=timezone.utc)
    activity.average_heartrate = average_heartrate
    activity.max_heartrate = max_heartrate
    activity.calories = calories
    activity.description = description

    return activity


def _mock_token_response(refresh_token="original_refresh"):
    """Create a mock token response dict."""
    return {
        "access_token": "mock_access_token",
        "refresh_token": refresh_token,
    }


@patch("src.sync.strava_sync.settings")
@patch("src.sync.strava_sync.TOKENS_FILE")
@patch("src.sync.strava_sync.Client")
def test_sync_saves_activities(mock_client_cls, mock_tokens_file, mock_settings):
    """Test that sync fetches and saves Strava activities."""
    mock_tokens_file.exists.return_value = False
    mock_settings.strava_client_id = "12345"
    mock_settings.strava_client_secret = "secret"
    mock_settings.strava_refresh_token = "original_refresh"

    client = MagicMock()
    mock_client_cls.return_value = client
    client.refresh_access_token.return_value = _mock_token_response()

    activities = [
        _make_activity(activity_id=1, name="Morning Run"),
        _make_activity(activity_id=2, name="Evening Ride", activity_type="Ride"),
        _make_activity(activity_id=3, name="Swim", activity_type="Swim"),
    ]
    client.get_activities.return_value = iter(activities)

    result = sync_strava("user1")

    assert result == {"activities": 3}

    records = get_device_data("user1", source="strava", data_type="activity")
    assert len(records) == 3

    # Verify data content of one record
    names = {r["data"]["name"] for r in records}
    assert names == {"Morning Run", "Evening Ride", "Swim"}

    # Verify strava_id is stored
    strava_ids = {r["data"]["strava_id"] for r in records}
    assert strava_ids == {1, 2, 3}


@patch("src.sync.strava_sync.TOKENS_FILE")
@patch("src.sync.strava_sync.Client")
def test_sync_handles_token_refresh(mock_client_cls, mock_tokens_file):
    """Test that sync handles token refresh and saves new refresh token."""
    mock_tokens_file.exists.return_value = False

    client = MagicMock()
    mock_client_cls.return_value = client
    # Return a new refresh token
    client.refresh_access_token.return_value = _mock_token_response(
        refresh_token="new_refresh_token"
    )
    client.get_activities.return_value = iter([])

    with patch("src.sync.strava_sync.settings") as mock_settings:
        mock_settings.strava_client_id = "12345"
        mock_settings.strava_client_secret = "secret"
        mock_settings.strava_refresh_token = "original_refresh"

        result = sync_strava("user1")

    assert result == {"activities": 0}

    # Verify refresh_access_token was called
    client.refresh_access_token.assert_called_once()

    # Verify the new token was saved (write_text called on TOKENS_FILE)
    mock_tokens_file.parent.mkdir.assert_called_once()
    mock_tokens_file.write_text.assert_called_once()
    saved_data = json.loads(mock_tokens_file.write_text.call_args[0][0])
    assert saved_data["refresh_token"] == "new_refresh_token"


@patch("src.sync.strava_sync.settings")
@patch("src.sync.strava_sync.TOKENS_FILE")
@patch("src.sync.strava_sync.Client")
def test_sync_is_idempotent(mock_client_cls, mock_tokens_file, mock_settings):
    """Test that running sync twice doesn't create duplicates."""
    mock_tokens_file.exists.return_value = False
    mock_settings.strava_client_id = "12345"
    mock_settings.strava_client_secret = "secret"
    mock_settings.strava_refresh_token = "original_refresh"

    client = MagicMock()
    mock_client_cls.return_value = client
    client.refresh_access_token.return_value = _mock_token_response()

    activity = _make_activity(activity_id=42, name="Test Run")

    # First sync
    client.get_activities.return_value = iter([activity])
    result1 = sync_strava("user1")
    assert result1 == {"activities": 1}

    # Second sync with same activity
    client.get_activities.return_value = iter([activity])
    result2 = sync_strava("user1")
    assert result2 == {"activities": 0}

    # Only one record in DB
    records = get_device_data("user1", source="strava", data_type="activity")
    assert len(records) == 1


@patch("src.sync.strava_sync.settings")
@patch("src.sync.strava_sync.TOKENS_FILE")
@patch("src.sync.strava_sync.Client")
def test_sync_handles_no_new_activities(mock_client_cls, mock_tokens_file, mock_settings):
    """Test that sync handles empty activity list gracefully."""
    mock_tokens_file.exists.return_value = False
    mock_settings.strava_client_id = "12345"
    mock_settings.strava_client_secret = "secret"
    mock_settings.strava_refresh_token = "original_refresh"

    client = MagicMock()
    mock_client_cls.return_value = client
    client.refresh_access_token.return_value = _mock_token_response()
    client.get_activities.return_value = iter([])

    result = sync_strava("user1")

    assert result == {"activities": 0}
    records = get_device_data("user1", source="strava", data_type="activity")
    assert len(records) == 0


@patch("src.sync.strava_sync.settings")
@patch("src.sync.strava_sync.TOKENS_FILE")
@patch("src.sync.strava_sync.Client")
def test_sync_handles_api_error(mock_client_cls, mock_tokens_file, mock_settings):
    """Test that sync propagates API errors from get_activities."""
    mock_tokens_file.exists.return_value = False
    mock_settings.strava_client_id = "12345"
    mock_settings.strava_client_secret = "secret"
    mock_settings.strava_refresh_token = "original_refresh"

    client = MagicMock()
    mock_client_cls.return_value = client
    client.refresh_access_token.return_value = _mock_token_response()
    client.get_activities.side_effect = Exception("Strava API rate limit exceeded")

    with pytest.raises(Exception, match="rate limit"):
        sync_strava("user1")
