#!/usr/bin/env bash
# start.sh — Launch Octagon Log for beta/test deployment
#
# Usage:
#   ./start.sh          Start with default settings (port 8080, 2 workers)
#   ./start.sh --dev    Start in development mode (Flask debug server)
#
# Environment (set in .env or export before running):
#   SECRET_KEY    — Required. Random string for session signing.
#   DATABASE_URL  — Optional. Defaults to sqlite:///instance/woodshop.db
#   PORT          — Optional. Defaults to 8080.
#   WORKERS       — Optional. Gunicorn workers. Defaults to 2.

set -e

# Load .env if present
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Ensure instance directory exists for SQLite
mkdir -p instance

PORT="${PORT:-8080}"
WORKERS="${WORKERS:-2}"

if [ "$1" = "--dev" ]; then
    echo "Starting in DEVELOPMENT mode on port $PORT..."
    export FLASK_CONFIG=development
    python run.py
else
    # Validate required env vars
    if [ -z "$SECRET_KEY" ]; then
        echo "ERROR: SECRET_KEY environment variable must be set."
        echo "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        exit 1
    fi

    echo "Starting Octagon Log (beta) on port $PORT with $WORKERS workers..."
    export FLASK_CONFIG=production
    exec gunicorn wsgi:app \
        --bind "0.0.0.0:$PORT" \
        --workers "$WORKERS" \
        --access-logfile - \
        --error-logfile - \
        --timeout 120
fi
