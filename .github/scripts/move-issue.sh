#!/usr/bin/env bash
# Usage: move-issue.sh <issue_number> <status_name>
# Moves a GitHub issue to the given status in the GitHub Project board.
# Reads node IDs from .github/project-config.json.
#
# Required env vars (set automatically by GitHub Actions):
#   GH_TOKEN          — PAT with repo + project scopes
#   GITHUB_REPOSITORY — owner/repo (e.g. acme/my-app)
#   PROJECT_NUMBER    — GitHub Project number (set via gh variable set)

set -euo pipefail

ISSUE_NUMBER=$1
STATUS_NAME=$2
CONFIG=".github/project-config.json"
REPO="${GITHUB_REPOSITORY}"
PROJECT_NUMBER="${PROJECT_NUMBER}"

PROJECT_NODE_ID=$(jq -r '.project_node_id' "$CONFIG")
STATUS_FIELD_ID=$(jq -r '.status_field_id' "$CONFIG")
OPTION_ID=$(jq -r --arg name "$STATUS_NAME" '.options[$name]' "$CONFIG")

if [ -z "$PROJECT_NODE_ID" ] || [ -z "$STATUS_FIELD_ID" ]; then
  echo "ERROR: $CONFIG is not populated — run setup.sh to initialize the project board" >&2
  exit 1
fi

if [ "$OPTION_ID" = "null" ]; then
  echo "ERROR: Unknown status '$STATUS_NAME'" >&2
  exit 1
fi

# Get issue node ID
ISSUE_NODE_ID=$(gh api "repos/$REPO/issues/$ISSUE_NUMBER" --jq '.node_id')

# Find the project item ID for this issue
ITEM_ID=$(gh api graphql -f query="
{
  node(id: \"$ISSUE_NODE_ID\") {
    ... on Issue {
      projectItems(first: 10) {
        nodes {
          id
          project { number }
        }
      }
    }
  }
}" --jq ".data.node.projectItems.nodes[] | select(.project.number == $PROJECT_NUMBER) | .id")

if [ -z "$ITEM_ID" ]; then
  echo "Issue #$ISSUE_NUMBER not found in project #$PROJECT_NUMBER — skipping"
  exit 0
fi

# Update the status
gh api graphql -f query="
mutation {
  updateProjectV2ItemFieldValue(input: {
    projectId: \"$PROJECT_NODE_ID\"
    itemId: \"$ITEM_ID\"
    fieldId: \"$STATUS_FIELD_ID\"
    value: { singleSelectOptionId: \"$OPTION_ID\" }
  }) {
    projectV2Item { id }
  }
}" > /dev/null

echo "Moved issue #$ISSUE_NUMBER to '$STATUS_NAME'"
