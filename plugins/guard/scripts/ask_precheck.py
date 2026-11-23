#!/usr/bin/env python3
"""選択肢の画面（AskUserQuestion）の問いを、出す前に guard と同じ照らしに通し、通る形かを先に返す道具。

意図: 選択肢の画面の問いを、止められてから直すのでなく、初めから通る形で出す。
課題: 問いの形（題の長さ・中の言葉・話題の混ざり・推奨の印・1 つだけ選ばせる問い）は出す時に guard が照らして止める。
AI は止められてから直して出し直すので、同じ問いの往復が出ていた。
原因: 照らしの正本（guard の見張り）は出す時の hook からしか呼べず、出す前に同じ照らしを当てる口が無かった。
解決: guard.py の出来事の入口（run("pre", …)）をそのまま呼ぶ＝見張りの一覧も照らしも写さない。止める物は足さない
（この道具は止めず、照らした結果の文を返すだけ）。
照らさない物: 会話ログを要る見張り（prior_ask の「決定の記録と問いの表を引いた跡」）は、ログの path を渡さないので照らさない
（渡すと止めた回数の印を進めてしまう）。引いた跡は出す時に guard が照らす。

使い方:
  python3 ask_precheck.py [file]   file か標準入力に AskUserQuestion の入力の JSON（{"questions": [...]} か問いの並び）
出口: 通る形なら 0（「通る」と出す）・止まる形なら 2（guard が止める時と同じ訳を出す）・JSON が読めなければ 1。
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard  # noqa: E402  照らしの入口の正本（写さない）

ASK_TOOL = "AskUserQuestion"


def precheck(questions, cwd=None):
    """問いの並びを guard の pre に通す。(通るか, 止める時の訳)。"""
    data = {"hook_event_name": "PreToolUse", "tool_name": ASK_TOOL, "tool_input": {"questions": questions},
            "cwd": cwd or os.getcwd()}
    out = guard.run("pre", data)
    if not out:
        return True, ""
    return False, out["hookSpecificOutput"]["permissionDecisionReason"]


def main(argv):
    try:
        raw = open(argv[1], encoding="utf-8").read() if len(argv) > 1 else sys.stdin.read()
        got = json.loads(raw)
    except (OSError, ValueError) as e:
        sys.stderr.write("問いの JSON を読めない: %s\n" % e)
        return 1
    qs = got.get("questions") if isinstance(got, dict) else got
    if not isinstance(qs, list) or not qs:
        sys.stderr.write("問いが無い（{\"questions\": [...]} か問いの並びを渡す）\n")
        return 1
    ok, why = precheck(qs)
    print("通る" if ok else why)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
