#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python scripts/x_api_export.py auth-check
