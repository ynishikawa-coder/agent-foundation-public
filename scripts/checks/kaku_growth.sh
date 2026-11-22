#!/usr/bin/env bash
# 増やさない物（核・振る舞いの既定・形の細目）が main との分かれ目より増えていないかを照らす（本体は plugins/core/scripts/kaku.py grow）。
# 比べる元は出所の今の main（手元の origin/main が古ければ取り直す＝scripts/pr_shape.py の fresh_main）。聞けない・
# 揃わない・分かれ目が無ければ黙って緑にせず赤で止める。CI は ci.yml の check で全部の歴史を取ってから呼ぶ。
# 先端が main そのもの（main への push・手元の main）だと分かれ目が先端自身で、何と比べても増えない＝必ず緑になる。
# その時は先端の 1 つ前（first parent＝この commit が入る前の main）と比べ、入った変更が増やしていないかを照らす。
set -uo pipefail
cd "$(dirname "$0")/../.."
main=$(python3 scripts/pr_shape.py --print-main) || exit 2
base=$(git merge-base HEAD "$main" 2>/dev/null) || {
  echo "✗ 出所の main ${main:0:12} との分かれ目が取れない（浅い clone なら git fetch --unshallow をしてから回す）"
  exit 2
}
if [ "$base" = "$(git rev-parse HEAD)" ]; then
  base=$(git rev-parse -q --verify 'HEAD^1') || {
    echo "✗ 先端が main と同じで、1 つ前の commit が無い（比べる物が無い）"
    exit 2
  }
  echo "（先端が main と同じ＝先端の 1 つ前 ${base:0:12} と比べる）"
fi
exec python3 plugins/core/scripts/kaku.py grow --base "$base"
