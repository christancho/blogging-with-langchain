#!/usr/bin/env bash
# Boots the real stack (docker-compose.yml) from already-built images, in
# production mode, and checks it end to end:
#   1. api /health          (app up, migrations ran, DB reachable)
#   2. web /api/health      (web -> api -> db)
#   3. /mcp without a JWT   must be 401 (Cloudflare Access auth fails closed)
# Used by CI (locally built images) and by release candidates (published images).
# Needs IMAGE_API and IMAGE_WEB.
set -euo pipefail

: "${IMAGE_API:?set IMAGE_API}" "${IMAGE_WEB:?set IMAGE_WEB}"
cd "$(dirname "$0")/.."
export COMPOSE_PROJECT_NAME="smoke-$$"
compose=(docker compose -f docker-compose.yml -f scripts/compose.smoke.yaml)

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "::group::container logs"
    "${compose[@]}" ps -a || true
    "${compose[@]}" logs --no-color --tail 200 || true
    echo "::endgroup::"
  fi
  "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT

"${compose[@]}" up -d --no-build --wait --wait-timeout 180

check() { # name, expected status, command...
  local name=$1 want=$2; shift 2
  local got
  got=$("$@" || true)
  if [ "$got" = "$want" ]; then echo "ok   $name ($got)"; else echo "FAIL $name: got '$got', want $want"; return 1; fi
}

check "api /health" 200 "${compose[@]}" exec -T api curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health
check "web /api/health" 200 curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/api/health
check "mcp rejects no JWT" 401 "${compose[@]}" exec -T api curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8000/mcp
echo "smoke test passed"
