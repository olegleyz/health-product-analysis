"""Oura Ring data sync.

Fetches sleep, readiness, and activity data from the Oura API v2
using a personal access token.
"""

import logging
from datetime import datetime, timedelta, timezone

import requests

from config import settings
from src.db import get_connection, get_device_data, save_device_data

logger = logging.getLogger(__name__)

BASE_URL = "https://api.ouraring.com/v2/usercollection"

# Maps API endpoint suffix to data_type stored in DB
ENDPOINTS = {
    "daily_sleep": "sleep",
    "daily_readiness": "readiness",
    "daily_activity": "activity",
    "heartrate": "heart_rate",
}


def _get_last_sync_date(user_id: str) -> str:
    """Return the start_date parameter for the API call.

    Looks at the latest recorded_at across all oura data types.
    If none found, defaults to 7 days ago.
    """
    records = get_device_data(user_id, source="oura")
    if records:
        # records are ordered by recorded_at DESC, so first is latest
        latest = records[0]["recorded_at"]
        # Return the date portion — we re-fetch the latest day to catch updates
        return latest[:10]

    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    return seven_days_ago.strftime("%Y-%m-%d")


def _fetch_endpoint(endpoint: str, start_date: str) -> list[dict]:
    """Fetch data from a single Oura API v2 endpoint.

    Returns the list of data items, or empty list on error.
    """
    url = f"{BASE_URL}/{endpoint}"
    headers = {"Authorization": f"Bearer {settings.oura_access_token}"}
    params = {"start_date": start_date}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except requests.RequestException as exc:
        logger.error("Oura API error for %s: %s", endpoint, exc)
        return []


def _record_exists(user_id: str, source: str, data_type: str, recorded_at: str) -> bool:
    """Check if a device_data record already exists for the given key."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM device_data WHERE user_id = ? AND source = ? "
            "AND data_type = ? AND recorded_at = ?",
            (user_id, source, data_type, recorded_at),
        ).fetchone()
    return row is not None


def sync_oura(user_id: str) -> dict:
    """Sync Oura Ring data for a user.

    Pulls sleep, readiness, activity, and heart rate data from the Oura API v2.
    Only inserts new records (idempotent by user_id + source + data_type + recorded_at).

    Returns a summary dict with counts of records synced per data type.
    """
    start_date = _get_last_sync_date(user_id)
    logger.info("Syncing Oura data for user %s since %s", user_id, start_date)

    result: dict[str, int] = {}

    for endpoint, data_type in ENDPOINTS.items():
        items = _fetch_endpoint(endpoint, start_date)
        count = 0

        for item in items:
            day = item.get("day", item.get("timestamp", "")[:10])
            if not day:
                continue

            recorded_at = f"{day}T00:00:00+00:00"

            if _record_exists(user_id, "oura", data_type, recorded_at):
                continue

            save_device_data(
                user_id=user_id,
                source="oura",
                data_type=data_type,
                data=item,
                recorded_at=recorded_at,
            )
            count += 1

        result[data_type] = count
        logger.info("Oura %s: synced %d records for user %s", data_type, count, user_id)

    return result
