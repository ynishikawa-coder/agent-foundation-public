#!/usr/bin/env bash
# 検査の入口（CI も手元もこの 1 本を呼ぶ）。
# 1. tests/ を pytest で走らせる。
# 2. scripts/checks/*.sh があれば名前の順に走らせる（後の窓はここに 1 本足すだけ）。
# 最後の行: 通れば「check_all: 緑 …」、止まれば「check_all: 赤 …」。
set -uo pipefail
cd "$(dirname "$0")/.."

failed=()
ran=0

echo "== pytest tests/"
ran=$((ran + 1))
if ! python3 -m pytest -q tests/; then
  failed+=("pytest")
fi

if [ -d scripts/checks ]; then
  for f in scripts/checks/*.sh; do
    [ -e "$f" ] || continue
    echo "== $f"
    ran=$((ran + 1))
    if ! bash "$f"; then
      failed+=("$f")
    fi
  done
fi

if [ ${#failed[@]} -eq 0 ]; then
  echo "check_all: 緑 (${ran} 本)"
  exit 0
fi
echo "check_all: 赤 (${#failed[@]}/${ran} 本: ${failed[*]})"
exit 1
