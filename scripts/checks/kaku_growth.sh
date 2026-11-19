#!/usr/bin/env bash
# 増やさない物（核・振る舞いの既定・形の細目）が main との分かれ目より増えていないかを照らす（本体は plugins/core/scripts/kaku.py grow）。
# 比べる元（origin/main）が無ければ黙って緑にせず赤で止める。CI は ci.yml の check で全部の歴史を取ってから呼ぶ。
set -uo pipefail
cd "$(dirname "$0")/../.."
base=$(git merge-base HEAD origin/main 2>/dev/null) || {
  echo "✗ origin/main との分かれ目が取れない（git fetch origin main をしてから回す）"
  exit 2
}
exec python3 plugins/core/scripts/kaku.py grow --base "$base"
