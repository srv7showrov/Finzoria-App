#!/usr/bin/env bash
# Same as package-source.ps1: archive of committed files only (no .env, databases, node_modules, venvs, builds).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
commit="$(git rev-parse --short HEAD)"
[ -z "$(git status --porcelain)" ] || echo "Note: uncommitted changes are NOT included in the archive."
mkdir -p release
git archive --format=zip --prefix=finzoria/ --output="release/finzoria-source-$commit.zip" HEAD
echo "Created release/finzoria-source-$commit.zip"
