"""Application configuration.

Loads environment variables from .env and exposes a Settings dataclass.
"""

from dataclasses import dataclass, field
from pathlib import Path
import logging
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """All application settings, loaded from environment variables."""

    # Telegram
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # Claude API
    claude_api_key: str = os.getenv("CLAUDE_API_KEY", "")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

    # Garmin Connect
    garmin_email: str = os.getenv("GARMIN_EMAIL", "")
    garmin_password: str = os.getenv("GARMIN_PASSWORD", "")

    # Oura Ring
    oura_access_token: str = os.getenv("OURA_ACCESS_TOKEN", "")

    # Strava
    strava_client_id: str = os.getenv("STRAVA_CLIENT_ID", "")
    strava_client_secret: str = os.getenv("STRAVA_CLIENT_SECRET", "")
    strava_refresh_token: str = os.getenv("STRAVA_REFRESH_TOKEN", "")

    # Renpho (optional)
    renpho_email: str = os.getenv("RENPHO_EMAIL", "")
    renpho_password: str = os.getenv("RENPHO_PASSWORD", "")

    # Database
    db_path: str = os.getenv("DB_PATH", "./data/concierge.db")

    # Allowed Telegram user IDs
    user_telegram_ids: list[str] = field(default_factory=list)

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    def __post_init__(self) -> None:
        raw_ids = os.getenv("USER_TELEGRAM_IDS", "")
        self.user_telegram_ids = [
            uid.strip() for uid in raw_ids.split(",") if uid.strip()
        ]


settings = Settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)

# Add file handler if logs directory exists
_log_dir = Path("logs")
if _log_dir.exists():
    _file_handler = logging.FileHandler(_log_dir / "concierge.log")
    _file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(_file_handler)
