#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

username="${1:-balthazarpoly}"
shift || true

python scripts/x_api_export.py export-user "$username" --download-media "$@"
