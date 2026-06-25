#!/bin/bash

python export_polymarket_activity.py
python export_polymarket_trade_history_windows.py --max-windows 500
