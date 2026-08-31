#!/usr/bin/env bash
# fork-audit.sh -- regenerate the verification record in FORK_AUDIT.md.
#
# FORK_AUDIT.md is a point-in-time claim about a specific commit. A claim that
# cannot be re-derived goes stale silently, so this script re-runs the exact
# verification and prints a record in the same shape, ready to paste.
#
# It reports only what it measured. It does not edit FORK_AUDIT.md, does not
# push, and does not assert anything about live third-party services.
#
# Usage:  bash scripts/fork-audit.sh
set -euo pipefail

UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/Panniantong/Agent-Reach.git}"
UPSTREAM_BRANCH="${UPSTREAM_BRANCH:-main}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

command -v git >/dev/null || { echo "git is required" >&2; exit 1; }
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null || { echo "$PY not found; set PYTHON=" >&2; exit 1; }

echo "==> Upstream source integrity"
if git remote get-url upstream >/dev/null 2>&1; then
    git remote set-url upstream "$UPSTREAM_URL"
else
    git remote add upstream "$UPSTREAM_URL"
fi
git fetch --quiet upstream "$UPSTREAM_BRANCH"
UP="upstream/$UPSTREAM_BRANCH"

BASE="$(git merge-base HEAD "$UP")"
BEHIND="$(git rev-list --count "HEAD..$UP")"

# Keep in sync with .github/workflows/upstream-drift.yml and README Boundaries.
FORK_OWNED='^(README\.md|FORK_AUDIT\.md|CONTRIBUTING\.md|SECURITY\.md|\.github/|scripts/fork-audit\.sh)'
VIOLATIONS="$(git diff --name-only "$BASE..HEAD" | grep -Ev "$FORK_OWNED" || true)"

if [ -n "$VIOLATIONS" ]; then
    INTEGRITY="MODIFIED -- this fork changed upstream-owned files:
$VIOLATIONS"
    echo "    ATTENTION: upstream-owned files differ:"
    echo "$VIOLATIONS" | sed 's/^/      /'
else
    INTEGRITY="Unmodified -- no upstream-owned file differs from the shared base."
    echo "    OK: no upstream-owned file modified."
fi
echo "    Shared base: $(git log -1 --format='%h %s' "$BASE")"
echo "    Behind upstream/$UPSTREAM_BRANCH by $BEHIND commit(s)."

echo "==> Clean virtual environment"
VENV="$(mktemp -d)/venv"
trap 'rm -rf "$(dirname "$VENV")"' EXIT
"$PY" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --quiet --upgrade pip
pip install --quiet -c constraints.txt -e ".[dev]"

echo "==> Test suite"
set +e
PYTEST_OUT="$(pytest -q 2>&1)"
PYTEST_RC=$?
set -e
echo "$PYTEST_OUT" | tail -5
RESULT="$(echo "$PYTEST_OUT" | grep -E '(passed|failed|error)' | tail -1)"

cat <<RECORD

────────────────────────────────────────────────────────────
Record for FORK_AUDIT.md (verify, then paste):
────────────────────────────────────────────────────────────

## Target

- Repository: \`$(git config --get remote.origin.url | sed -E 's#.*github\.com[:/]##; s#\.git$##')\`
- Upstream: \`Panniantong/Agent-Reach\`
- Verified commit: \`$(git rev-parse --short HEAD)\`
- Shared base with upstream: \`$(git rev-parse --short "$BASE")\`
- Behind upstream/$UPSTREAM_BRANCH by: $BEHIND commit(s)
- Upstream source: $INTEGRITY
- Verification date: $(date -u '+%Y-%m-%d') UTC

## Environment

- $(python -V)
- $(uname -s) $(uname -r) $(uname -m)
- Clean isolated virtual environment
- Dependencies installed through \`constraints.txt\`

## Commands

\`\`\`bash
bash scripts/fork-audit.sh
\`\`\`

## Result

\`\`\`text
$RESULT
\`\`\`

This result verifies the repository's automated test suite in the environment
above (pytest exit code $PYTEST_RC). It is not a live integration guarantee for
third-party sites, account sessions, APIs, anti-bot systems, or network
services.
────────────────────────────────────────────────────────────
RECORD

exit "$PYTEST_RC"
