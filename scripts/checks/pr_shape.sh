#!/usr/bin/env bash
# PR の差分の形（断片の名・試験の file の末尾への追記）を照らす（本体は scripts/pr_shape.py）。
# 枝の名は CI では GITHUB_HEAD_REF（PR の枝）、手元では今の枝。比べる元は PR の基点の枝（CI では GITHUB_BASE_REF・手元では
# PR_BASE・どちらも無ければ main）の origin の物（無ければ赤で止める）。積んだ PR（基点が別の PR の枝）は基点の差分を自分の物と数えない。
set -uo pipefail
cd "$(dirname "$0")/../.."
branch="${GITHUB_HEAD_REF:-}"
if [ -z "$branch" ]; then
  if [ "${GITHUB_EVENT_NAME:-}" = "push" ]; then
    branch="main"
  else
    branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo HEAD)
  fi
fi
base="origin/${GITHUB_BASE_REF:-${PR_BASE:-main}}"
git rev-parse --verify --quiet "$base" >/dev/null || {
  echo "✗ $base が無い（git fetch origin をしてから回す）"
  exit 2
}
exec python3 scripts/pr_shape.py --branch "$branch" --base "$base"
