#!/usr/bin/env bash
# scripts/checks の検査が source する小さな道具（scripts/checks の外に置く＝check_all はこれを検査として回さない）。
# af_unchecked <対象外|照らせない> <訳>: 照らしていない訳を check_all へ渡して終わり方 3 で終える。
#   check_all は終わり方 3 をこの訳の行が在る時だけ「照らしていない」に数える（訳なしの 3 は赤）。
#   対象外＝その場に照らす物が無い（main への push に PR の本文が無い等）。照らせない＝照らす物は在るのに道具・値が無い（CI では赤）。
af_unchecked() {
  local kind="$1"
  shift
  echo "$(basename "$0" .sh): 照らしていない（${kind}: $*）"
  [ -n "${AF_CHECK_UNCHECKED:-}" ] && printf '%s: %s\n' "$kind" "$*" > "$AF_CHECK_UNCHECKED"
  exit 3
}
