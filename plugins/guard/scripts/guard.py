#!/usr/bin/env python3
"""守りの hook の入口（1 つの出来事に 1 つの process）。

  guard.py pre    … PreToolUse（止める見張り）
  guard.py post   … PostToolUse（隣に知らせる見張り）
  guard.py start  … SessionStart（持ち越した問いの出し直し）
  どの出来事でどの見張りが回るかは、各見張りの file の頭の HOOKS が正本（ここに一覧を写さない）。

止めるのは pre（permissionDecision=deny）だけ。post と start は隣に文を出すだけ。AI の締め（Stop）を差し戻す口は持たない
（差し戻すと同じ返事を書き直させる無駄になる＝形の崩れは知らせるだけ）。
見張りが壊れた時（import・呼び出しの例外・HOOKS の宣言が読めない）と、入力の JSON が読めない時は、pre では止める
（守りが働いたかを判らないまま通さない＝既定で止める）。止めの文に壊れた見張りの名と訳を載せる。1 つの故障で他の見張りは
止めない（他も全部走らせてから、壊れた分を止めの訳に足す）。post と start は通す側の出来事なので、壊れた見張りの名を隣に知らせる
だけ。exit は常に 0（止めは JSON の permissionDecision で出す）。
"""
import ast
import glob
import importlib
import json
import os
import sys

sys.dont_write_bytecode = True    # 写しの置き場に __pycache__ を作らない（写しの照らしを汚さない）
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import guard_common as G  # noqa: E402  （lib/ を道に足す）

EVENTS = {"pre": "PreToolUse", "post": "PostToolUse", "start": "SessionStart"}
# 止めた時の最後の行（どの見張りの止めにも 1 か所で付ける。中身は細目「直すは根治」が正本＝ここは指すだけ）
def root_cause_line():
    """根治の 1 文の 1 本の口＝lib/root_cause.py の root_cause（正本へ戻る symlink・止める・知らせる時だけ読む＝写した見張りの照らしは読まずに動く）"""
    from root_cause import root_cause
    return root_cause("止めた守りが守る物", shortcut="止められた所を直して出し直す")


def _broken(name, why):
    return "[guard] 見張り %s が壊れていて、この呼び出しを照らせていない（%s）。照らせないまま通さない。" \
           "直し: 土台の plugins/guard/scripts/%s.py を直す（土台の main が進んでいれば窓を立て直すと入る）。" % (name, why, name)


def _run(module, func, data, vals):
    """1 つの見張りを走らせる。import から呼び出しまでを try の中に置く＝1 つが壊れても他は走る。
    (出す文, 壊れた訳) を返す。"""
    try:
        return getattr(importlib.import_module(module), func)(data, vals) or "", ""
    except Exception as e:      # noqa: BLE001
        sys.stderr.write("[guard] %s.%s: %s\n" % (module, func, e))
        return "", _broken(module, "%s.%s: %s: %s" % (module, func, type(e).__name__, e))


def watchers(event, broken=None):
    """この出来事で回す (module, 関数) の並び。同じ dir の各見張りが自分の頭に書く HOOKS = {出来事: 関数} を読む
    （入口に一覧を持たない＝見張りを足す PR が同じ 1 行へ足して互いに衝突しない）。読むのは字の宣言だけで import しない
    （import で壊れる見張りも、ここでは他を巻き込まない）。並びは module の名の順。"""
    out = []
    for path in sorted(glob.glob(os.path.join(HERE, "*.py"))):
        name = os.path.basename(path)[:-3]
        if name in ("guard", "guard_common"):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            hooks = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                         and any(isinstance(t, ast.Name) and t.id == "HOOKS" for t in n.targets))
        except StopIteration:
            continue                     # 宣言の無い file は見張りでない（手伝いの部品）
        except Exception as e:           # noqa: BLE001
            sys.stderr.write("[guard] %s の HOOKS が読めない: %s\n" % (name, e))
            if broken is not None:     # どの出来事の見張りかを判らない＝どの出来事でも壊れた見張りとして名指す
                broken.append(_broken(name, "HOOKS の宣言が読めない: %s: %s" % (type(e).__name__, e)))
            continue
        if isinstance(hooks, dict) and isinstance(hooks.get(event), str):
            out.append((name, hooks[event]))
    return out


def run(event, data):
    """出す JSON（dict）か None。"""
    try:
        vals = G.values(data)
    except Exception:          # noqa: BLE001
        vals = dict(G.DEFAULTS)
    broken = []
    outs = []
    for m, f in watchers(event, broken):
        o, b = _run(m, f, data, vals)
        if o:
            outs.append(o)
        if b:
            broken.append(b)
    outs += broken
    if not outs:
        return None
    if event == "pre":
        return {"hookSpecificOutput": {"hookEventName": EVENTS[event], "permissionDecision": "deny",
                                       "permissionDecisionReason": "\n\n".join(outs + [root_cause_line()])}}
    return {"hookSpecificOutput": {"hookEventName": EVENTS[event], "additionalContext": "\n\n".join(outs)}}


def main(argv):
    event = argv[1] if len(argv) > 1 else ""
    if event not in EVENTS:
        sys.stderr.write("使い方: guard.py pre|post|start（標準入力に hook の JSON）\n")
        return 0
    try:
        data = json.load(sys.stdin)
        why = "" if isinstance(data, dict) else "頂が {…} でない"
    except Exception as e:     # noqa: BLE001
        data, why = None, "%s: %s" % (type(e).__name__, e)
    if why:
        if event != "pre":
            return 0
        out = {"hookSpecificOutput": {"hookEventName": EVENTS[event], "permissionDecision": "deny",
                                      "permissionDecisionReason": "[guard] hook の入力の JSON を読めない（%s）。照らせないまま通さない。"
                                      % why}}
    else:
        out = run(event, data)
    if out:
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
