#!/usr/bin/env bash
# 検査の入口（CI も手元もこの 1 本を呼ぶ）。
# 1. tests/ を入口 scripts/pytest.sh で走らせ、入口の plugin が書いた構造の結果（af_tally）だけを数える。
#    飛ばした・xfail の試験は数えて名指す（緑に数えない）。xpass・回らずに終わった試験・通った 0 本・知らない plugin・
#    結果を変える conftest の hook・書いたのに集めていない試験は赤。
# 2. scripts/checks/*.sh を名前の順に走らせる（後の窓はここに 1 本足すだけ）。scripts/checks に *.sh の外の物
#    （.py・下の dir など＝ここが回さない物）を置くと赤（置いた検査が黙って回らない形にしない）。
#    検査の終わり方: 0=緑 / 3=照らしていない / ほか=赤。3 は終わり方だけでは数えない: 検査が AF_CHECK_UNCHECKED の
#    file に「対象外: 訳」か「照らせない: 訳」の 1 行を書いて 3 で終わった時だけ（scripts/af_unchecked.sh の af_unchecked・python の道具は AF_CHECK_UNCHECKED へ同じ形で書く）。
#    書かずに 3（exec した道具が別の訳で 3 を返した）・書いたのに 0 は赤。
#    CI では「照らせない」も赤（CI は照らす物が揃う所）。「対象外」（main への push に PR の本文が無い等）は名指すだけ。
# 飛ばした試験の扱い:
#   - 待つ物の飛ばしは tests/waits.py の wait_for だけが出す（条件と理由が同じ 1 つの path から出る）。その path が
#     待つ物の表 tests/waits.txt に無い・表の試験の file の外から待った・在るのに飛んだら赤。理由の文の「待ち:」の字は読まない。
#   - CI（GITHUB_ACTIONS=true）では、印 real_claude の試験を -m で外し（job plugin-smoke が回す・外した本数を印で数える）、
#     待つ物の外の飛ばし・xfail は全部赤（CI に要る部品が入っていない。手元では名指すだけ）。印の無い試験を外すと赤。
# 最後の行: 通れば「check_all: 緑 …」、止まれば「check_all: 赤 … 直し: …」（根治の入口を指す。中身は細目 §3 が正本）。
# どちらも回した場（CI か手元か。手元は CI と数え方が違う所を名指す）と回した先端（@<SHA>）を添え、commit していない
# 変更や git に無い file がある時は「+未 commit」を付ける
# （git ls-files で道具を拾う試験は、git に無い file を見ないので、その結果は先端の結果と言えない）。
set -uo pipefail
cd "$(dirname "$0")/.."

failed=()
unchecked=()
outside=()
green=0
ci=0
[ "${GITHUB_ACTIONS:-}" = "true" ] && ci=1
ran=0
# 回した先端は PR の先端（CI の PR では event の head.sha＝scripts/pr_shape.py の pr_head）。CI の PR の HEAD は main と
# 合わせた merge の commit なので、その時はそれも添える（PR の先端と照らす人に食い違って見せない）。
here=$(git rev-parse --short=12 HEAD 2>/dev/null || echo 不明)
if [ "${GITHUB_EVENT_NAME:-}" = "pull_request" ] && head=$(python3 scripts/pr_shape.py --print-head 2>/dev/null); then
  at="@${head:0:12}（PR の先端・回したのは main と合わせた ${here}）"
else
  at="@${here}"
fi
[ -n "$(git status --porcelain 2>/dev/null)" ] && at="${at}+未 commit"
tally=$(mktemp) || { echo "check_all: 赤 (試験の結果の置き場を作れない) ${at}"; exit 1; }
trap 'rm -f "$tally" "$tally.tmp"' EXIT
rm -f "$tally"   # 前の中身を残さない（pytest が書かなければ数える段が止まって赤）

