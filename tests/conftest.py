"""試験の全体の決まり。

GUARD_STRICT_KEYS: 守りの見張りが値の表に無い鍵を読むと、guard.py を exit 3 にする（窓の中では exit 0 のまま文を stderr に残す）。
試験が hook を回すたびに「読んだ鍵が表に載っているか」を照らす＝表とコードのずれを、試験が通る道の全部で赤にする。
"""
import os

os.environ.setdefault("GUARD_STRICT_KEYS", "1")
