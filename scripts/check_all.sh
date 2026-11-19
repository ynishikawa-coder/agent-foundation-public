#!/usr/bin/env bash
# 検査の入口（CI も手元もこの 1 本を呼ぶ）。
# 1. tests/ を pytest で走らせる。飛ばした試験は理由ごとに数えて名指す（緑に数えない）。
# 2. scripts/checks/*.sh があれば名前の順に走らせる（後の窓はここに 1 本足すだけ）。
#    検査の終わり方: 0=緑 / 3=照らしていない（その場では照らせない分岐。緑に数えず名指す）/ ほか=赤。
# 飛ばした試験の扱い:
#   - 理由が「待ち: <path> …」の試験は、<path> が在るのに飛んだら赤（前提が満ちたのに飛ばす条件が残っている）。
#   - CI（GITHUB_ACTIONS=true）では、印 real_claude の試験を -m で外し（job plugin-smoke が回す・外した本数を名指す）、
#     「待ち:」の外の飛ばしは全部赤（CI に要る部品が入っていない。手元では名指すだけ）。
# 最後の行: 通れば「check_all: 緑 …」、止まれば「check_all: 赤 … 直し: …」（根治の入口を指す。中身は細目 §3 が正本）。
# どちらも回した先端（@<SHA>）を添え、commit していない変更や git に無い file がある時は「+未 commit」を付ける
# （git ls-files で道具を拾う試験は、git に無い file を見ないので、その結果は先端の結果と言えない）。
set -uo pipefail
cd "$(dirname "$0")/.."

failed=()
unchecked=()
green=0
ran=0
at="@$(git rev-parse --short=12 HEAD 2>/dev/null || echo 不明)"
[ -n "$(git status --porcelain 2>/dev/null)" ] && at="${at}+未 commit"
log=$(mktemp)
trap 'rm -f "$log"' EXIT

echo "== pytest tests/"
ran=$((ran + 1))
sel=()
[ "${GITHUB_ACTIONS:-}" = "true" ] && sel=(-m "not real_claude")
python3 -m pytest -q -rs "${sel[@]}" tests/ 2>&1 | tee "$log"
pytest_code=${PIPESTATUS[0]}
deselected=$(grep -oE '[0-9]+ deselected' "$log" | tail -n 1 | grep -oE '^[0-9]+')
# 飛ばした試験を理由ごとに数え、赤にする飛ばしを名指す（1 行目＝本数、続く行＝赤にする理由）
skip_report=$(python3 - "$log" <<'PY'
import os, re, sys
from pathlib import Path
ci = os.environ.get("GITHUB_ACTIONS") == "true"
total, bad = 0, []
for ln in Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").splitlines():
    m = re.match(r"SKIPPED \[(\d+)\] (.*?): (.*)$", ln)
    if not m:
        continue
    n, where, why = int(m.group(1)), m.group(2), m.group(3)
    total += n
    w = re.match(r"待ち: ([^\s（(]+)", why)
    if w:
        if Path(w.group(1)).exists():
            bad.append(f"{where}: 待つ物 {w.group(1)} が在るのに飛んだ（飛ばす条件が残っている）")
    elif ci:
        bad.append(f"{where}: CI で飛んだ（{why}）")
print(total)
print("\n".join(bad))
PY
)
skipped=$(printf '%s\n' "$skip_report" | head -n 1)
bad_skips=$(printf '%s\n' "$skip_report" | tail -n +2 | sed '/^$/d')
if [ "$pytest_code" -ne 0 ]; then
  failed+=("pytest")
elif [ -n "$bad_skips" ]; then
  printf '%s\n' "$bad_skips" | sed 's/^/✗ /'
  failed+=("pytest（飛ばした試験）")
else
  green=$((green + 1))
fi

if [ -d scripts/checks ]; then
  for f in scripts/checks/*.sh; do
    [ -e "$f" ] || continue
    echo "== $f"
    ran=$((ran + 1))
    bash "$f"
    code=$?
    if [ $code -eq 0 ]; then
      green=$((green + 1))
    elif [ $code -eq 3 ]; then
      unchecked+=("$(basename "$f")")
    else
      failed+=("$f")
    fi
  done
fi

note="緑 ${green}/${ran} 本"
[ ${#unchecked[@]} -gt 0 ] && note="${note}・照らしていない ${#unchecked[@]} 本: ${unchecked[*]}"
note="${note}・pytest で飛ばした ${skipped:-0} 本"
[ -n "$deselected" ] && note="${note}・印 real_claude で外した ${deselected} 本（job plugin-smoke が回す）"
if [ ${#failed[@]} -eq 0 ]; then
  echo "check_all: 緑 (${note}) ${at}"
  exit 0
fi
echo "check_all: 赤 (落ちた ${#failed[@]} 本: ${failed[*]}・${note}) ${at} 直し: 赤の行を 1 つずつ潰さず、細目 §3「まず構造を疑う」で原因から直す"
exit 1
