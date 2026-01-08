#!/bin/bash
# Setup script for supervisord on Raspberry Pi
# Run this on your Raspberry Pi as root or with sudo

set -e

echo "=== Installing supervisord ==="
sudo apt-get update
sudo apt-get install -y supervisor

echo ""
echo "=== Copying configuration ==="
sudo cp /home/trinity/polymarket-bots/my-sports-bot/deploy/nfl-whale-supervisord.conf /etc/supervisor/conf.d/nfl-whale.conf

echo ""
echo "=== Creating log directory (if needed) ==="
mkdir -p /home/trinity/polymarket-bots/my-sports-bot
touch /home/trinity/polymarket-bots/my-sports-bot/log_nfl_whale_service.log
touch /home/trinity/polymarket-bots/my-sports-bot/log_nfl_whale_service.err.log
chown trinity:trinity /home/trinity/polymarket-bots/my-sports-bot/log_nfl_whale_service*.log

echo ""
echo "=== Reloading supervisord ==="
sudo supervisorctl reread
sudo supervisorctl update

echo ""
echo "=== Starting nfl-whale service ==="
sudo supervisorctl start nfl-whale

echo ""
echo "=== Checking status ==="
sudo supervisorctl status nfl-whale

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Useful commands:"
echo "  sudo supervisorctl status nfl-whale    # Check status"
echo "  sudo supervisorctl tail -f nfl-whale   # Follow logs"
echo "  sudo supervisorctl restart nfl-whale   # Restart service"
echo "  sudo supervisorctl stop nfl-whale      # Stop service"
echo "  sudo supervisorctl start nfl-whale     # Start service"
echo ""
echo "Logs are written to:"
echo "  /home/trinity/polymarket-bots/my-sports-bot/log_nfl_whale_service.log"
echo "  /home/trinity/polymarket-bots/my-sports-bot/log_nfl_whale_service.err.log"
