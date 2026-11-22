#!/usr/bin/env bash
# 手元で公開の検査を回す（本体は public-guard/guard.py）。CI では ci.yml の job public-guard が回すので、ここは照らさない。
# guard.py に渡す値（置かない語の表・形の照らしから外す path）は ci.yml の job public-guard の呼び口の with: から
# workflow の読み手（public-guard/workflow_reader.py）で読む（ここに写さない＝ci.yml を直せば手元も CI と揃う）。
# CI の exit 3（照らしていない）の訳「job public-guard が照らす」は、その job に数える呼び口が在る事を同じ読み手で
# 確かめてから言う（無ければ赤＝在ると思い込んで照らしていない物を名指しだけで済ませない）。
# 手元で照らしていない物（顧客の語・PR の題・本文・照らす物 0 など）があると guard.py は exit 3 と照らせない訳（AF_CHECK_UNCHECKED）を返す＝緑に数えない。
set -euo pipefail
cd "$(dirname "$0")/../.."
. scripts/af_unchecked.sh
WORKFLOW=.github/workflows/ci.yml
if ! out="$(python3 public-guard/workflow_reader.py guard-args "$WORKFLOW")"; then
  echo "public_guard: $WORKFLOW の job public-guard の呼び口から guard.py の値を読めない（CI でも照らす job が在ると言えない）"
  echo "直し: 意図（公開の検査の値を ci.yml の 1 か所から読む）とのずれから入り、呼び口が読めない形になった原因を細目 §3「まず構造を疑う」で探して直す（値をここへ写して通すだけで済ませない）"
  exit 1
fi
if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
  af_unchecked 対象外 "CI では job public-guard が照らす（$WORKFLOW のその job に数える呼び口が在る事を読み手で確かめた）"
fi
args=()
while IFS= read -r line; do [ -n "$line" ] && args+=("$line"); done <<< "$out"
exec python3 public-guard/guard.py "${args[@]}"
