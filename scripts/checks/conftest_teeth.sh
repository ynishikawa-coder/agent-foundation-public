#!/usr/bin/env bash
# tests/conftest.py の「飛ばす条件」を、conftest を読まない pytest で照らす。
# 飛ばす条件が壊れて全部を飛ばすと、check_all の pytest は全部 skip のまま緑になり、条件を照らす試験
# （tests/test_real_claude_on_ci.py）自身も同じ conftest に飛ばされる。ここでは --noconftest で回すので、
# 照らす試験は飛ばされず、試験の中で壊れた conftest を小箱に写して回した結果で赤になる。
# 回った試験が 0 本・飛ばした試験が 1 本でもあれば赤（照らしていないのに緑と言わない）。
set -uo pipefail
cd "$(dirname "$0")/../.."
out=$(python3 -m pytest -q --noconftest -p no:cacheprovider -W ignore::pytest.PytestUnknownMarkWarning \
  -rs tests/test_real_claude_on_ci.py 2>&1)
code=$?
printf '%s\n' "$out" | tail -n 15
last=$(printf '%s\n' "$out" | grep -E '[0-9]+ (passed|failed|skipped|error)' | tail -n 1)
if [ $code -ne 0 ]; then
  echo "✗ conftest を読まずに回した飛ばす条件の試験が赤（tests/conftest.py の飛ばす条件が壊れている）"
  exit 1
fi
if ! printf '%s' "$last" | grep -qE '[1-9][0-9]* passed' || printf '%s' "$last" | grep -qE 'skipped|deselected'; then
  echo "✗ 飛ばす条件の試験が回っていない（${last:-結果の行なし}）。照らしていないのに緑と言わない"
  exit 1
fi
echo "conftest_teeth: 緑（${last}）"
