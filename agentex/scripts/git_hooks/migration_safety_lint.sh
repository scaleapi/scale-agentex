#!/usr/bin/env bash
# Pre-commit wrapper around scripts/ci_tools/migration_lint.py.
#
# pre-commit invokes this with the changed migration files as arguments. We
# pass them through to the linter via --files so authors get fast, file-scoped
# feedback before pushing.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT/agentex"

if [ "$#" -eq 0 ]; then
  exit 0
fi

# Strip the agentex/ prefix so paths resolve relative to the package root
# (matches REPO_ROOT in the linter).
relative_paths=()
for path in "$@"; do
  relative_paths+=("${path#agentex/}")
done

exec python scripts/ci_tools/migration_lint.py --files "${relative_paths[@]}"
