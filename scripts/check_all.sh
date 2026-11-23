#!/usr/bin/env bash
# 検査の入口（CI も手元もこの 1 本を呼ぶ）。
# 1. tests/ を pytest で回す（CI では本物の claude を要る試験を外す。それは job plugin-smoke が回す）。
# 2. scripts/checks/*.sh を名前の順に回す（終わり方 0 が緑・ほかは赤）。
set -uo pipefail
cd "$(dirname "$0")/.."

failed=()
sel=()
[ "${GITHUB_ACTIONS:-}" = "true" ] && sel=(-m "not real_claude")
echo "== pytest tests/"
python3 -m pytest -q -rs "${sel[@]}" tests/ || failed+=("pytest")
for f in scripts/checks/*.sh; do
  [ -e "$f" ] || continue
  echo "== $f"
  bash "$f" || failed+=("$f")
done
if [ ${#failed[@]} -eq 0 ]; then
  echo "check_all: 緑"
  exit 0
fi
echo "check_all: 赤 (${failed[*]})"
exit 1
