"""Garmin Connect data sync.

Fetches activity, heart rate, sleep, stress, and steps data
via the garminconnect library (unofficial API, session-cached).
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from garminconnect import Garmin, GarminConnectAuthenticationError

from config import settings
from src.db import get_connection, get_device_data, save_device_data

logger = logging.getLogger(__name__)

# Token store directory for garth session persistence
TOKEN_STORE = str(Path(settings.db_path).parent / ".garmin_tokens")

# Auth failure backoff: skip sync for this many hours after a failed login
_AUTH_BACKOFF_HOURS = 6
_auth_fail_path = Path(settings.db_path).parent / ".garmin_auth_failed"


def _should_skip_auth() -> bool:
    """Check if we should skip Garmin auth due to recent failure backoff."""
    if not _auth_fail_path.exists():
        return False
    try:
        fail_time = datetime.fromisoformat(_auth_fail_path.read_text().strip())
        if datetime.now(timezone.utc) - fail_time < timedelta(hours=_AUTH_BACKOFF_HOURS):
            return True
        # Backoff expired, clear the marker
        _auth_fail_path.unlink(missing_ok=True)
    except (ValueError, OSError):
        _auth_fail_path.unlink(missing_ok=True)
    return False


def _mark_auth_failed() -> None:
    """Record an auth failure timestamp for backoff."""
    _auth_fail_path.parent.mkdir(parents=True, exist_ok=True)
    _auth_fail_path.write_text(datetime.now(timezone.utc).isoformat())


def _get_garmin_client() -> Garmin:
    """Create and authenticate a Garmin client with session caching.

    Tries to load saved tokens from TOKEN_STORE first.
    If no tokens or tokens are expired, logs in with credentials and saves tokens.
    """
    client = Garmin(settings.garmin_email, settings.garmin_password)
    token_path = Path(TOKEN_STORE)

    if token_path.exists():
        try:
            client.login(tokenstore=TOKEN_STORE)
            # Auth succeeded — clear any backoff marker
            _auth_fail_path.unlink(missing_ok=True)
            return client
        except GarminConnectAuthenticationError:
            logger.warning("Saved Garmin tokens expired, re-authenticating")

    # Fresh login with credentials
    client.login()
    token_path.mkdir(parents=True, exist_ok=True)
    client.garth.dump(TOKEN_STORE)
    _auth_fail_path.unlink(missing_ok=True)
    return client


def _get_sync_dates(user_id: str) -> list[str]:
    """Return list of date strings (YYYY-MM-DD) to sync.

    Checks the latest recorded_at from garmin device data.
    If none found, defaults to today and yesterday.
    """
    records = get_device_data(user_id, source="garmin")
    if records:
        latest = records[0]["recorded_at"][:10]
        latest_date = datetime.strptime(latest, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        latest_date = datetime.now(timezone.utc) - timedelta(days=1)

    today = datetime.now(timezone.utc)
    dates = []
    d = latest_date
    while d.date() <= today.date():
        dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    return dates


def _record_exists(user_id: str, source: str, data_type: str, recorded_at: str) -> bool:
    """Check if a device_data record already exists for the given key."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM device_data WHERE user_id = ? AND source = ? "
            "AND data_type = ? AND recorded_at = ?",
            (user_id, source, data_type, recorded_at),
        ).fetchone()
    return row is not None


def _sync_activities(client: Garmin, user_id: str, dates: list[str]) -> int:
    """Sync activity data. Uses get_activities_by_date for the date range."""
    if not dates:
        return 0

    try:
        activities = client.get_activities_by_date(dates[0], dates[-1])
    except Exception as exc:
        logger.error("Garmin activities fetch error: %s", exc)
        return 0

    if not activities:
        return 0

    count = 0
    for activity in activities:
        start_time = activity.get("startTimeLocal", "")
        if not start_time:
            continue

        day = start_time[:10]
        recorded_at = f"{day}T00:00:00+00:00"

        # Use activity ID for uniqueness -- multiple activities per day possible
        activity_id = activity.get("activityId", "")
        unique_recorded_at = f"{day}T00:00:00+00:00#{activity_id}" if activity_id else recorded_at

        if _record_exists(user_id, "garmin", "activity", unique_recorded_at):
            continue

        data = {
            "activity_id": activity_id,
            "activity_type": activity.get("activityType", {}).get("typeKey", "unknown"),
            "activity_name": activity.get("activityName", ""),
            "duration_seconds": activity.get("duration"),
            "distance_meters": activity.get("distance"),
            "avg_heart_rate": activity.get("averageHR"),
            "max_heart_rate": activity.get("maxHR"),
            "calories": activity.get("calories"),
            "avg_speed": activity.get("averageSpeed"),
            "start_time": start_time,
        }

        save_device_data(
            user_id=user_id,
            source="garmin",
            data_type="activity",
            data=data,
            recorded_at=unique_recorded_at,
        )
        count += 1

    return count


