#!/usr/bin/env python3
"""守りの hook の入口（1 つの出来事に 1 つの process）。

  guard.py pre    … PreToolUse:  irreversible（離席中の戻せない操作）＋ paid_upstream（試験から有料の上流）
  guard.py post   … PostToolUse: unanswered の capture（答えの無い問いの台帳）＋ context_size（文脈の量）
  guard.py start  … SessionStart: unanswered の resurface（持ち越した問いの出し直し）

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


def _run(module, func, data, vals):
    """1 つの見張りを走らせる。import から呼び出しまでを try の中に置く＝1 つが壊れても他は走る。"""
    try:
        return getattr(importlib.import_module(module), func)(data, vals) or ""
    except Exception as e:      # noqa: BLE001
        sys.stderr.write("[guard] %s.%s: %s\n" % (module, func, e))
        return ""


WATCHERS = {
    "pre": [("irreversible", "check"), ("paid_upstream", "check")],
    "post": [("unanswered", "capture"), ("context_size", "check")],
    "start": [("unanswered", "resurface")],
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
                                       "permissionDecisionReason": "\n\n".join(outs)}}
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
