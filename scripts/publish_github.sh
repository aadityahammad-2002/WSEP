#!/usr/bin/env bash
# Create the public anonymous repository after authenticating with GitHub CLI.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo 'Usage: bash scripts/publish_github.sh <anonymous-repository-name>' >&2
  exit 2
fi
command -v git >/dev/null || { echo 'git is required' >&2; exit 1; }
command -v gh >/dev/null || { echo 'GitHub CLI (gh) is required' >&2; exit 1; }
gh auth status >/dev/null

cd "$(dirname "$0")/.."
if [[ ! -d .git ]]; then
  git init -b main
fi
git add .
if ! git diff --cached --quiet; then
  git commit -m 'Implement day-ahead wind forecast analytics'
fi
gh repo create "$1" --public --source=. --remote=origin --push
