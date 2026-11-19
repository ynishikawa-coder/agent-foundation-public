#!/usr/bin/env bash
# 手元で公開の検査を回す（本体は public-guard/guard.py）。CI では ci.yml の job public-guard が回すので、ここは飛ばす。
# 手元で顧客の語（AF_DENY_WORDS など）が無いと guard.py はその照合を飛ばして exit 3（照らしていない）を返す＝緑に数えない。
set -euo pipefail
cd "$(dirname "$0")/../.."
if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
  echo "public_guard: 照らしていない（CI では job public-guard が照らす）"
  exit 3   # 照らしていない（check_all は緑に数えず名指す）
fi
exec python3 public-guard/guard.py --deny-words-file tests/data/denylist.txt \
  --pattern-skip public-guard/guard.py tests/test_public_guard.py
