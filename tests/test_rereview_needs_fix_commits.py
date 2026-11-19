"""頼み直しの文は、前回の止めるの全部に前回の後に足した commit が結ばれた時だけ出る（rereview.py・注入の試験）。"""
import subprocess
import sys
from pathlib import Path

from test_merge_gate import RED

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "checker" / "scripts" / "rereview.py"


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout.strip()


def commit(repo, name):
    (repo / name).write_text(name, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", name)
    return git(repo, "rev-parse", "HEAD")


def setup(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q")
    old = commit(repo, "a")
    prev = tmp_path / "前回.md"
    prev.write_text(RED.replace("aaaaaaaaaaaa", old[:12]), encoding="utf-8")
    return repo, old, prev


def run(repo, prev, *fixes):
    args = [a for f in fixes for a in ("--fix", f)]
    return subprocess.run([sys.executable, "-B", str(TOOL), "--previous", str(prev), *args], cwd=repo,
                          capture_output=True, text=True)


def test_全部の止めるに前回の後の_commit_を結べば頼みの文が出る(tmp_path):
    repo, old, prev = setup(tmp_path)
    c1, c2 = commit(repo, "b"), commit(repo, "c")
    res = run(repo, prev, f"1={c1}", f"2={c2}")
    assert res.returncode == 0, res.stdout
    assert f"前回の止める 1 番 → {c1[:12]}" in res.stdout and f"前回の止める 2 番 → {c2[:12]}" in res.stdout


def test_止めるが欠けた_先端が動かない_前回より前の_commit_は文を出さない(tmp_path):
    repo, old, prev = setup(tmp_path)
    assert run(repo, prev).returncode == 1                                  # 先端が動かない・commit が無い
    c1 = commit(repo, "b")
    assert run(repo, prev, f"1={c1}").returncode == 1                       # 2 番が欠けた
    assert run(repo, prev, f"1={c1}", f"2={old}").returncode == 1           # 前回の見た先端より前の commit
    assert run(repo, prev, f"1={c1}", f"2={c1}", f"3={c1}").returncode == 1  # 前回に無い番号


def test_頼み直しの手順はこの道具の文を貼る():
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "python3 plugins/checker/scripts/rereview.py --previous <前回の判定> --fix <N>=<commit> …` が出した行をそのまま貼る" in text
