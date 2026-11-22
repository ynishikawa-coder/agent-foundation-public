"""guard: 人が止めた時に Claude Code が書く中断の印の行を、人の新しい頼みと数えないか（注入の試験）。

意図: 頼みの番（prior_ask の上限・人の頼みの頭）を、人が打った行だけで切る。
課題: prior_ask が中断の印の行で番を切り直し、止める上限を数え直していた（原因の台帳の行）。
原因: 人の行の見分け（is_human_row）が、Claude Code が人の行の形で書く中断の印を除いていなかった。
"""
import sys

import pytest

from test_guard import ROOT, deny_reason, env, write_log  # noqa: F401  （env は fixture）
from test_guard_prior_ask import ask_with, lookup_values, owner

sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
import guard_common as G  # noqa: E402

MARKS = ["[Request interrupted by user]", "[Request interrupted by user for tool use]"]


def mark(text, list_form):
    content = [{"type": "text", "text": text}] if list_form else text
    return {"type": "user", "uuid": "i1", "message": {"role": "user", "content": content}}


@pytest.mark.parametrize("list_form", [True, False], ids=["中身が並び", "中身が字"])
@pytest.mark.parametrize("text", MARKS)
def test_中断の印は人の行と数えない(text, list_form):
    row = mark(text, list_form)
    assert G.is_owner_row(row) and not G.is_human_row(row)
    assert G.is_human_row(owner("作り物の頼み [Request interrupted by user]", "u2"))     # 印を含むだけの人の頼みは人の行


def test_prior_ask_中断の印の行で上限を数え直さない(env, tmp_path):
    lookup_values(env, tmp_path)
    tpath = write_log(tmp_path / "p.jsonl", [owner("作り物の頼み", "u1")])
    assert deny_reason(env, ask_with(tpath)) and deny_reason(env, ask_with(tpath))
    tpath = write_log(tmp_path / "p.jsonl", [owner("作り物の頼み", "u1"), mark(MARKS[0], True)])
    assert deny_reason(env, ask_with(tpath)) == ""          # 同じ頼みの 3 回目＝通す（印は新しい頼みでない）
