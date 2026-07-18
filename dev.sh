#!/usr/bin/env bash
set -e

# Start the database
docker compose up -d db

# Wait for db to be healthy
echo "Waiting for database..."
until docker compose exec db pg_isready -U postgres -d blogforge &>/dev/null; do
  sleep 1
done

# Load env vars and override DATABASE_URL for native (non-Docker) access
set -a; source .env; set +a
export DATABASE_URL="postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@localhost:5432/blogforge"

# Start API in background
source .venv/bin/activate
# Scope --reload to the Python source only. Without --reload-dir, uvicorn
# watches the whole cwd tree (incl. web/.next/, which `next dev` rewrites
# constantly) and spams "changes detected" / churns reloads.
uvicorn api.main:app --reload --reload-dir api --reload-dir agentic &
API_PID=$!

# Start web in background
cd web && npm run dev &
WEB_PID=$!

# Trap Ctrl+C and kill both
trap "kill $API_PID $WEB_PID 2>/dev/null; docker compose stop db" INT TERM

echo ""
echo "API: http://localhost:8000"
echo "Web: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop"

wait