echo "== pytest tests/"
ran=$((ran + 1))
sel=()
[ $ci -eq 1 ] && sel=(-m "not real_claude")
AF_PYTEST_TALLY="$tally" bash scripts/pytest.sh -q -rs "${sel[@]}" tests/
pytest_code=$?
# 数えるのは pytest の文でなく、入口の plugin が書いた構造の結果だけ（scripts/pytest_plugin/af_tally.py）。
# 1 行目＝数えた値、続く行＝緑に数えない物。数える段が止まれば（結果が無い・壊れた）赤。
report=$(python3 scripts/pytest_plugin/af_tally.py judge "$tally")
judge_code=$?
summary=$(printf '%s\n' "$report" | head -n 1)
bad=$(printf '%s\n' "$report" | sed -n 's/^赤: //p')
named=$(printf '%s\n' "$report" | sed -n 's/^名指し: //p')
[ -n "$named" ] && printf '%s\n' "$named" | sed 's/^/・/'
nskip=$(printf '%s' "$summary" | sed -nE 's/^pytest で飛ばした ([0-9]+) 本.*/\1/p')
# 判定は 1 行目を必ず「pytest で飛ばした N 本」で始める。終わり方が 0 でも 1 行目が無ければ数えていない（赤）。
if [ "$judge_code" -ne 0 ] || ! printf '%s' "$summary" | grep -qE '^pytest で飛ばした [0-9]+ 本'; then
  printf '%s\n' "${report:-数える段が何も出さずに終わった}" | sed 's/^/✗ /'
  failed+=("pytest（数える段が止まった）")
  summary="pytest の結果を数えていない"
elif [ "$pytest_code" -ne 0 ]; then
  failed+=("pytest")
elif [ -n "$bad" ]; then
  printf '%s\n' "$bad" | sed 's/^/✗ /'
  failed+=("pytest（緑に数えない試験）")
else
  green=$((green + 1))
fi

# scripts/checks に置いた物はどれもここが回す形（1 段の *.sh）でなければ赤（置いたのに黙って回らない検査を作らない）。
if [ -d scripts/checks ]; then
  while IFS= read -r -d '' x; do
    case "$x" in
      scripts/checks/*/*) failed+=("${x}（scripts/checks の下の dir の物は回らない）") ;;
      scripts/checks/*.sh) [ -f "$x" ] || failed+=("${x}（file でない）") ;;
      *) failed+=("${x}（*.sh の外は回らない。検査は scripts/checks/<名>.sh に置く）") ;;
    esac
  done < <(find scripts/checks -mindepth 1 \( -name __pycache__ -prune -o -print0 \) | sort -z)
  for f in scripts/checks/*.sh; do
    [ -e "$f" ] || continue
    echo "== $f"
    ran=$((ran + 1))
    why=$(mktemp) || { failed+=("$f（照らしていない訳の置き場を作れない）"); continue; }
    AF_CHECK_UNCHECKED="$why" bash "$f"
    code=$?
    said=$(head -n 1 "$why")
    rm -f "$why"
    if [ $code -eq 0 ] && [ -z "$said" ]; then
      green=$((green + 1))
    elif [ $code -eq 0 ]; then
      echo "✗ 緑で終わったのに照らしていない訳を書いた（${said}）"
      failed+=("$f（緑と照らしていないを両方言った）")
    elif [ $code -eq 3 ] && [[ "$said" == 対象外:* ]]; then
      outside+=("$(basename "$f")（${said#対象外: }）")
    elif [ $code -eq 3 ] && [[ "$said" == 照らせない:* ]]; then
      if [ $ci -eq 1 ]; then
        echo "✗ CI で照らせない（${said#照らせない: }）"
        failed+=("$f（CI で照らせない）")
      else
        unchecked+=("$(basename "$f")")
      fi
    elif [ $code -eq 3 ]; then
      echo "✗ 終わり方 3 なのに照らしていない訳（AF_CHECK_UNCHECKED の「対象外:」か「照らせない:」の行）が無い"
      failed+=("$f（訳の無い終わり方 3）")
    else
      failed+=("$f")
    fi
  done
fi

note="緑 ${green}/${ran} 本"
[ ${#unchecked[@]} -gt 0 ] && note="${note}・照らしていない ${#unchecked[@]} 本: ${unchecked[*]}"
[ ${#outside[@]} -gt 0 ] && note="${note}・対象外 ${#outside[@]} 本: ${outside[*]}"
note="${note}・${summary}"
# 回した場。手元は CI と数え方が違う（印 real_claude は claude が無ければ飛ぶ・待つ物の外の飛ばしと xfail は赤にせず名指す・
# 照らせない検査を赤にしない）ので、手元の緑を CI の緑と同じに読ませない。
if [ $ci -eq 1 ]; then
  note="場 CI・${note}"
else
  note="場 手元（CI と違い、飛ばし ${nskip:-?} 本と照らしていない ${#unchecked[@]} 本を赤にしていない）・${note}"
fi
if [ ${#failed[@]} -eq 0 ]; then
  echo "check_all: 緑 (${note}) ${at}"
  exit 0
fi
echo "check_all: 赤 (落ちた ${#failed[@]} 本: ${failed[*]}・${note}) ${at} 直し: 赤の行を 1 つずつ潰さず、落ちた検査の意図とのずれから入り、細目 §3「まず構造を疑う」で原因を探して直す"
exit 1
