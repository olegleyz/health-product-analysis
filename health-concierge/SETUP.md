# Health Concierge Setup Guide

## Prerequisites

- Python 3.11 or newer
- A Telegram bot token (create one via [@BotFather](https://t.me/BotFather))
- Claude API key from [console.anthropic.com](https://console.anthropic.com/)
- API credentials for your devices (see Device Setup below)

## Installation

```bash
# Clone the repository
git clone <repo-url> health-concierge
cd health-concierge

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create required directories
mkdir -p data logs backups
```

## Configuration

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your values:

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `CLAUDE_API_KEY` | Yes | Anthropic API key |
| `CLAUDE_MODEL` | No | Defaults to `claude-sonnet-4-20250514` |
| `USER_TELEGRAM_IDS` | Yes | Comma-separated Telegram user IDs |
| `DB_PATH` | No | Defaults to `./data/concierge.db` |
| `GARMIN_EMAIL` | Yes | Garmin Connect email |
| `GARMIN_PASSWORD` | Yes | Garmin Connect password |
| `OURA_ACCESS_TOKEN` | Yes | Oura personal access token |
| `STRAVA_CLIENT_ID` | Yes | Strava API client ID |
| `STRAVA_CLIENT_SECRET` | Yes | Strava API client secret |
| `STRAVA_REFRESH_TOKEN` | Yes | Strava OAuth2 refresh token |
| `RENPHO_EMAIL` | No | Renpho account email (optional) |
| `RENPHO_PASSWORD` | No | Renpho account password (optional) |
| `LOG_LEVEL` | No | Defaults to `INFO` |

### Finding Your Telegram User ID

Send a message to [@userinfobot](https://t.me/userinfobot) on Telegram. It will reply with your numeric user ID.

## Initialize the Database

```bash
.venv/bin/python scripts/setup_db.py
```

## Run the Bot

```bash
.venv/bin/python -m src.bot
```

The bot listens for incoming Telegram messages and responds via the concierge brain.

## Cron Setup (Scheduled Tasks)

The concierge uses cron for proactive check-ins, data syncing, and backups.

Review the cron configuration:

```bash
cat scripts/crontab.txt
```

Install the cron jobs:

```bash
bash scripts/install_cron.sh
```

This installs:
- Database backup at 2:00 AM
- Data sync every 4 hours
- Morning check-in at 8:00 AM
- Evening check-in at 9:00 PM
- Nudge checks every 2 hours (9 AM - 10 PM)
- Daily summary at 11:30 PM
- Weekly reflection on Sundays at 8:00 PM
- Daily counter reset at midnight

All cron jobs are wrapped with `error_alert.py`, which sends a Telegram alert to the first configured user if any job fails.

## Adding a Second User

1. Get the second user's Telegram user ID (see above).
2. In `.env`, add their ID to the comma-separated list:
   ```
   USER_TELEGRAM_IDS=123456789,987654321
   ```
3. Have them start a conversation with the bot on Telegram (send `/start`).
4. The bot handles onboarding automatically.

No other changes are needed. The bot, cron jobs, and data syncs all iterate over every user in `USER_TELEGRAM_IDS`.

## Manual Backup

```bash
.venv/bin/python scripts/backup_db.py
```

Backups are saved to `backups/` with a UTC timestamp. The last 7 backups are kept automatically.

## Running Tests

```bash
.venv/bin/python -m pytest --tb=short -q
```

## Device Setup Notes

### Garmin Connect
Uses the unofficial `garminconnect` library. Provide your Garmin email and password in `.env`. Sessions are cached automatically.

### Oura Ring
Uses the official Oura API v2. Create a Personal Access Token at [cloud.ouraring.com/personal-access-tokens](https://cloud.ouraring.com/personal-access-tokens).

### Strava
Uses `stravalib` with OAuth2. You need to create a Strava API application at [strava.com/settings/api](https://www.strava.com/settings/api), then obtain a refresh token via the OAuth2 flow.

### Renpho (Optional)
Uses a reverse-engineered API. If credentials are not provided, body composition data falls back to Garmin Connect.
