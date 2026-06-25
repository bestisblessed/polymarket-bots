#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

username="${1:-balthazarpoly}"
python scripts/x_api_export.py lookup-user "$username"
