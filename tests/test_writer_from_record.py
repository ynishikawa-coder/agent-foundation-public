"""窓の名乗りを記録から取る（判定の形の道具 verdict_form.py の --reviewer・書いた窓の組と、scripts/pr_writer.py --writers）の注入の試験。

前の形: 判定した窓は 1 行目に手で書いた「レビューした窓:」の字、書いた窓は 1 つ（本文の写しか先端の 1 窓）だった。
今の形: 判定した窓は出す窓の記録（--reviewer）、書いた窓は PR の commit 全部の `Claude-Session:` の組。
"""
import subprocess
import sys
from pathlib import Path

import pytest

from test_pr_text import REVIEWER, STRANGER, WRITER, verdict_comment
from test_pr_writer import commit, git

ROOT = Path(__file__).resolve().parent.parent
FORM = ROOT / "plugins" / "checker" / "scripts" / "verdict_form.py"
PR_WRITER = ROOT / "scripts" / "pr_writer.py"
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
