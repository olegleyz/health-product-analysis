#!/usr/bin/env bash
# Install Health Concierge cron jobs.
#
# Usage:  bash scripts/install_cron.sh
#
# What it does:
#   1. Shows you the cron entries that will be installed
#   2. Asks for confirmation
#   3. Backs up your existing crontab to logs/crontab.backup
#   4. Merges the new entries with your existing crontab (or installs fresh)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CRONTAB_SRC="$SCRIPT_DIR/crontab.txt"
BACKUP_FILE="$PROJECT_DIR/logs/crontab.backup"

if [ ! -f "$CRONTAB_SRC" ]; then
    echo "ERROR: $CRONTAB_SRC not found"
    exit 1
fi

# Build the resolved crontab by replacing PROJECT_DIR placeholder
RESOLVED=$(sed "s|/path/to/health-concierge|$PROJECT_DIR|g" "$CRONTAB_SRC")

echo "============================================="
echo "  Health Concierge — Cron Installation"
echo "============================================="
echo ""
echo "Project directory: $PROJECT_DIR"
echo ""
echo "The following cron entries will be installed:"
echo "---------------------------------------------"
echo "$RESOLVED"
echo "---------------------------------------------"
echo ""

read -p "Install these cron jobs? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Ensure logs directory exists
mkdir -p "$PROJECT_DIR/logs"

# Backup existing crontab
EXISTING=$(crontab -l 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
    echo "$EXISTING" > "$BACKUP_FILE"
    echo "Existing crontab backed up to: $BACKUP_FILE"
fi

# Remove any previous Health Concierge entries from existing crontab
CLEANED=$(echo "$EXISTING" | grep -v "health-concierge" | grep -v "Health Concierge" || true)

# Build new crontab: existing (cleaned) + new entries
{
    if [ -n "$CLEANED" ]; then
        echo "$CLEANED"
        echo ""
    fi
    echo "$RESOLVED"
} | crontab -

echo ""
echo "Cron jobs installed successfully."
echo "Verify with: crontab -l"
