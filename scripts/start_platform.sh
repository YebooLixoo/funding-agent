#!/bin/bash
# Start the public-facing platform (backend + frontend dev servers)
# Prerequisites: PostgreSQL running on localhost:5432 with database funding_platform

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Funding Agent Platform ==="
echo ""

# Check PostgreSQL
if ! pg_isready -q 2>/dev/null; then
    echo "PostgreSQL not running. Start it with:"
    echo "  brew services start postgresql@16"
    echo "  createdb funding_platform"
    exit 1
fi

echo "Starting backend (FastAPI)..."
cd "$PROJECT_DIR"
uv run uvicorn web.main:app --reload --port 8000 &
BACKEND_PID=$!

echo "Starting frontend (Vite)..."
cd "$PROJECT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
