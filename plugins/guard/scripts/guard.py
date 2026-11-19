#!/usr/bin/env python3
"""守りの hook の入口（1 つの出来事に 1 つの process）。

  guard.py pre    … PreToolUse:  irreversible（離席中の戻せない操作）＋ paid_upstream（試験から有料の上流）
                                ＋ qa_page（問いのページを Artifact で出す前の qa-html の検査）
                                ＋ ask_shape（選択肢の画面の問いの形: 題の長さ・中の言葉・話題の混ざり・推奨の印の付け方）
                                ＋ pick_one（選択肢の画面で作業・論点・原因を 1 つだけ選ばせる問い）
                                ＋ values_keys（値の表に土台が読まない鍵を残す書き込み）
  guard.py post   … PostToolUse: unanswered の capture（答えの無い問いの台帳）＋ context_size（文脈の量）
                                ＋ ask_shape の notice（推奨の印が済んだか・意図の問いに付いた知らせ）
  guard.py start  … SessionStart: unanswered の resurface（持ち越した問いの出し直し）＋ values_keys（値の表の知らない鍵の知らせ）

止めるのは pre だけ（permissionDecision=deny）。post と start は隣に文を出すだけ。
どの見張りも壊れた時は黙って通す（1 つの故障で他の見張りや仕事を止めない）。exit は常に 0。
"""
import importlib
import json
import os
import sys

sys.dont_write_bytecode = True    # 写しの置き場に __pycache__ を作らない（写しの照らしを汚さない）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import guard_common as G  # noqa: E402

EVENTS = {"pre": "PreToolUse", "post": "PostToolUse", "start": "SessionStart"}
# 止めた時の最後の行（どの見張りの止めにも 1 か所で付ける。中身は細目 §3 が正本＝ここは指すだけ）
ROOT_CAUSE = "直し: 止められた所を直して出し直すだけで済ませず、その形が出た原因を細目 §3「まず構造を疑う」で探して直す"


def _run(module, func, data, vals):
    """1 つの見張りを走らせる。import から呼び出しまでを try の中に置く＝1 つが壊れても他は走る。"""
    try:
        return getattr(importlib.import_module(module), func)(data, vals) or ""
    except Exception as e:      # noqa: BLE001
        sys.stderr.write("[guard] %s.%s: %s\n" % (module, func, e))
        return ""


WATCHERS = {
    "pre": [("irreversible", "check"), ("paid_upstream", "check"), ("qa_page", "check"), ("ask_shape", "check"), ("pick_one", "check"), ("values_keys", "check")],
    "post": [("unanswered", "capture"), ("context_size", "check"), ("ask_shape", "notice")],
    "start": [("unanswered", "resurface"), ("values_keys", "resurface")],
}


def run(event, data):
    """出す JSON（dict）か None。"""
    try:
        vals = G.values(data)
    except Exception:          # noqa: BLE001
        vals = dict(G.DEFAULTS)
    outs = [o for o in (_run(m, f, data, vals) for m, f in WATCHERS[event]) if o]
    if not outs:
        return None
    if event == "pre":
        return {"hookSpecificOutput": {"hookEventName": EVENTS[event], "permissionDecision": "deny",
                                       "permissionDecisionReason": "\n\n".join(outs + [ROOT_CAUSE])}}
    return {"hookSpecificOutput": {"hookEventName": EVENTS[event], "additionalContext": "\n\n".join(outs)}}


def main(argv):
    event = argv[1] if len(argv) > 1 else ""
    if event not in EVENTS:
        sys.stderr.write("使い方: guard.py pre|post|start（標準入力に hook の JSON）\n")
        return 0
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0
    out = run(event, data)
    if out:
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
