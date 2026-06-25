#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

username="${1:-balthazarpoly}"
out_dir="${2:-/tmp/x_api_${username}_smoke}"

python scripts/x_api_export.py export-user "$username" \
  --max-pages 1 \
  --delay 0 \
  --no-recent-fallback \
  --out-dir "$out_dir"
