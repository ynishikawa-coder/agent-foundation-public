"""窓の名乗りを記録から取る（判定の形の道具 verdict_form.py の --reviewer・書いた窓の組と、plugins/checker/scripts/pr_writer.py --writers）の注入の試験。

前の形: 判定した窓は 1 行目に手で書いた「レビューした窓:」の字、書いた窓は 1 つ（本文の写しか先端の 1 窓）だった。
今の形: 判定した窓は出す窓の記録（--reviewer）、書いた窓は PR の commit 全部の `Claude-Session:` の組。
"""
import subprocess
import sys
from pathlib import Path

import pytest

from test_pr_text import (REVIEWER, STRANGER, WRITER, _fake_gh, cleanup_body, deny_reason, env, gh,  # noqa: F401
                          verdict_comment)
from test_pr_writer import commit, git

ROOT = Path(__file__).resolve().parent.parent
FORM = ROOT / "plugins" / "checker" / "scripts" / "verdict_form.py"
PR_WRITER = ROOT / "plugins" / "checker" / "scripts" / "pr_writer.py"
HEAD = "0123456789ab" + "c" * 28


def form(tmp_path, *args, body=None):
    f = tmp_path / "v.md"
    f.write_text(body or verdict_comment(), encoding="utf-8")
    p = subprocess.run([sys.executable, str(FORM), str(f), "--head", HEAD, *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def test_出す窓の記録と名乗りが合えば通る(tmp_path):
    assert form(tmp_path, "--writer", WRITER, "--reviewer", REVIEWER) == (0, "")


def test_注入_名乗りの字が出す窓の記録と違えば誤り(tmp_path):
    code, out = form(tmp_path, "--writer", WRITER, "--reviewer", WRITER)       # 書いた窓が他の窓を名乗った
    assert code == 1 and "判定を出す窓" in out and "別の目でない" in out, out
    code, out = form(tmp_path, "--writer", WRITER, "--reviewer", STRANGER)     # 第三の窓が他の窓を名乗った
    assert code == 1 and "判定を出す窓" in out, out


def test_注入_書いた窓の組のどれかが出す窓なら誤り(tmp_path):
    code, out = form(tmp_path, "--writer", "%s,%s" % (WRITER, REVIEWER), "--reviewer", REVIEWER)
    assert code == 1 and "別の目でない" in out, out
    assert form(tmp_path, "--writer", "%s,%s" % (WRITER, STRANGER), "--reviewer", REVIEWER) == (0, "")


@pytest.mark.parametrize("args", [("--writer", ","), ("--writer", " , "), ("--writer", "x,y", "--reviewer", REVIEWER),
                                  ("--writer", WRITER, "--reviewer", "cse_abc")])
def test_注入_書いた窓の組が空か形でなければ止まる(tmp_path, args):
    code, _ = form(tmp_path, *args)
    assert code == 2


def test_助手の名乗りの形は変えない_reviewer_を渡さない手の照らしは前のまま(tmp_path):
    """読むだけの助手は立てた窓の id で名乗る（今の形）。--reviewer の無い手の照らしは 1 行目の字で別の目を見る。"""
    assert form(tmp_path, "--writer", WRITER) == (0, "")
    code, out = form(tmp_path, "--writer", REVIEWER)
    assert code == 1 and "別の目でない" in out


def _writers(repo, head, base="main"):
    p = subprocess.run([sys.executable, str(PR_WRITER), "--writers", "--repo", str(repo), "--head", head, "--base", base],
                       capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def test_注入_途中の_commit_を書いた窓も書いた窓の組に入る(tmp_path):
    """A→B→(記録なし)→A と並ぶ PR の書いた窓は A と B（前の形: 先端から最初の 1 窓＝A だけ）。"""
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    commit(r, "base", STRANGER)                       # main の commit の窓は入らない
    git(r, "checkout", "-qb", "claude/x")
    for i, s in enumerate([WRITER, REVIEWER, None, WRITER]):
        head = commit(r, "f%d" % i, s)
    assert _writers(r, head) == (0, "%s,%s" % (WRITER, REVIEWER))
    git(r, "checkout", "-q", "main")
    commit(r, "later-main", STRANGER)
    git(r, "checkout", "-q", "claude/x")
    git(r, "merge", "-q", "--no-edit", "main")        # main を取り込んでも main の窓は入らない
    assert _writers(r, git(r, "rev-parse", "HEAD")) == (0, "%s,%s" % (WRITER, REVIEWER))


def test_記録の無い_PR_は書いた窓の組を出さず止まる(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    commit(r, "base")
    git(r, "checkout", "-qb", "claude/x")
    head = commit(r, "f")
    assert _writers(r, head)[0] == 2


# ── 窓の名乗りは記録から（手で書いた写しは照らされる側）──
def test_注入_判定の名乗りを偽っても出す窓の記録で照らす(env):
    """書いた窓が、レビューの窓の id を 1 行目に書いて自分の PR に green を出す（前の形: 1 行目の字を判定した窓と読み、通った）。"""
    p = gh("add_issue_comment", issue_number=1, body=verdict_comment())      # 1 行目は REVIEWER と名乗る
    _fake_gh(env)
    assert deny_reason(env, p) == ""                                          # 出す窓が本当に REVIEWER なら通る
    env["CLAUDE_CODE_REMOTE_SESSION_ID"] = "cse_" + WRITER[len("session_"):]  # 出す窓は本当は書いた窓
    why = deny_reason(env, p)
    assert "[verdict]" in why and "判定を出す窓" in why, why
    env["CLAUDE_CODE_REMOTE_SESSION_ID"] = "cse_" + STRANGER[len("session_"):]  # 書いていない第三の窓が他の窓を名乗る
    assert "[verdict]" in deny_reason(env, p)


@pytest.mark.parametrize("value", [None, "", "session_01BBBB", "cse_", "cse_ab-cd"])
def test_注入_出す窓の記録が無ければ判定を通さない(env, value):
    p = gh("add_issue_comment", issue_number=1, body=verdict_comment())
    _fake_gh(env)
    if value is None:
        env.pop("CLAUDE_CODE_REMOTE_SESSION_ID")
    else:
        env["CLAUDE_CODE_REMOTE_SESSION_ID"] = value
    why = deny_reason(env, p)
    assert "判定の材料" in why and "CLAUDE_CODE_REMOTE_SESSION_ID" in why, why


def test_注入_途中の_commit_を書いた窓も書いた側(env):
    """commit が A→B→A と並ぶと、途中を書いた B の判定は別の目でない（前の形: 本文の写し・先端の 1 窓だけを書いた窓と見た）。"""
    p = gh("add_issue_comment", issue_number=1, body=verdict_comment())
    _fake_gh(env, commits=[WRITER, REVIEWER, None, WRITER])                  # 本文は WRITER・先端も WRITER
    why = deny_reason(env, p)
    assert "[verdict]" in why and "別の目でない" in why, why
    _fake_gh(env, commits=[WRITER, STRANGER, WRITER])                         # 途中の窓が出す窓と違えば通る
    assert deny_reason(env, p) == ""


def test_注入_本文の書いた窓の写しを偽っても_commit_の記録で照らす(env):
    p = gh("add_issue_comment", issue_number=1, body=verdict_comment())
    _fake_gh(env, writer=WRITER, commits=[REVIEWER])     # 本文の写しは最初の窓のまま・直しの commit は出す窓が書いた
    why = deny_reason(env, p)
    assert "[verdict]" in why and "別の目でない" in why, why


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

