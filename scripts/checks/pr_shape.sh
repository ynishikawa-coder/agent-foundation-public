#!/usr/bin/env bash
# PR の差分の形（断片の名・試験の file の末尾への追記）を照らす（本体は scripts/pr_shape.py）。
# 枝の名は CI では GITHUB_HEAD_REF（PR の枝）、手元では今の枝。比べる元は出所の今の main（手元の origin/main が
# 古ければ取り直す。聞けない・揃わなければ赤で止める＝scripts/pr_shape.py の fresh_main）。
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
main=$(python3 scripts/pr_shape.py --print-main) || exit 2
exec python3 scripts/pr_shape.py --branch "$branch" --base "$main"
