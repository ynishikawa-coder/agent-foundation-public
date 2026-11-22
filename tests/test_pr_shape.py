"""scripts/pr_shape.py: 並ぶ PR が同じ所へ足して衝突する形（同じ名の断片・元から在る試験の file の末尾への追記）を止めるか（注入の試験）。"""
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent / "scripts" / "pr_shape.py"
BR = "claude/20261119-sakumono"


def git(cwd, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "tests").mkdir(parents=True)
    (r / "CHANGELOG.d").mkdir()
    (r / "tests" / "test_old.py").write_text("def test_a():\n    assert 1\n", encoding="utf-8")
    (r / "CHANGELOG.d" / "20261118-mae.txt").write_text("- 足した: 作り物\n", encoding="utf-8")
    git(r, "init", "-q", "-b", "main")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "元")
    git(r, "checkout", "-qb", BR)
    return r


def run(repo, branch=BR):
    return subprocess.run([sys.executable, "-B", str(TOOL), "--branch", branch, "--base", "main", "--repo", str(repo)],
                          capture_output=True, text=True)


def commit(repo):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "枝")


def test_枝から決まる名の断片と新しい試験の_file_は緑(repo):
    (repo / "CHANGELOG.d" / "20261119-sakumono.txt").write_text("- 足した: 作り物\n", encoding="utf-8")
    (repo / "tests" / "test_new_promise.py").write_text("def test_b():\n    assert 1\n", encoding="utf-8")
    (repo / "tests" / "test_old.py").write_text("def test_a():\n    assert 2  # 直すのはよい\n", encoding="utf-8")
    commit(repo)
    res = run(repo)
    assert res.returncode == 0, res.stdout


def test_枝と違う名の断片は赤(repo):
    (repo / "CHANGELOG.d" / "20261119-betsu.txt").write_text("- 足した: 作り物\n", encoding="utf-8")
    commit(repo)
    res = run(repo)
    assert res.returncode == 1 and "CHANGELOG.d/20261119-sakumono.txt" in res.stdout
    assert "細目 §3「まず構造を疑う」" in res.stdout.strip().splitlines()[-1]


def test_元から在る試験の_file_の末尾に試験を足すと赤(repo):
    with (repo / "tests" / "test_old.py").open("a", encoding="utf-8") as f:
        f.write("\n\ndef test_tail():\n    assert 1\n")
    commit(repo)
    res = run(repo)
    assert res.returncode == 1 and "tests/test_old.py" in res.stdout and "新しい file" in res.stdout


def test_commit_前の物も照らす(repo):
    (repo / "CHANGELOG.d" / "20261119-betsu.txt").write_text("- 足した: 作り物\n", encoding="utf-8")
    assert run(repo).returncode == 1


@pytest.mark.parametrize("branch,code", [("claude/sakumono", 1), ("claude/2026-11-19-sakumono", 1),
                                         ("patch-1", 3), ("fix/sakumono", 3), ("main", 3), ("HEAD", 3)])
def test_AI_の枝だけを止め_人の枝と枝の分からない時は照らしていないと出す(repo, branch, code):
    (repo / "CHANGELOG.d" / "20261119-betsu.txt").write_text("- 足した: 作り物\n", encoding="utf-8")
    with (repo / "tests" / "test_old.py").open("a", encoding="utf-8") as f:
        f.write("\n\ndef test_tail():\n    assert 1\n")
    commit(repo)
    res = run(repo, branch)
    assert res.returncode == code, (branch, res.stdout)
    if code == 3:
        assert "照らしていない" in res.stdout and "緑" not in res.stdout, branch
