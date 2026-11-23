#!/usr/bin/env bash
# 手元で公開の検査を回す（本体は public-guard/guard.py）。CI では ci.yml の job public-guard が回すので、ここは回さない。
# guard.py に渡す値は ci.yml の job public-guard の with: から読む（ここに写さない）。
set -euo pipefail
cd "$(dirname "$0")/../.."
[ "${GITHUB_ACTIONS:-}" = "true" ] && exit 0
out="$(python3 public-guard/workflow_reader.py guard-args .github/workflows/ci.yml)"
args=()
while IFS= read -r line; do [ -n "$line" ] && args+=("$line"); done <<< "$out"
exec python3 public-guard/guard.py "${args[@]}"
