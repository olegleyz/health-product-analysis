"""Renpho scales data sync.

Fetches body composition measurements via reverse-engineered API
or falls back to Garmin body composition data.
"""

import logging
from datetime import datetime, timedelta, timezone

import requests

from config import settings
from src.db import get_connection, get_device_data, save_device_data

logger = logging.getLogger(__name__)

RENPHO_LOGIN_URL = "https://renpho.qnclouds.com/api/v3/users/sign_in.json"
RENPHO_MEASUREMENTS_URL = "https://renpho.qnclouds.com/api/v3/measurements.json"


def _get_last_sync_date(user_id: str) -> str:
    """Return the earliest date to fetch from.

    Looks at the latest recorded_at for weight data.
    Defaults to 7 days ago if nothing found.
    """
    records = get_device_data(user_id, data_type="weight")
    if records:
        return records[0]["recorded_at"][:10]

    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    return seven_days_ago.strftime("%Y-%m-%d")


def _record_exists(
    user_id: str, source: str, data_type: str, recorded_at: str
) -> bool:
    """Check if a device_data record already exists for the given key."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM device_data WHERE user_id = ? AND source = ? "
            "AND data_type = ? AND recorded_at = ?",
            (user_id, source, data_type, recorded_at),
        ).fetchone()
    return row is not None


def _renpho_login() -> str | None:
    """Authenticate with Renpho API, return session token or None."""
    try:
        resp = requests.post(
            RENPHO_LOGIN_URL,
            json={
                "email": settings.renpho_email,
                "password": settings.renpho_password,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        token = (
            data.get("terminal_user_session_key")
            or data.get("session_key")
            or (data.get("user", {}) or {}).get("terminal_user_session_key")
        )
        return token
    except Exception as exc:
        logger.warning("Renpho login failed: %s", exc)
        return None


def _fetch_renpho_measurements(session_token: str) -> list[dict]:
    """Fetch measurements from Renpho API using session token."""
    try:
        resp = requests.get(
            RENPHO_MEASUREMENTS_URL,
            headers={"terminal_user_session_key": session_token},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return (
            data.get("last_ary", data.get("measurements", data.get("data", [])))
            or []
        )
    except Exception as exc:
        logger.warning("Renpho fetch measurements failed: %s", exc)
        return []


def _parse_renpho_measurement(item: dict) -> tuple[dict, str] | None:
    """Extract body composition data and timestamp from a Renpho measurement.

    Returns (data_dict, recorded_at) or None if unusable.
    """
    weight = item.get("weight")
    if weight is None:
        return None

    data: dict = {"weight_kg": round(float(weight), 2)}

    field_map = {
        "bodyfat": "body_fat_pct",
        "body_fat": "body_fat_pct",
        "muscle": "muscle_mass_kg",
        "muscle_mass": "muscle_mass_kg",
        "bmi": "bmi",
        "water": "water_pct",
        "water_percentage": "water_pct",
        "bone": "bone_mass_kg",
        "bone_mass": "bone_mass_kg",
    }

    for api_key, db_key in field_map.items():
        val = item.get(api_key)
        if val is not None:
            data[db_key] = round(float(val), 2)

    ts = item.get("time_stamp") or item.get("created_at") or item.get("measured_at")
    if ts is None:
        return None

    if isinstance(ts, (int, float)):
        recorded_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    else:
        recorded_at = str(ts)

    return data, recorded_at


def _sync_from_renpho(user_id: str) -> dict | None:
    """Try syncing from Renpho API. Returns result dict or None on failure."""
    if not settings.renpho_email or not settings.renpho_password:
        logger.info("Renpho credentials not configured, skipping")
        return None

    token = _renpho_login()
    if token is None:
        return None

    measurements = _fetch_renpho_measurements(token)
    if not measurements:
        logger.info("No Renpho measurements returned")
        return None

    count = 0
    for item in measurements:
        parsed = _parse_renpho_measurement(item)
        if parsed is None:
            continue

        data, recorded_at = parsed

        if _record_exists(user_id, "renpho", "weight", recorded_at):
            continue

        save_device_data(
            user_id=user_id,
            source="renpho",
            data_type="weight",
            data=data,
            recorded_at=recorded_at,
        )
        count += 1

    logger.info("Renpho: synced %d weight records for user %s", count, user_id)
    return {"weight": count}


def _sync_from_garmin(user_id: str) -> dict | None:
    """Fallback: pull body composition from Garmin Connect."""
    try:
        from garminconnect import Garmin
    except ImportError:
        logger.warning("garminconnect not installed, cannot fall back to Garmin")
        return None

    if not settings.garmin_email or not settings.garmin_password:
        logger.info("Garmin credentials not configured, skipping fallback")
        return None

    try:
        client = Garmin(settings.garmin_email, settings.garmin_password)
        client.login()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        body_comp = client.get_body_composition(today)
    except Exception as exc:
        logger.warning("Garmin body composition fetch failed: %s", exc)
        return None

    if not body_comp:
        return None

    weight_list = body_comp.get("dateWeightList", body_comp.get("weightList", []))
    if not weight_list:
        weight_list = [body_comp] if body_comp.get("weight") else []

    count = 0
    for entry in weight_list:
        weight = entry.get("weight")
        if weight is None:
            continue

        weight_val = float(weight)
        weight_kg = weight_val / 1000.0 if weight_val > 500 else weight_val

        data: dict = {"weight_kg": round(weight_kg, 2)}

        if entry.get("bodyFat") is not None:
            data["body_fat_pct"] = round(float(entry["bodyFat"]), 2)
        if entry.get("muscleMass") is not None:
            muscle_val = float(entry["muscleMass"])
            muscle_kg = muscle_val / 1000.0 if muscle_val > 500 else muscle_val
            data["muscle_mass_kg"] = round(muscle_kg, 2)
        if entry.get("bmi") is not None:
            data["bmi"] = round(float(entry["bmi"]), 2)

        ts = entry.get("date") or entry.get("calendarDate") or today
        if isinstance(ts, (int, float)):
            recorded_at = datetime.fromtimestamp(
                ts / 1000, tz=timezone.utc
            ).isoformat()
        else:
            recorded_at = f"{str(ts)[:10]}T00:00:00+00:00"

        if _record_exists(user_id, "garmin", "weight", recorded_at):
            continue

        save_device_data(
            user_id=user_id,
            source="garmin",
            data_type="weight",
            data=data,
            recorded_at=recorded_at,
        )
        count += 1

    logger.info(
        "Garmin fallback: synced %d weight records for user %s", count, user_id
    )
    return {"weight": count}


def sync_renpho(user_id: str) -> dict:
    """Sync body composition data for a user.

    Primary: Renpho reverse-engineered API.
    Fallback: Garmin Connect body composition.
    Idempotent -- skips records that already exist.

    Returns a summary dict, e.g. {"weight": 3} or {"weight": 0, "error": "..."}.
    """
    logger.info("Starting Renpho sync for user %s", user_id)

    result = _sync_from_renpho(user_id)
    if result is not None:
        return result

    logger.info("Renpho failed, trying Garmin fallback for user %s", user_id)
    result = _sync_from_garmin(user_id)
    if result is not None:
        return result

    logger.error(
        "Both Renpho and Garmin body comp sync failed for user %s", user_id
    )
    return {"weight": 0, "error": "both sources failed"}
