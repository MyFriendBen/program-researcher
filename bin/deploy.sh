#!/usr/bin/env bash
# Deploy program-researcher to Heroku.
#
# Run from the program-researcher directory. Expects benefits-api and
# benefits-calculator to be checked out as siblings (../benefits-api, etc.).
#
# Builds a clean deploy from a temporary git repo so vendor files can be
# included without affecting the local working tree or branch history.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PARENT_DIR="$(cd "$REPO_ROOT/.." && pwd)"

MODELS_SRC="$PARENT_DIR/benefits-api/screener/models.py"
TYPES_SRC="$PARENT_DIR/benefits-calculator/src/Types/FormData.ts"

# Verify sibling files exist
if [ ! -f "$MODELS_SRC" ]; then
  echo "ERROR: $MODELS_SRC not found. Is benefits-api checked out as a sibling directory?"
  exit 1
fi

if [ ! -f "$TYPES_SRC" ]; then
  echo "ERROR: $TYPES_SRC not found. Is benefits-calculator checked out as a sibling directory?"
  exit 1
fi

# Ensure the heroku remote is configured in the source repo
cd "$REPO_ROOT"
if ! git remote get-url heroku &>/dev/null; then
  echo "Adding heroku remote..."
  heroku git:remote --app mfb-program-researcher
fi
HEROKU_URL="$(git remote get-url heroku)"

# Create a temp dir with a fresh git repo
DEPLOY_DIR="$(mktemp -d)"
trap "rm -rf '$DEPLOY_DIR'" EXIT

echo "Building deploy in $DEPLOY_DIR ..."

# Copy the repo into the temp dir (excluding .git and vendor/sibling_files)
rsync -a --exclude='.git' --exclude='vendor/sibling_files' "$REPO_ROOT/" "$DEPLOY_DIR/"

# Copy sibling files in (no gitignore to worry about in the fresh repo)
mkdir -p "$DEPLOY_DIR/vendor/sibling_files"
cp "$MODELS_SRC" "$DEPLOY_DIR/vendor/sibling_files/models.py"
cp "$TYPES_SRC" "$DEPLOY_DIR/vendor/sibling_files/FormData.ts"

# Remove the vendor/sibling_files gitignore entry so git tracks them
sed -i '' '/vendor\/sibling_files/d' "$DEPLOY_DIR/.gitignore"

# Commit everything in the temp repo and push to Heroku
git -C "$DEPLOY_DIR" init -b main
git -C "$DEPLOY_DIR" add .
git -C "$DEPLOY_DIR" commit -m "deploy"
git -C "$DEPLOY_DIR" remote add heroku "$HEROKU_URL"
git -C "$DEPLOY_DIR" push heroku main --force

echo ""
echo "Deploy complete. Scale dynos if needed:"
echo "  heroku ps:scale web=1 worker=1 --app mfb-program-researcher"
