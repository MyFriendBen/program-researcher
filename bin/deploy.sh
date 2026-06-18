#!/usr/bin/env bash
# Deploy program-researcher to Heroku.
#
# Run from the program-researcher directory. Expects benefits-api and
# benefits-calculator to be checked out as siblings (../benefits-api, etc.).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PARENT_DIR="$(cd "$REPO_ROOT/.." && pwd)"

MODELS_SRC="$PARENT_DIR/benefits-api/screener/models.py"
TYPES_SRC="$PARENT_DIR/benefits-calculator/src/Types/FormData.ts"
VENDOR_DIR="$REPO_ROOT/vendor/sibling_files"

# Verify sibling files exist
if [ ! -f "$MODELS_SRC" ]; then
  echo "ERROR: $MODELS_SRC not found. Is benefits-api checked out as a sibling directory?"
  exit 1
fi

if [ ! -f "$TYPES_SRC" ]; then
  echo "ERROR: $TYPES_SRC not found. Is benefits-calculator checked out as a sibling directory?"
  exit 1
fi

# Copy sibling files into vendor/
mkdir -p "$VENDOR_DIR"
cp "$MODELS_SRC" "$VENDOR_DIR/models.py"
cp "$TYPES_SRC" "$VENDOR_DIR/FormData.ts"
echo "Copied sibling files to $VENDOR_DIR"

# Stage and push, cleaning up vendor files afterwards
cd "$REPO_ROOT"
git add --force vendor/sibling_files/
git commit -m "chore: bundle sibling files for deploy"
git push heroku main

# Remove vendored files so they don't linger in the working tree
git rm -r --cached vendor/sibling_files/ 2>/dev/null || true
rm -rf "$VENDOR_DIR"
git commit -m "chore: remove vendored sibling files post-deploy"

echo ""
echo "Deploy complete. Scale dynos if needed:"
echo "  heroku ps:scale web=1 worker=1 --app mfb-program-researcher"
