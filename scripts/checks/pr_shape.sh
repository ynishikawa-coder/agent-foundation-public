#!/usr/bin/env bash
# PR の差分の形（断片の名・試験の file の末尾への追記）を照らす（本体は scripts/pr_shape.py）。
# 枝の名は CI では GITHUB_HEAD_REF（PR の枝）、手元では今の枝。比べる元は origin/main（無ければ赤で止める）。
# AI の PR かは PR の実物で読む: CI では PR の出来事（GITHUB_EVENT_PATH の本文の書いた窓）、手元では AI の窓の環境（CLAUDECODE）。
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
git rev-parse --verify --quiet origin/main >/dev/null || {
  echo "✗ origin/main が無い（git fetch origin main をしてから回す）"
  exit 2
}
args=(--branch "$branch" --base origin/main)
case "${GITHUB_EVENT_NAME:-}" in
  pull_request*) [ -n "${GITHUB_EVENT_PATH:-}" ] && args+=(--event "$GITHUB_EVENT_PATH") ;;
esac
[ -n "${CLAUDECODE:-}" ] && args+=(--ai)
exec python3 scripts/pr_shape.py "${args[@]}"
