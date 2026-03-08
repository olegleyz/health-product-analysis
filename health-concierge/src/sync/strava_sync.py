"""Strava data sync.

Fetches activity data from Strava using stravalib with OAuth2
refresh token flow.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from stravalib import Client

from config import settings
from src.db import get_connection, get_device_data, save_device_data

logger = logging.getLogger(__name__)

TOKENS_FILE = Path("data/.strava_tokens")


def _load_refresh_token() -> str:
    """Load refresh token from file if it exists, otherwise from config."""
    if TOKENS_FILE.exists():
        data = json.loads(TOKENS_FILE.read_text())
        return data.get("refresh_token", settings.strava_refresh_token)
    return settings.strava_refresh_token


def _save_refresh_token(refresh_token: str) -> None:
    """Save refresh token to file for persistence across runs."""
    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_FILE.write_text(json.dumps({"refresh_token": refresh_token}))


def _get_authenticated_client() -> Client:
    """Create and authenticate a stravalib Client using OAuth2 refresh flow.

    Returns an authenticated Client ready to make API calls.
    """
    client = Client()
    refresh_token = _load_refresh_token()

    token_response = client.refresh_access_token(
        client_id=int(settings.strava_client_id),
        client_secret=settings.strava_client_secret,
        refresh_token=refresh_token,
    )

    client.access_token = token_response["access_token"]

    # Save new refresh token if it changed
    new_refresh = token_response.get("refresh_token", refresh_token)
    if new_refresh != refresh_token:
        _save_refresh_token(new_refresh)
        logger.info("Strava refresh token updated")

    return client


def _get_last_sync_date(user_id: str) -> datetime:
    """Return the earliest date to fetch activities from.

    Looks at the latest recorded_at for strava activity data.
    If none found, defaults to 7 days ago.
    """
    records = get_device_data(user_id, source="strava", data_type="activity")
    if records:
        latest = records[0]["recorded_at"]
        return datetime.fromisoformat(latest)

    return datetime.now(timezone.utc) - timedelta(days=7)


def _record_exists(user_id: str, strava_id: int) -> bool:
    """Check if a strava activity already exists by its strava ID."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT data FROM device_data WHERE user_id = ? AND source = 'strava' "
            "AND data_type = 'activity'",
            (user_id,),
        ).fetchall()
    for row in rows:
        data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        if data.get("strava_id") == strava_id:
            return True
    return False


def sync_strava(user_id: str) -> dict:
    """Sync Strava activity data for a user.

    Authenticates via OAuth2 refresh token, fetches new activities,
    and stores them in device_data. Idempotent by strava activity ID.

    Returns a summary dict: {"activities": <count>}.
    """
    client = _get_authenticated_client()
    after = _get_last_sync_date(user_id)
    logger.info(
        "Syncing Strava data for user %s since %s", user_id, after.isoformat()
    )

    activities = client.get_activities(after=after)
    count = 0

    for activity in activities:
        activity_id = activity.id
        if _record_exists(user_id, activity_id):
            continue

        recorded_at = (
            activity.start_date.isoformat()
            if activity.start_date
            else datetime.now(timezone.utc).isoformat()
        )

        data = {
            "strava_id": activity_id,
            "type": str(activity.type) if activity.type else None,
            "name": activity.name,
            "moving_time_seconds": (
                float(activity.moving_time) if activity.moving_time else None
            ),
            "distance_meters": (
                float(activity.distance) if activity.distance else None
            ),
            "total_elevation_gain_meters": (
                float(activity.total_elevation_gain)
                if activity.total_elevation_gain
                else None
            ),
            "average_heartrate": activity.average_heartrate,
            "max_heartrate": activity.max_heartrate,
            "calories": activity.calories,
            "description": activity.description,
        }

        save_device_data(
            user_id=user_id,
            source="strava",
            data_type="activity",
            data=data,
            recorded_at=recorded_at,
        )
        count += 1

    logger.info("Strava: synced %d activities for user %s", count, user_id)
    return {"activities": count}
