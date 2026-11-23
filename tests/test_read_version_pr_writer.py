"""pr_writer が比べる元を出所の既定の枝で決める（名を main と決め打ちしない）か（注入の試験）。"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pr_writer import A, BRANCH, TOOL, body, commit, git  # noqa: E402,F401


def _origin(tmp_path, repo, default):
    bare = tmp_path / "出所.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", default, str(bare)], check=True)
    git(repo, "remote", "add", "origin", str(bare))
    return bare


def test_注入_出所の既定の枝が_main_でなくてもその枝で比べる(tmp_path):
    """既定の枝が trunk の出所に、古い main も残る。比べる元を省くと trunk の先端で比べる（古い main の上の窓を数えない）。"""
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "trunk")
    commit(r, "base")
    old = git(r, "rev-parse", "HEAD")
    commit(r, "trunk2", A)                       # 既定の枝の上の窓＝PR の書いた窓でない
    _origin(tmp_path, r, "trunk")
    git(r, "push", "-q", "origin", "trunk")
    git(r, "push", "-q", "origin", f"{old}:refs/heads/main")
    git(r, "checkout", "-qb", BRANCH)
    head = commit(r, "f", None)
    f = r.parent / "body.md"
    f.write_text(body(A), encoding="utf-8")
    p = subprocess.run([sys.executable, str(TOOL), "--repo", str(r), "--branch", BRANCH, "--head", head,
                        "--body-file", str(f)], capture_output=True, text=True)
    assert p.returncode == 1 and "Claude-Session" in p.stdout + p.stderr, p.stdout + p.stderr
