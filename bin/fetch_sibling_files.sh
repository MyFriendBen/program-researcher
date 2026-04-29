#!/usr/bin/env bash
# -----------------------------------------------------------------------
# fetch_sibling_files.sh
#
# Downloads the two files from sibling repos that the research agent
# needs to parse screener fields. Runs at deploy time (Heroku release
# phase) or at boot.
#
# Requires GITHUB_TOKEN with read access to the MyFriendBen org repos.
# Falls back to unauthenticated requests for public repos.
#
# The downloaded files land in ./vendor/sibling_files/ and the env vars
# RESEARCH_AGENT_BACKEND_MODELS_PATH / RESEARCH_AGENT_FRONTEND_TYPES_PATH
# are exported so config.py picks them up.
# -----------------------------------------------------------------------

set -euo pipefail

DEST_DIR="${1:-$(pwd)/vendor/sibling_files}"
mkdir -p "$DEST_DIR"

# GitHub branch to pull from (default: main)
BRANCH="${SIBLING_FILES_BRANCH:-main}"

# Auth header (optional — needed for private repos)
AUTH_HEADER=""
if [ -n "${GITHUB_TOKEN:-}" ]; then
  AUTH_HEADER="Authorization: token $GITHUB_TOKEN"
fi

fetch_file() {
  local repo="$1"
  local path="$2"
  local dest="$3"

  local url="https://raw.githubusercontent.com/MyFriendBen/${repo}/${BRANCH}/${path}"

  echo "Fetching ${repo}/${path} ..."

  local http_code
  if [ -n "$AUTH_HEADER" ]; then
    http_code=$(curl -sS -w "%{http_code}" -o "$dest" -H "$AUTH_HEADER" "$url")
  else
    http_code=$(curl -sS -w "%{http_code}" -o "$dest" "$url")
  fi

  if [ "$http_code" -ne 200 ]; then
    echo "  WARNING: Got HTTP $http_code for $url"
    echo "  The research agent will still run but screener field parsing may be incomplete."
    rm -f "$dest"
    return 1
  fi

  echo "  Saved to $dest ($(wc -c < "$dest" | tr -d ' ') bytes)"
  return 0
}

# ---- Fetch the two files ----

MODELS_DEST="$DEST_DIR/models.py"
TYPES_DEST="$DEST_DIR/FormData.ts"

fetch_file "benefits-api" "screener/models.py" "$MODELS_DEST" || true
fetch_file "benefits-calculator" "src/Types/FormData.ts" "$TYPES_DEST" || true

# ---- Export env vars for config.py ----

if [ -f "$MODELS_DEST" ]; then
  export RESEARCH_AGENT_BACKEND_MODELS_PATH="$MODELS_DEST"
  echo "RESEARCH_AGENT_BACKEND_MODELS_PATH=$MODELS_DEST"
fi

if [ -f "$TYPES_DEST" ]; then
  export RESEARCH_AGENT_FRONTEND_TYPES_PATH="$TYPES_DEST"
  echo "RESEARCH_AGENT_FRONTEND_TYPES_PATH=$TYPES_DEST"
fi

echo "Done."
