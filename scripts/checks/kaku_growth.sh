#!/usr/bin/env bash
# 増やさない物（核・振る舞いの既定・形の細目）が main との分かれ目より増えていないかを照らす（本体は plugins/core/scripts/kaku.py grow）。
# 比べる元は出所の今の main（手元の origin/main が古ければ取り直す＝scripts/pr_shape.py の fresh_main）。聞けない・
# 揃わない・分かれ目が無ければ黙って緑にせず赤で止める。CI は ci.yml の check で全部の歴史を取ってから呼ぶ。
set -uo pipefail
cd "$(dirname "$0")/../.."
main=$(python3 scripts/pr_shape.py --print-main) || exit 2
base=$(git merge-base HEAD "$main" 2>/dev/null) || {
  echo "✗ 出所の main ${main:0:12} との分かれ目が取れない（浅い clone なら git fetch --unshallow をしてから回す）"
  exit 2
}
exec python3 plugins/core/scripts/kaku.py grow --base "$base"
