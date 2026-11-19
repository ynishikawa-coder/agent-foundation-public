#!/usr/bin/env bash
# 検査の入口（CI も手元もこの 1 本を呼ぶ）。
# 1. tests/ を pytest で走らせる。
# 2. scripts/checks/*.sh があれば名前の順に走らせる（後の窓はここに 1 本足すだけ）。
# 最後の行: 通れば「check_all: 緑 …」、止まれば「check_all: 赤 … 直し: …」（根治の入口を指す。中身は細目 §3 が正本）。
# どちらも回した先端（@<SHA>）を添え、commit していない変更や git に無い file がある時は「+未 commit」を付ける
# （git ls-files で道具を拾う試験は、git に無い file を見ないので、その結果は先端の結果と言えない）。
set -uo pipefail
cd "$(dirname "$0")/.."

failed=()
ran=0
at="@$(git rev-parse --short=12 HEAD 2>/dev/null || echo 不明)"
[ -n "$(git status --porcelain 2>/dev/null)" ] && at="${at}+未 commit"

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
  echo "check_all: 緑 (${ran} 本) ${at}"
  exit 0
fi
echo "check_all: 赤 (${#failed[@]}/${ran} 本: ${failed[*]}) ${at} 直し: 赤の行を 1 つずつ潰さず、細目 §3「まず構造を疑う」で原因から直す"
exit 1
