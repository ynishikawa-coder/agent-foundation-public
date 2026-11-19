#!/usr/bin/env bash
# tests/conftest.py の「飛ばす条件」を、conftest を読まない pytest で照らす。
# 飛ばす条件が壊れて全部を飛ばすと、check_all の pytest は全部 skip のまま緑になり、条件を照らす試験
# （tests/test_real_claude_on_ci.py）自身も同じ conftest に飛ばされる。ここでは --noconftest で回すので、
# 照らす試験は飛ばされず、試験の中で壊れた conftest を小箱に写して回した結果で赤になる。
# 回った試験が 0 本・passed の外（飛ばし・xfail・xpass・外し・回らずに終わった）が 1 本でもあれば赤
# （照らしていないのに緑と言わない）。数えるのは pytest の文でなく入口の plugin が書いた構造の結果（af_tally）。
set -uo pipefail
cd "$(dirname "$0")/../.."
tally=$(mktemp) || exit 1
trap 'rm -f "$tally" "$tally.tmp"' EXIT
rm -f "$tally"
out=$(AF_PYTEST_TALLY="$tally" bash scripts/pytest.sh -q --noconftest -p no:cacheprovider \
  -W ignore::pytest.PytestUnknownMarkWarning -rs tests/test_real_claude_on_ci.py 2>&1)
code=$?
printf '%s\n' "$out" | tail -n 15
report=$(python3 scripts/pytest_plugin/af_tally.py judge "$tally" --only-passed)
judge_code=$?
last=$(printf '%s\n' "$report" | tail -n +2 | sed '/^$/d')
if [ $code -ne 0 ]; then
  echo "✗ conftest を読まずに回した飛ばす条件の試験が赤（tests/conftest.py の飛ばす条件が壊れている）"
  echo "直し: 試験を合わせて通すだけで済ませず、飛ばす条件が壊れた原因を細目 §3「まず構造を疑う」で探して直す"
  exit 1
fi
if [ $judge_code -ne 0 ] || [ -n "$last" ] || ! printf '%s' "$report" | grep -qE '^pytest で飛ばした [0-9]+ 本'; then
  echo "✗ 飛ばす条件の試験が回っていない（${last:-${report:-結果なし}}）。照らしていないのに緑と言わない"
  echo "直し: 試験を飛ばす形になった原因を細目 §3「まず構造を疑う」で探して直す"
  exit 1
fi
echo "conftest_teeth: 緑（$(printf '%s\n' "$out" | tail -n 1)）"
