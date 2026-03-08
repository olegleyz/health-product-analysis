#!/usr/bin/env bash
# =============================================================================
# Health Concierge — VPS Deploy Script
# =============================================================================
# Usage:
#   1. Provision a VPS (Ubuntu 22.04+ recommended)
#   2. SSH in:  ssh user@your-vps-ip
#   3. Copy this script:  scp scripts/deploy.sh user@your-vps-ip:~/
#   4. Run it:  bash deploy.sh
#
# After deploy:
#   - Copy your .env to the VPS:
#       scp health-concierge/.env user@your-vps-ip:~/health-concierge/.env
#   - Or create it manually on the VPS from .env.example
#
# IMPORTANT: Never commit .env to git. Transfer it via scp or create on VPS.
# =============================================================================

set -euo pipefail

REPO_URL="https://github.com/olegleyz/health-product-analysis.git"
PROJECT_DIR="$HOME/health-product-analysis"
APP_DIR="$PROJECT_DIR/health-concierge"

echo "=== Health Concierge VPS Deploy ==="

# --- System dependencies ---
echo "[1/6] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "       Python version: $PYTHON_VERSION"

# --- Clone or update repo ---
echo "[2/6] Setting up repository..."
if [ -d "$PROJECT_DIR" ]; then
    echo "       Repo exists, pulling latest..."
    cd "$PROJECT_DIR"
    git pull origin master
else
    git clone "$REPO_URL" "$PROJECT_DIR"
fi

cd "$APP_DIR"

# --- Virtual environment ---
echo "[3/6] Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -e . -q

# --- Directories ---
echo "[4/6] Creating data directories..."
mkdir -p data logs backups

# --- .env check ---
echo "[5/6] Checking configuration..."
if [ ! -f ".env" ]; then
    echo ""
    echo "  *** .env file not found! ***"
    echo "  Copy it from your laptop:"
    echo "    scp health-concierge/.env $(whoami)@$(hostname -I | awk '{print $1}'):$APP_DIR/.env"
    echo ""
    echo "  Or create it manually:"
    echo "    cp .env.example .env"
    echo "    nano .env"
    echo ""
fi

# --- Database ---
echo "[6/6] Initializing database..."
cd "$APP_DIR"
.venv/bin/python scripts/setup_db.py

echo ""
echo "=== Deploy complete! ==="
echo ""
echo "Next steps:"
echo ""
if [ ! -f ".env" ]; then
    echo "  1. Copy your .env file to this server (see above)"
    echo "  2. Start the bot:    cd $APP_DIR && .venv/bin/python -m src.bot"
    echo "  3. Install cron:     cd $APP_DIR && bash scripts/install_cron.sh"
else
    echo "  1. Start the bot:    cd $APP_DIR && .venv/bin/python -m src.bot"
    echo "  2. Install cron:     cd $APP_DIR && bash scripts/install_cron.sh"
fi
echo ""
echo "  Run in background:     nohup .venv/bin/python -m src.bot > logs/bot.log 2>&1 &"
echo "  Or use systemd:        sudo cp scripts/health-concierge.service /etc/systemd/system/"
echo "                         sudo systemctl enable --now health-concierge"
echo ""
