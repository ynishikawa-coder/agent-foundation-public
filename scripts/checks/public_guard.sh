#!/usr/bin/env bash
# 手元で公開の検査を回す（本体は public-guard/guard.py）。CI では ci.yml の job public-guard が回すので、ここは飛ばす。
# guard.py に渡す値（置かない語の表・形の照らしから外す path）は ci.yml の job public-guard の呼び口の with: から
# workflow の読み手（public-guard/workflow_reader.py）で読む（ここに写さない＝ci.yml を直せば手元も CI と揃う）。
# 手元で顧客の語（AF_DENY_WORDS など）が無いと guard.py はその照合を飛ばして exit 3（照らしていない）を返す＝緑に数えない。
set -euo pipefail
cd "$(dirname "$0")/../.."
if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
  echo "public_guard: 照らしていない（CI では job public-guard が照らす）"
  exit 3   # 照らしていない（check_all は緑に数えず名指す）
fi
WORKFLOW=.github/workflows/ci.yml
if ! out="$(python3 public-guard/workflow_reader.py guard-args "$WORKFLOW")"; then
  echo "public_guard: $WORKFLOW の job public-guard の呼び口から guard.py の値を読めない"
  echo "直し: 値をここへ写して通すだけで済ませず、ci.yml の呼び口が読めない形になった原因を細目 §3「まず構造を疑う」で探して直す"
  exit 1
fi
args=()
while IFS= read -r line; do [ -n "$line" ] && args+=("$line"); done <<< "$out"
exec python3 public-guard/guard.py "${args[@]}"
