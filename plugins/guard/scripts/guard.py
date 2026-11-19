#!/usr/bin/env python3
"""守りの hook の入口（1 つの出来事に 1 つの process）。

  guard.py pre    … PreToolUse（止める見張り）
  guard.py post   … PostToolUse（隣に知らせる見張り）
  guard.py start  … SessionStart（持ち越した問いの出し直し）
  guard.py stop   … Stop（AI の締めを差し戻す見張り・decision=block・上限は各見張りが持つ）
  どの出来事でどの見張りが回るかは、各見張りの file の頭の HOOKS が正本（ここに一覧を写さない）。

止めるのは pre（permissionDecision=deny）と stop（decision=block・AI の締めだけ・上限つき）。post と start は隣に文を出すだけ。
どの見張りも壊れた時は黙って通す（1 つの故障で他の見張りや仕事を止めない）。exit は常に 0。
"""
import importlib
import json
import os
import sys

sys.dont_write_bytecode = True    # 写しの置き場に __pycache__ を作らない（写しの照らしを汚さない）
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import guard_common as G  # noqa: E402

EVENTS = {"pre": "PreToolUse", "post": "PostToolUse", "start": "SessionStart", "stop": "Stop"}
# 止めた時の最後の行（どの見張りの止めにも 1 か所で付ける。中身は細目 §3 が正本＝ここは指すだけ）
ROOT_CAUSE = "直し: 止められた所を直して出し直すだけで済ませず、その形が出た原因を細目 §3「まず構造を疑う」で探して直す"


def _run(module, func, data, vals):
    """1 つの見張りを走らせる。import から呼び出しまでを try の中に置く＝1 つが壊れても他は走る。"""
    try:
        return getattr(importlib.import_module(module), func)(data, vals) or ""
    except Exception as e:      # noqa: BLE001
        sys.stderr.write("[guard] %s.%s: %s\n" % (module, func, e))
        return ""


def watchers(event):
    """この出来事で回す (module, 関数) の並び。同じ dir の各見張りが自分の頭に書く HOOKS = {出来事: 関数} を読む
    （入口に一覧を持たない＝見張りを足す PR が同じ 1 行へ足して互いに衝突しない）。読むのは字の宣言だけで import しない
    （import で壊れる見張りも、ここでは他を巻き込まない）。並びは module の名の順。"""
    out = []
    for path in G.watcher_files(HERE):
        name = os.path.basename(path)[:-3]
        try:
            hooks = G.declared(path).get("HOOKS")
        except Exception as e:           # noqa: BLE001
            sys.stderr.write("[guard] %s の HOOKS が読めない: %s\n" % (name, e))
            continue
        if isinstance(hooks, dict) and isinstance(hooks.get(event), str):
            out.append((name, hooks[event]))
    return out


def fix_doc(name):
    """見張りの直し方の在り処（1 見張り 1 file。止めた文・知らせた文の末に付け、SKILL の表を引かせない）。"""
    return os.path.join(os.path.dirname(HERE), "skills", "guard-rules", "見張り", name + ".md")


def run(event, data):
    """出す JSON（dict）か None。"""
    try:
        vals = G.values(data)
    except Exception:          # noqa: BLE001
        vals = dict(G.DEFAULTS)
    outs = []
    for m, f in watchers(event):
        o = _run(m, f, data, vals)
        if o:
            outs.append("%s\n直し方と値の表の鍵: %s" % (o, fix_doc(m)))
    if not outs:
        return None
    if event == "stop":
        return {"decision": "block", "reason": "\n\n".join(outs + [ROOT_CAUSE])}
    if event == "pre":
        return {"hookSpecificOutput": {"hookEventName": EVENTS[event], "permissionDecision": "deny",
                                       "permissionDecisionReason": "\n\n".join(outs + [ROOT_CAUSE])}}
    return {"hookSpecificOutput": {"hookEventName": EVENTS[event], "additionalContext": "\n\n".join(outs)}}


def main(argv):
    event = argv[1] if len(argv) > 1 else ""
    if event not in EVENTS:
        sys.stderr.write("使い方: guard.py pre|post|start|stop（標準入力に hook の JSON）\n")
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
