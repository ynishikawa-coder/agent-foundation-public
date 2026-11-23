"""どの窓が書き・どの窓が見たかを照らさない形の注入の試験（2026-11-23 オーナーの同意・CONTRIBUTING.md §2）。

前の形: 書いた窓の組（commit の `Claude-Session:`）と判定を出す窓の記録を照らし、同じなら判定を止めた。窓を分ける理由
（並走の速さ・自分の物への甘い合格を避ける）を書かずに手段を決まりにし、手段を見張る道具を重ねた。助手に見させた小さな
直しも止まり、書いた窓が合流できず人に merge を頼んだ。
今の形: 窓は照らさない。残す照らしは「今の先端を見た判定か」。誤りの類をわざと入れて、先端の違う判定は拒み、
書いた窓と同じ窓の判定・前の呼び方（--writer・--reviewer）は通すかを見る。
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_pr_text import (REVIEWER, RULES_CLONE, STRANGER, WRITER, _fake_gh, cleanup_body, deny_reason, env, gh,  # noqa: F401
                          verdict_comment)

ROOT = Path(__file__).resolve().parent.parent
FORM = ROOT / "plugins" / "checker" / "scripts" / "verdict_form.py"
HEAD = "0123456789ab" + "c" * 28


def form(tmp_path, *args, body=None, head=HEAD):
    f = tmp_path / "v.md"
    f.write_text(body or verdict_comment(), encoding="utf-8")
    run_env = dict(os.environ, AF_RULES_GIT=str(RULES_CLONE))     # 判定の決まりの版を読む決まりの git（作り物）
    p = subprocess.run([sys.executable, str(FORM), str(f), "--head", head, "--first", "なし", *args],
                       capture_output=True, text=True, env=run_env)
    return p.returncode, p.stdout + p.stderr


def test_窓を渡さない今の呼び方で通る(tmp_path):
    assert form(tmp_path)[0] == 0


@pytest.mark.parametrize("args", [("--writer", WRITER, "--reviewer", REVIEWER), ("--writer", REVIEWER, "--reviewer", REVIEWER),
                                  ("--writer", "%s,%s" % (WRITER, REVIEWER))])
def test_注入_書いた窓と出す窓が同じでも前の呼び方でも通す(tmp_path, args):
    """前の形では「別の目でない」と止めた組。窓は照らさない（受けて使わない）。"""
    code, out = form(tmp_path, *args)
    assert code == 0 and "別の目" not in out, out


def test_注入_先端の違う判定は拒む(tmp_path):
    code, out = form(tmp_path, head="fedcba987654" + "d" * 28)
    assert code == 1 and "先端" in out, out


def test_注入_書いた窓が出す判定も_guard_は通す(env):
    """前の形: 出す窓が書いた窓の組に在ると止めた。今は窓を引かず、先端だけを照らす。"""
    p = gh("add_issue_comment", issue_number=1, body=verdict_comment())
    _fake_gh(env, commits=[REVIEWER])                     # 直しの commit も出す窓が書いた
    env["CLAUDE_CODE_REMOTE_SESSION_ID"] = "cse_" + REVIEWER[len("session_"):]
    assert deny_reason(env, p) == ""
    env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)        # 出す窓の記録が無い窓（手元の窓）も止めない
    assert deny_reason(env, p) == ""


def test_注入_guard_も先端の違う判定は拒む(env):
    p = gh("add_issue_comment", issue_number=1, body=verdict_comment(head="fedcba987654"))
    _fake_gh(env)
    why = deny_reason(env, p)
    assert "[verdict]" in why and "先端" in why, why


def _tail():
    """整地の欄の揃った本文の、頭の塊（最初の空行まで）を除いた残り（窓の id を含まない）。"""
    return cleanup_body().split("\n\n", 1)[1]


WORDS_BAD = [
    ("頭の塊の検査の欄", "書いた窓: %s\n検査: %s の結果\n\n" % (WRITER, STRANGER)),
    ("頭の塊の job の欄", "job: %s\n\n" % STRANGER),
    ("頭の塊の外の書いた窓の行", "job: x\n\n書いた窓: %s が直した\n\n" % STRANGER),
    ("頭の塊の外の親窓の行", "job: x\n\n## 何をどう変えたか\n親窓: %s の頼み\n\n" % STRANGER),
    ("頭の塊の外の検査の行", "job: x\n\n検査: %s の結果\n\n" % STRANGER),
]


@pytest.mark.parametrize("name,head", WORDS_BAD, ids=[c[0] for c in WORDS_BAD])
def test_注入_窓の_id_を数えない欄は頭の塊の書いた窓だけ(env, name, head):
    """前の形: 行頭が job: や 検査: ならどの行でも窓の id を数えず、公開の PR にそのまま出た。"""
    assert STRANGER not in _tail()
    why = deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=head + _tail()))
    assert "[words]" in why and STRANGER in why, why


def test_頭の塊の書いた窓の欄の窓の_id_は数えない(env):
    body = "書いた窓: %s\njob: 20261119-fake\n検査: 緑\n\n" % WRITER + _tail()
    assert deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=body)) == ""
