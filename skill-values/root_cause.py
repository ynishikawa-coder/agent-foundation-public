"""止めた・赤の知らせに付ける根治の 1 文の 1 本の口（正本はここ 1 か所・各 plugin の lib/ へ symlink で届く）。

文の形: 「直し: <済ませがちな手>だけで済ませず、意図（<守る物>）とのずれから入り、<何が>原因<（どこ）>を細目 §3「まず構造を疑う」で探して直す」。
道具ごとに違うのは 4 つの欄だけ。文の形を道具ごとに写さず、ここを呼ぶ（写しが戻ると tests/test_root_cause_one_source.py が赤）。
"""
from __future__ import annotations

ENTRY = "細目 §3「まず構造を疑う」"


def root_cause(intent, cause="その形が出た", shortcut="直して出し直す", where=""):
    """根治の 1 文。intent は守る物（括弧の中に入る）、cause は原因の前に付く語（「〜した」）、shortcut は済ませがちな手、where は原因の後の括弧（探す所）。"""
    return "直し: %sだけで済ませず、意図（%s）とのずれから入り、%s原因%sを%sで探して直す" % (shortcut, intent, cause, where, ENTRY)
