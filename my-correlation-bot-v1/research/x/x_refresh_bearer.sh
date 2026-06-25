#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

python x_api_export.py refresh-bearer --save
