#!/usr/bin/env bash
# Restart the bot process. Safe to call from CI/CD.
set -euo pipefail

APP_DIR="$HOME/health-product-analysis/health-concierge"
cd "$APP_DIR"

# Stop existing bot (if running)
BOT_PID=$(pgrep -f 'python -m src\.bot' 2>/dev/null || true)
if [ -n "$BOT_PID" ]; then
    echo "Stopping bot (PID $BOT_PID)..."
    kill "$BOT_PID" 2>/dev/null || true
    sleep 2
fi

# Start bot
echo "Starting bot..."
nohup .venv/bin/python -m src.bot >> logs/bot.log 2>&1 &
NEW_PID=$!
sleep 2

if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "Bot started (PID $NEW_PID)"
else
    echo "ERROR: Bot failed to start"
    tail -10 logs/bot.log
    exit 1
fi
