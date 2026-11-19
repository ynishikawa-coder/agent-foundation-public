"""PR 本文の `書いた窓:` を先端の commit の `Claude-Session:` で照らす（scripts/pr_writer.py の注入の試験）。

前の形: 本文の `書いた窓:` は最初に PR を出した窓が手で書き、直しの往復で別の窓が commit しても付いて来なかった
（別の目の照らしは本文の窓を書いた窓として読む）。今の形: 先端の commit の窓と違えば CI の job check で赤。
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "pr_writer.py"
CHECK = ROOT / "scripts" / "checks" / "pr_writer.sh"
A, B = "session_01AAAAAAAAAAAAAAAAAAAAAAAA", "session_01BBBBBBBBBBBBBBBBBBBBBBBB"
BRANCH = "claude/20261119-test"


def git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a],
                          check=True, capture_output=True, text=True).stdout.strip()


def commit(repo, name, session=None):
    (repo / name).write_text(name, encoding="utf-8")
    git(repo, "add", "-A")
    msg = f"{name}\n\nCo-Authored-By: t <t@example.invalid>\n"
    if session:
        msg += f"Claude-Session: https://claude.ai/code/{session}\n"
    git(repo, "commit", "-qm", msg)
    return git(repo, "rev-parse", "HEAD")


def repo_with(tmp_path, sessions):
    """main に 1 commit、枝に sessions の順で commit（None は Claude-Session の無い commit）。"""
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    commit(r, "base")
    git(r, "checkout", "-qb", BRANCH)
    head = ""
    for i, s in enumerate(sessions):
        head = commit(r, f"f{i}", s)
    return r, head


def run(repo, head, body, branch=BRANCH):
    f = repo.parent / "body.md"
    f.write_text(body, encoding="utf-8")
    p = subprocess.run([sys.executable, str(TOOL), "--repo", str(repo), "--branch", branch, "--head", head,
                        "--base", "main", "--body-file", str(f)], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def body(writer):
    return f"親窓: {A}\n書いた窓: {writer}\njob: 20261119-test\n検査: x\n\n## 何をどう変えたか\n"


def test_合格_本文の窓と先端の窓が同じなら緑(tmp_path):
    repo, head = repo_with(tmp_path, [A])
    assert run(repo, head, body(A)) == (0, "pr_writer: 緑\n")


def test_注入_直しの往復で別の窓が_commit_したのに本文が最初の窓のままなら赤(tmp_path):
    repo, head = repo_with(tmp_path, [A, B])
    code, out = run(repo, head, body(A))
    assert code == 1 and f"書いた窓: {B}" in out, out


def test_合格_本文を直した窓に替えると緑(tmp_path):
    repo, head = repo_with(tmp_path, [A, B])
    assert run(repo, head, body(B))[0] == 0


def test_合格_main_を取り込む_merge_は飛ばして前の_commit_の窓を見る(tmp_path):
    repo, _ = repo_with(tmp_path, [B])
    git(repo, "checkout", "-q", "main")
    commit(repo, "main2")
    git(repo, "checkout", "-q", BRANCH)
    git(repo, "merge", "-q", "--no-edit", "main")
    head = git(repo, "rev-parse", "HEAD")
    assert run(repo, head, body(B))[0] == 0
    assert run(repo, head, body(A))[0] == 1


def test_注入_Claude_Session_の無い_PR_は赤(tmp_path):
    repo, head = repo_with(tmp_path, [None])
    code, out = run(repo, head, body(A))
    assert code == 1 and "Claude-Session" in out, out


def test_注入_本文に書いた窓が無い_形でないは赤(tmp_path):
    repo, head = repo_with(tmp_path, [A])
    assert run(repo, head, "親窓: x\n")[0] == 1
    assert run(repo, head, body("<session id>"))[0] == 1


def test_main_より前の_commit_の窓は見ない(tmp_path):
    """分かれ目より前（main の上）の Claude-Session は PR の書いた窓でない。"""
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    commit(r, "base", A)
    git(r, "checkout", "-qb", BRANCH)
    head = commit(r, "f", None)
    assert run(r, head, body(A))[0] == 1


def test_人の枝は照らさない(tmp_path):
    repo, head = repo_with(tmp_path, [A])
    code, out = run(repo, head, body(B), branch="patch-1")
    assert code == 3 and "照らしていない" in out


def test_CI_の_job_check_が本文と先端を渡す():
    """入口（scripts/checks/pr_writer.sh）が読む env を、ci.yml の job check が PR の値で渡す。"""
    yml = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = yml.split("\n  check:\n", 1)[1].split("\n  overlap:", 1)[0]
    assert "PR_BODY: ${{ github.event.pull_request.body }}" in job
    assert "PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}" in job
    sh = CHECK.read_text(encoding="utf-8")
    assert "PR_BODY" in sh and "PR_HEAD_SHA" in sh


def test_入口は_PR_で本文が違えば赤(tmp_path):
    repo, head = repo_with(tmp_path, [A, B])
    (repo / "scripts" / "checks").mkdir(parents=True)
    (repo / "window-shape").mkdir()
    for p in (TOOL, CHECK, ROOT / "window-shape" / "window_shape.py", ROOT / "scripts" / "pr_shape.py"):   # 入口は窓の形の正本を直に読む・pr_shape.py の fresh_main が出所の今の main を出す
        (repo / p.relative_to(ROOT)).write_bytes(p.read_bytes())
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(tmp_path / "出所.git")], check=True)
    git(repo, "remote", "add", "origin", str(tmp_path / "出所.git"))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    env = dict(os.environ, GITHUB_EVENT_NAME="pull_request", GITHUB_HEAD_REF=BRANCH, PR_HEAD_SHA=head, PR_BODY=body(A))
    p = subprocess.run(["bash", str(repo / "scripts" / "checks" / "pr_writer.sh")], capture_output=True, text=True, env=env)
    assert p.returncode == 1 and "pr_writer: 赤" in p.stdout, p.stdout + p.stderr
    env["PR_BODY"] = body(B)
    p = subprocess.run(["bash", str(repo / "scripts" / "checks" / "pr_writer.sh")], capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stdout + p.stderr
