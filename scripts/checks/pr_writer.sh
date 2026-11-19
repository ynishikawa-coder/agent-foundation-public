#!/usr/bin/env bash
# PR 本文の `書いた窓:` が先端の commit の `Claude-Session:` の窓と同じかを照らす（本体は plugin checker の plugins/checker/scripts/pr_writer.py）。
# 本文（PR_BODY）が渡れば、CI の PR でも手元でも照らす（照らせる時に照らさない形にしない）。CI の PR では本文・先端
# （PR_HEAD_SHA）・枝（GITHUB_HEAD_REF）を ci.yml の job check が渡す。手元は PR_BODY に本文を渡すと、今の枝と HEAD で照らす。
# 本文が無い所: main への push は「対象外」（PR の本文が無い）、ほかは「照らせない」（CI では赤）。
set -uo pipefail
cd "$(dirname "$0")/../.."
. scripts/af_unchecked.sh
if [ -z "${PR_BODY+x}" ]; then
  if [ "${GITHUB_EVENT_NAME:-}" = "push" ]; then
    af_unchecked 対象外 "main への push に PR の本文が無い（PR の時に照らした）"
  fi
  af_unchecked 照らせない "PR の本文が無い（PR_BODY に本文を渡すと照らす）"
fi
branch="${GITHUB_HEAD_REF:-}"
[ -n "$branch" ] || branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
# 比べる元は出所の今の main（手元に無ければ取って来る。聞けなければ止める＝scripts/pr_shape.py の fresh_main）。
main=$(python3 scripts/pr_shape.py --print-main) || exit 2
# 先端は PR の head（PR_HEAD_SHA か event の head.sha＝scripts/pr_shape.py の pr_head）。HEAD は CI の PR では main と
# 合わせた merge の commit なので代わりに使わない。PR の外（手元）では HEAD が先端。
if [ "${GITHUB_EVENT_NAME:-}" = "pull_request" ]; then
  head=$(python3 scripts/pr_shape.py --print-head) || af_unchecked 照らせない "PR の先端が分からない（PR_HEAD_SHA も event の head.sha も無い）"
else
  head=$(git rev-parse HEAD)
fi
body=$(mktemp)
trap 'rm -f "$body"' EXIT
printf '%s' "${PR_BODY}" > "$body"
python3 plugins/checker/scripts/pr_writer.py --branch "$branch" --head "$head" --base "$main" --body-file "$body"
