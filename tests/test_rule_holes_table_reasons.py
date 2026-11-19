"""守らない文の表（tests/data/試験で守らない文.txt）の行は、全部が決まった訳を持つ（訳の無い穴を置かない）。"""
import sys

from test_rule_holes import (ROOT, _open_real, _回す, _試験, _決まりの試験, 穴, 表, 形の行, 訳)

def test_守らない文の表の行は全部_決まった訳を持ち_形の訳は形の行だけ():
    bad = [f"{r}\t{s}\t{w}" for (r, s), w in sorted(表().items())
           if w not in 訳 or (w == "形") != bool(形の行.match(s))]
    assert not bad, "訳が無い・知らない訳・形の訳と行の形が合わない行（訳は " + "／".join(訳) + "）:\n" + "\n".join(bad)
