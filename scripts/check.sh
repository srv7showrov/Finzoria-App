#!/usr/bin/env bash
# Same checks as check.ps1 for macOS/Linux/cloud shells.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
(cd "$root/backend" && .venv/bin/python -m pytest)
(cd "$root/frontend" && npm run build)
