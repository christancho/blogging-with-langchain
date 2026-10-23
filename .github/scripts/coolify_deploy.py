#!/usr/bin/env python3
"""Deploy the Coolify apps whose files changed (or the ones asked for), one at a time.

Used by .github/workflows/deploy.yml on the self-hosted runner (home network).

Modes:
  --changed-files FILE   pick apps from changed paths (one per line)
  --apps api,web         deploy these apps (manual run)
  --dry-run              only print what would be deployed

Coolify API: POST /api/v1/deploy?uuid=<app> starts a deployment of the app's branch HEAD;
GET /api/v1/deployments/<deployment_uuid> reports queued / in_progress / finished / failed.
The token needs the deploy + read abilities.

Env: COOLIFY_URL, COOLIFY_TOKEN, SHA (optional; a mismatch with the deployed commit is
reported as a warning, since the branch may have moved on).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

COOLIFY_URL = os.environ.get("COOLIFY_URL", "http://192.168.2.127:8000").rstrip("/")
TOKEN = os.environ.get("COOLIFY_TOKEN", "")
SHA = os.environ.get("SHA", "")

# Coolify application UUIDs (identifiers, not secrets).
# Deploy order matters: web's health check calls the API, so api goes first.
APPS = {
    "api": "6qcysgqqppo00sfiqkgjnkhh",  # gitleaks:allow
    "web": "azfeymm7bpqh3wvytx86iff2",  # gitleaks:allow
}
# Paths that never need a deploy.
IGNORED_PREFIXES = ("docs/", "tests/", ".github/", "media/")
IGNORED_FILES = ("dev.sh", "pytest.ini", "docker-compose.yml", "docker-compose.override.yml",
                 ".gitignore", "CLAUDE.md")

POLL_SECONDS = 10
MAX_WAIT_SECONDS = 25 * 60


def app_for(path):
    """Which app a changed path belongs to (None = no deploy)."""
    if path.startswith("web/"):
        return None if path.endswith(".md") else "web"
    if path.startswith(IGNORED_PREFIXES) or path in IGNORED_FILES or path.endswith(".md"):
        return None
    return "api"  # api/, agentic/, requirements.txt, main.py, ... (api builds from the repo root)


def api(method, path, timeout=60):
    req = urllib.request.Request(COOLIFY_URL + "/api/v1" + path, method=method)
    req.add_header("Accept", "application/json")
    if TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {detail}") from None
    return json.loads(raw) if raw else {}


def deploy(name):
    out = api("POST", f"/deploy?uuid={APPS[name]}")
    deps = out.get("deployments") or []
    if not deps or not deps[0].get("deployment_uuid"):
        raise RuntimeError(f"Coolify did not start a deployment: {json.dumps(out)[:300]}")
    dep_uuid = deps[0]["deployment_uuid"]
    print(f"deployment {dep_uuid} started")
    waited, status, d = 0, "", {}
    while waited < MAX_WAIT_SECONDS:
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
        d = api("GET", f"/deployments/{dep_uuid}")
        if d.get("status") != status:
            status = d.get("status", "")
            print(f"  {waited}s: {status}")
        if status == "finished":
            commit = d.get("commit") or ""
            if SHA and commit and commit != SHA:
                print(f"::warning::{name} deployed {commit[:7]}, not {SHA[:7]} (branch moved on?)")
            return commit
        if status in ("failed", "cancelled-by-user"):
            raise RuntimeError(f"deployment {dep_uuid} {status} (see Coolify -> {name} -> Deployments)")
    raise RuntimeError(f"deployment {dep_uuid} still '{status}' after {MAX_WAIT_SECONDS // 60} min")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--changed-files")
    ap.add_argument("--apps")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.changed_files and not a.apps:
        ap.error("give --changed-files or --apps")

    if a.apps:
        wanted = {x.strip() for x in a.apps.split(",") if x.strip()}
        unknown = wanted - set(APPS)
        if unknown:
            print(f"::error::unknown app(s): {', '.join(sorted(unknown))} (known: {', '.join(APPS)})")
            return 1
    else:
        with open(a.changed_files) as f:
            changed = [l.strip() for l in f if l.strip()]
        wanted = {app_for(p) for p in changed} - {None}
    picked = [n for n in APPS if n in wanted]  # keep api-before-web order

    if not picked:
        print("Nothing to deploy: no app files changed.")
        return 0
    print(("DRY RUN — would deploy: " if a.dry_run else "Deploying: ") + ", ".join(picked))
    if a.dry_run:
        return 0

    for name in picked:
        t = time.time()
        print(f"::group::{name}")
        try:
            commit = deploy(name)
        except RuntimeError as e:
            print("::endgroup::")
            print(f"::error::{name} failed: {e}")
            print("Stopping: remaining apps were not deployed.")
            return 1
        print(f"ok in {time.time() - t:.0f}s, commit {commit[:7]}")
        print("::endgroup::")
    print(f"Done: {', '.join(picked)} deployed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
