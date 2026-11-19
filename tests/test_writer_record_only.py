"""書いた窓は commit の記録だけ（PR 本文の `書いた窓:` の写しを畳んだ）を守りの hook の側で照らす注入の試験。

前の形: 守りの hook は判定の材料の書いた窓の組に本文の `書いた窓:` を足した（本文を直さないと記録と食い違う写しが残った）。
今の形: 本文は読まない。使う側の古い本文の頭の `書いた窓:` は壊れる 2 段の 1 段目の間だけ通す。
"""
import json
from pathlib import Path

from test_pr_text import REVIEWER, STRANGER, WRITER, _fake_gh, cleanup_body, deny_reason, env, gh  # noqa: F401
from test_pr_text import verdict_comment

ROOT = Path(__file__).resolve().parent.parent


def _tail():
    return cleanup_body().split("\n\n", 1)[1]


def test_注入_本文の書いた窓の写しは書いた窓の組に足さない(env):
    """写しを畳んだ: 本文の `書いた窓:` は読まない。本文が出す窓を書いた窓と名乗っても、記録（commit）に無ければ組に入らない
    （前の形: 本文の写しを組に足した＝本文を直さないと記録と食い違い、写しを持つ理由が残った）。"""
    p = gh("add_issue_comment", issue_number=1, body=verdict_comment())
    _fake_gh(env, writer=REVIEWER, commits=[WRITER])
    assert deny_reason(env, p) == ""


def test_注入_書いた窓の欄は古い形の行が在る間は通し_畳んだら数える(env):
    """壊れる 2 段（CONTRIBUTING.md §8）: pr-writer-field の行が在る間（1 段目）は使う側の古い本文の頭の塊の
    `書いた窓: <窓の id>` を通す。行を消した 2 段目からは窓の id として数える。"""
    olds = json.loads((ROOT / "plugins" / "core" / "古い形.json").read_text(encoding="utf-8"))["olds"]
    stage1 = any(o["id"] == "pr-writer-field" for o in olds)
    body = "書いた窓: %s\njob: 20261120-fake\n検査: 緑\n\n" % STRANGER + _tail()
    why = deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=body))
    if stage1:
        assert why == "", "1 段目なのに古い本文の書いた窓の欄を止めた: " + why
    else:
        assert "[words]" in why and STRANGER in why, why
