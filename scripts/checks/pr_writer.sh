#!/usr/bin/env bash
# PR 本文の `書いた窓:` が先端の commit の `Claude-Session:` の窓と同じかを照らす（本体は plugin checker の plugins/checker/scripts/pr_writer.py）。
# CI の PR では本文（PR_BODY）・先端（PR_HEAD_SHA）・枝（GITHUB_HEAD_REF）を ci.yml の job check が渡す。
# 本文が無い所（手元・main への push）では照らさず、照らしていない事を出す。
set -uo pipefail
cd "$(dirname "$0")/../.."
branch="${GITHUB_HEAD_REF:-}"
if [ "${GITHUB_EVENT_NAME:-}" != "pull_request" ]; then
  echo "pr_writer: 照らしていない（PR の外＝本文が無い。CI の PR で照らす）"
  exit 3   # 照らしていない（check_all は緑に数えず名指す）
fi
# 比べる元は出所の今の main（手元の origin/main が古ければ取り直す。聞けなければ止める＝scripts/pr_shape.py の fresh_main）。
main=$(python3 scripts/pr_shape.py --print-main) || exit 2
body=$(mktemp)
trap 'rm -f "$body"' EXIT
printf '%s' "${PR_BODY:-}" > "$body"
exec python3 plugins/checker/scripts/pr_writer.py --branch "$branch" --head "${PR_HEAD_SHA:-HEAD}" --base "$main" --body-file "$body"
