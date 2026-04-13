#!/usr/bin/env bash
# Restart the bot process via systemd. Safe to call from CI/CD.
set -euo pipefail

APP_DIR="$HOME/health-product-analysis/health-concierge"

# Install service file if not already there or if it changed
cp "$APP_DIR/scripts/health-concierge.service" /etc/systemd/system/health-concierge.service
systemctl daemon-reload
systemctl enable health-concierge

# Kill any stray non-systemd bot processes
BOT_PID=$(pgrep -f 'python -m src\.bot' 2>/dev/null || true)
SYSTEMD_PID=$(systemctl show health-concierge --property=MainPID --value 2>/dev/null || echo "0")
if [ -n "$BOT_PID" ] && [ "$BOT_PID" != "$SYSTEMD_PID" ]; then
    echo "Killing stray bot process (PID $BOT_PID)..."
    kill "$BOT_PID" 2>/dev/null || true
    sleep 2
fi

# Restart via systemd
systemctl restart health-concierge
sleep 3

if systemctl is-active --quiet health-concierge; then
    echo "Bot started via systemd ($(systemctl show health-concierge --property=MainPID --value))"
else
    echo "ERROR: Bot failed to start"
    systemctl status health-concierge --no-pager
    exit 1
fi
