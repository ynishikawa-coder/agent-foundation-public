"""PR の書いた窓を commit の `Claude-Session:`（記録）だけから決める（plugins/checker/scripts/pr_writer.py の注入の試験）。

前の形: PR 本文の頭の `書いた窓:`（手で書く写し）を先端の commit の窓と照らした。本文は push の後でしか直せないので、
別の窓が main を取り込んで push する度に先端の窓が変わり、その push の CI が毎回 1 回赤になった（PR 92・run 44585946954）。
今の形: 本文の写しを照らさず（古い土台の窓のために型の行は 2 段目まで残す）、書いた窓は PR の commit 全部の `Claude-Session:` の窓の組。push の時点で決まる物だけで照らす。
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "checker" / "scripts" / "pr_writer.py"
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


def run(repo, head, branch=BRANCH):
    p = subprocess.run([sys.executable, str(TOOL), "--repo", str(repo), "--branch", branch, "--head", head,
                        "--base", "main"], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def writers(repo, head):
    p = subprocess.run([sys.executable, str(TOOL), "--repo", str(repo), "--writers", "--head", head, "--base", "main"],
                       capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def merge_main_by(repo, session):
    """main に 1 commit 進め、別の窓 session が枝へ main を取り込む merge commit を作る（PR 92 で赤になった形）。"""
    git(repo, "checkout", "-q", "main")
    commit(repo, "main2")
    git(repo, "checkout", "-q", BRANCH)
    git(repo, "merge", "-q", "--no-ff", "-m", f"main を取り込む\n\nClaude-Session: https://claude.ai/code/{session}\n", "main")
    return git(repo, "rev-parse", "HEAD")


def test_合格_記録が在れば緑で書いた窓の組を出す(tmp_path):
    repo, head = repo_with(tmp_path, [A])
    assert run(repo, head) == (0, f"pr_writer: 緑（書いた窓の組: {A}）\n")


def test_注入_別の窓が_main_を取り込んで_push_しても赤にならない(tmp_path):
    """前の形の赤の再現: A が書いた PR に B が main を取り込む merge を push した。本文を直す前の push でも緑。"""
    repo, _ = repo_with(tmp_path, [A])
    head = merge_main_by(repo, B)
    code, out = run(repo, head)
    assert code == 0 and "赤" not in out, out


def test_注入_取り込みの_merge_を書いた窓も書いた側に残る(tmp_path):
    """安全を落とさない: merge には衝突の解き方という中身が在るので、取り込んだ窓 B は別の目になれない。"""
    repo, _ = repo_with(tmp_path, [A])
    head = merge_main_by(repo, B)
    assert writers(repo, head) == (0, f"{B},{A}")


def test_注入_途中の_commit_を書いた窓も組に入る(tmp_path):
    repo, head = repo_with(tmp_path, [A, B, None, A])
    assert writers(repo, head) == (0, f"{A},{B}")


def test_注入_Claude_Session_の無い_PR_は赤(tmp_path):
    repo, head = repo_with(tmp_path, [None])
    code, out = run(repo, head)
    assert code == 1 and "Claude-Session" in out and "pr_writer: 赤" in out, out
    assert writers(repo, head)[0] == 2


def test_main_より前の_commit_の窓は見ない(tmp_path):
    """分かれ目より前（main の上）の Claude-Session は PR の書いた窓でない。"""
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    commit(r, "base", A)
    git(r, "checkout", "-qb", BRANCH)
    head = commit(r, "f", None)
    assert run(r, head)[0] == 1


def test_人の枝は照らさない(tmp_path):
    repo, head = repo_with(tmp_path, [A])
    code, out = run(repo, head, branch="patch-1")
    assert code == 3 and "照らしていない" in out


def test_本文の写しを読む口が残っていない():
    """畳んだ写しへ戻らない: 道具は本文を受け取らず、CI は本文を渡さない。"""
    assert "--body-file" not in TOOL.read_text(encoding="utf-8")
    yml = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = yml.split("\n  check:\n", 1)[1].split("\n  overlap:", 1)[0]
    assert "PR_BODY" not in job
    assert "PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}" in job
    sh = CHECK.read_text(encoding="utf-8")
    assert "PR_BODY" not in sh and "PR_HEAD_SHA" in sh


def test_PR_の型の書いた窓の行は古い土台の窓のためだけに残し_今の道具は読まない():
    """壊れる 1 段目: 古い土台の窓の守りの hook は判定の材料に本文の `書いた窓:` を読むので、型の行は 2 段目まで残す。
    今の道具（CI の照らし・守りの hook）はその行を読まない＝取り込みの後に直さなくても赤にも止めにもならない。"""
    t = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
    assert t.splitlines()[0].startswith("書いた窓:")
    assert "CI も今の道具も読まない" in t
    pr_text = (ROOT / "plugins" / "guard" / "scripts" / "pr_text.py").read_text(encoding="utf-8")
    assert "WRITER_LINE" not in pr_text and ".body" not in pr_text


def test_入口は_PR_で取り込みの_push_でも緑_記録が無ければ赤(tmp_path):
    repo, _ = repo_with(tmp_path, [A])
    (repo / "scripts" / "checks").mkdir(parents=True)
    (repo / "plugins" / "checker" / "scripts").mkdir(parents=True)
    for p in (TOOL, CHECK, ROOT / "scripts" / "pr_shape.py"):  # pr_shape.py の fresh_main が出所の今の main を出す
        (repo / p.relative_to(ROOT)).write_bytes(p.read_bytes())
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "道具を置く\n\nClaude-Session: https://claude.ai/code/%s\n" % A)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(tmp_path / "出所.git")], check=True)
    git(repo, "remote", "add", "origin", str(tmp_path / "出所.git"))
    head = merge_main_by(repo, B)
    git(repo, "push", "-q", "origin", "main")
    git(repo, "update-ref", "refs/remotes/origin/main", "main")
    sh = str(repo / "scripts" / "checks" / "pr_writer.sh")
    env = dict(os.environ, GITHUB_EVENT_NAME="pull_request", GITHUB_HEAD_REF=BRANCH, PR_HEAD_SHA=head,
               PR_BODY=f"書いた窓: {A}\n")   # 古い本文の写しが残っていても読まない
    p = subprocess.run(["bash", sh], capture_output=True, text=True, env=env)
    assert p.returncode == 0 and "pr_writer: 緑" in p.stdout, p.stdout + p.stderr
    env["PR_HEAD_SHA"] = git(repo, "rev-parse", "main")   # PR の commit が無い＝記録が無い
    p = subprocess.run(["bash", sh], capture_output=True, text=True, env=env)
    assert p.returncode == 1 and "pr_writer: 赤" in p.stdout, p.stdout + p.stderr
