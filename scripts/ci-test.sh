#!/usr/bin/env bash
# Runs the test suites INSIDE the built images, so CI tests the same Python/Node
# runtime and dependencies that ship.
#   api: pytest against a throwaway Postgres (live LLM/search tests are skipped)
#   web: jest
# Needs IMAGE_API and IMAGE_WEB (set by the shared docker-ci workflow).
# Locally: IMAGE_API=<tag> IMAGE_WEB=<tag> bash scripts/ci-test.sh
set -euo pipefail

: "${IMAGE_API:?set IMAGE_API}" "${IMAGE_WEB:?set IMAGE_WEB}"
net="ci-test-$$"
db="ci-test-db-$$"

cleanup() {
  docker rm -f "$db" >/dev/null 2>&1 || true
  docker network rm "$net" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "$net" >/dev/null
docker run -d --name "$db" --network "$net" --network-alias db \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=blogforge_test postgres:16-alpine >/dev/null

echo "waiting for postgres..."
for _ in $(seq 1 30); do
  docker exec "$db" pg_isready -U postgres -d blogforge_test >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$db" pg_isready -U postgres -d blogforge_test

echo "::group::api: pytest"
docker run --rm --network "$net" \
  -e DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/blogforge_test \
  -e ENV=test \
  "$IMAGE_API" python -m pytest -q -m "not integration and not slow and not benchmark"
echo "::endgroup::"

echo "::group::web: jest"
docker run --rm -e CI=true "$IMAGE_WEB" npx jest --ci
echo "::endgroup::"