def _sync_daily_data(
    client: Garmin,
    user_id: str,
    dates: list[str],
    data_type: str,
    fetch_fn,
    extract_fn,
) -> int:
    """Sync a daily data type (sleep, stress, steps, heart_rate)."""
    count = 0
    for day in dates:
        recorded_at = f"{day}T00:00:00+00:00"

        if _record_exists(user_id, "garmin", data_type, recorded_at):
            continue

        try:
            raw = fetch_fn(day)
        except Exception as exc:
            logger.error("Garmin %s fetch error for %s: %s", data_type, day, exc)
            continue

        if not raw:
            continue

        data = extract_fn(raw)
        if not data:
            continue

        save_device_data(
            user_id=user_id,
            source="garmin",
            data_type=data_type,
            data=data,
            recorded_at=recorded_at,
        )
        count += 1

    return count


def _extract_sleep(raw: dict) -> dict | None:
    """Extract relevant sleep fields from Garmin sleep data."""
    daily = raw.get("dailySleepDTO", raw)
    if not daily:
        return None
    return {
        "sleep_start": daily.get("sleepStartTimestampLocal"),
        "sleep_end": daily.get("sleepEndTimestampLocal"),
        "duration_seconds": daily.get("sleepTimeInSeconds"),
        "deep_seconds": daily.get("deepSleepSeconds"),
        "light_seconds": daily.get("lightSleepSeconds"),
        "rem_seconds": daily.get("remSleepSeconds"),
        "awake_seconds": daily.get("awakeSleepSeconds"),
    }


def _extract_stress(raw: dict) -> dict | None:
    """Extract relevant stress fields from Garmin stress data."""
    return {
        "avg_stress": raw.get("overallStressLevel"),
        "max_stress": raw.get("maxStressLevel"),
        "rest_stress": raw.get("restStressDuration"),
        "low_stress": raw.get("lowStressDuration"),
        "medium_stress": raw.get("mediumStressDuration"),
        "high_stress": raw.get("highStressDuration"),
        "body_battery_high": raw.get("bodyBatteryHighestValue"),
        "body_battery_low": raw.get("bodyBatteryLowestValue"),
    }


def _extract_steps(raw) -> dict | None:
    """Extract relevant steps fields from Garmin steps data."""
    if isinstance(raw, list):
        if not raw:
            return None
        total_steps = sum(item.get("steps", 0) for item in raw)
        total_distance = sum(
            item.get("primaryActivityLevel", {}).get("distance", 0)
            if isinstance(item.get("primaryActivityLevel"), dict)
            else 0
            for item in raw
        )
        return {
            "total_steps": total_steps,
            "total_distance": total_distance,
        }
    return None


def _extract_heart_rate(raw: dict) -> dict | None:
    """Extract relevant heart rate fields from Garmin HR data."""
    return {
        "resting_hr": raw.get("restingHeartRate"),
        "min_hr": raw.get("minHeartRate"),
        "max_hr": raw.get("maxHeartRate"),
    }


def sync_garmin(user_id: str) -> dict:
    """Sync Garmin Connect data for a user.

    Pulls activities, sleep, stress, steps, and heart rate data.
    Only inserts new records (idempotent by user_id + source + data_type + recorded_at).

    Returns a summary dict with counts of records synced per data type.
    """
    result = {
        "activities": 0,
        "sleep": 0,
        "stress": 0,
        "steps": 0,
        "heart_rate": 0,
    }

    if _should_skip_auth():
        logger.info("Skipping Garmin sync — auth backoff active (retry in %dh)", _AUTH_BACKOFF_HOURS)
        return result

    try:
        client = _get_garmin_client()
    except Exception as exc:
        logger.error("Garmin authentication failed: %s", exc)
        _mark_auth_failed()
        return result

    dates = _get_sync_dates(user_id)
    logger.info("Syncing Garmin data for user %s, dates: %s", user_id, dates)

    result["activities"] = _sync_activities(client, user_id, dates)

    result["sleep"] = _sync_daily_data(
        client, user_id, dates, "sleep",
        client.get_sleep_data, _extract_sleep,
    )

    result["stress"] = _sync_daily_data(
        client, user_id, dates, "stress",
        client.get_stress_data, _extract_stress,
    )

    result["steps"] = _sync_daily_data(
        client, user_id, dates, "steps",
        client.get_steps_data, _extract_steps,
    )

    result["heart_rate"] = _sync_daily_data(
        client, user_id, dates, "heart_rate",
        client.get_heart_rates, _extract_heart_rate,
    )

    logger.info("Garmin sync complete for user %s: %s", user_id, result)
    return result
