#!/usr/bin/env python3
"""窓の題 `<種類><状態> <作業名>` を、題の印の表（session_watch.py の TITLE_TABLE）から組んで出す道具。

意図: 窓の題を、止められてから直すのでなく、初めから通る形で付ける。
課題: 題は付けた後に guard（題を付ける口）と Stop の見張りが title_shape で照らし、崩れていれば止める・知らせる。
AI は表を思い出して手で組むので、表に無い組み合わせ（例 ✋💤）・印の後の空白抜け・古い形を出して止められ、直して出し直す往復が出ていた。
原因: 表の正本（TITLE_TABLE）を照らす口はあっても、表から正しい題を組んで渡す口が無かった（正しい道が無いまま、外れを後で拒むだけ）。
解決: 表を写さず session_watch を import し、種類・状態・作業名から題を組み、組んだ題を同じ title_shape に通してから出す。
表に無い組み合わせは組まず、その種類に付けてよい状態を表から並べて返す（止める物は足さない。出すのは文だけ）。

使い方:
  python3 title_build.py <種類> <状態> <作業名…>
    種類: 🙋 ✋ 🤖 か human hand ai
    状態: 無し（動いている）❓ 💤 🛑 ✅ か moving asking waiting stopped done
  python3 title_build.py --table   題の印の表を出す
出口: 組めたら 0（標準出力に題 1 行）・組めなければ 2（標準エラーに訳と付けてよい状態）・使い方の誤りは 1。
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session_watch as SW  # noqa: E402  表の正本（写さない）

# 打ちやすい別名（表の中身でなく、表の印への引き当てだけを持つ）。
KIND_ALIASES = {"human": SW.HUMAN, "hand": SW.HAND, "ai": SW.AI}
STATE_ALIASES = {"moving": SW.MOVING, "無し": SW.MOVING, "なし": SW.MOVING, "-": SW.MOVING,
                 "asking": SW.ASKING, "waiting": SW.WAITING, "stopped": SW.STOPPED, "done": SW.DONE}
ROOT_CAUSE = "直し: 表に在る印で組み直すだけで済ませず、なぜ表に無い題を組もうとしたかを細目「まず構造を疑う」で探す"
STATE_ALIASES.update({w: s for s, w in SW.CARD_WORDS.items()})   # 返事の札の言葉（終わった・答えて・待ち・止まった）


def _kind(word):
    w = str(word or "").strip().rstrip(SW.VS16)
    return w if w in SW.KINDS else KIND_ALIASES.get(w.lower())


def _state(word):
    w = str(word or "").strip().rstrip(SW.VS16)
    if w in SW.STATES:
        return w
    return STATE_ALIASES.get(w.lower(), STATE_ALIASES.get(w))


def build(kind, state, name):
    """(題, 問題の並び)。問題が在れば題は None。"""
    k, s, n = _kind(kind), _state(state), " ".join(str(name or "").split())
    probs = []
    if k is None:
        probs.append("種類「%s」は表に無い（種類は %s）" % (kind, "・".join("%s＝%s" % (x, SW.KIND_NAMES[x]) for x in SW.KINDS)))
    if s is None:
        probs.append("状態「%s」は表に無い（状態は %s）" % (state, "・".join(
            "%s＝%s" % ("無し" if x == SW.MOVING else x, SW.STATE_NAMES[x]) for x in (SW.MOVING,) + SW.STATES)))
    if not n:
        probs.append("作業名が無い")
    if probs:
        return None, probs
    if s not in SW.TITLE_TABLE[k]:
        ok = "・".join(("無し" if x == SW.MOVING else x) for x in SW.TITLE_TABLE[k])
        return None, ["%s（%s）に付けてよい状態は %s" % (k, SW.KIND_NAMES[k], ok)]
    title = "%s%s %s" % (k, s, n)
    shape = SW.title_shape(title)      # 照らしの正本を同じく通す（組み方の誤りも出さない）
    return (None, shape) if shape else (title, [])


def main(argv):
    if len(argv) == 2 and argv[1] == "--table":
        print(SW.table_doc())
        return 0
    if len(argv) < 4:
        sys.stderr.write(__doc__.split("使い方:", 1)[1])
        return 1
    title, probs = build(argv[1], argv[2], " ".join(argv[3:]))
    if title is None:
        sys.stderr.write("題を組めない:\n" + "".join("- %s\n" % p for p in probs) + ROOT_CAUSE + "\n")
        return 2
    print(title)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
