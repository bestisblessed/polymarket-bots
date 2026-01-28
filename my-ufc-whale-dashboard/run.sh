#!/bin/bash
# UFC Whale Dashboard - Fetch holders data for all UFC fights
# Cron: */30 * * * * /Users/td/Code/polymarket-bots/my-ufc-whale-dashboard/run.sh

cd "$(dirname "$0")"
python fetch_ufc_holders.py
