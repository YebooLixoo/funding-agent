#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" = "--prod" ]; then
    uv run python -m web.cli email-digest --due
else
    if [ -z "${ADMIN_EMAIL:-}" ]; then
        echo "ERROR: ADMIN_EMAIL not set; cannot run test mode" >&2
        exit 1
    fi
    uv run python -m web.cli email-digest --user-email "$ADMIN_EMAIL" --test
fi
