"""scripts/pr_shape.py: 元から在る試験の file に試験を足す形を、書き換え（M）の外でも照らすか（注入の試験）。

名の変更（git が見つける R・見つけない D+A）・型の変化（T＝file を symlink に替える）・字下げした class の中の試験・
parametrize の軸の追加をわざと入れて赤になる事と、在る parametrize の行を足すのは緑のままの事を見る。
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent / "scripts" / "pr_shape.py"
BR = "claude/20261120-sakumono"
OLD = '''import pytest


def test_a():
    assert 1


@pytest.mark.parametrize("x", [1, 2])
def test_b(x):
    assert x


class TestC:
    def test_c(self):
        assert 1
'''


def git(cwd, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "tests").mkdir(parents=True)
    (r / "tests" / "test_old.py").write_text(OLD, encoding="utf-8")
    (r / "tests" / "test_other.py").write_text("def test_z():\n    assert 1\n", encoding="utf-8")
    git(r, "init", "-q", "-b", "main")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "元")
    git(r, "checkout", "-qb", BR)
    return r


def run(repo):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "枝", "--allow-empty")
    return subprocess.run([sys.executable, "-B", str(TOOL), "--branch", BR, "--base", "main", "--repo", str(repo)],
                          capture_output=True, text=True)


def _write(repo, rel, text):
    (repo / rel).write_text(text, encoding="utf-8")


def test_字下げした_class_の中に試験を足すと赤(repo):
    _write(repo, "tests/test_old.py", OLD + "\n    def test_c2(self):\n        assert 1\n")
    res = run(repo)
    assert res.returncode == 1 and "TestC.test_c2" in res.stdout, res.stdout


def test_新しい_class_の中に試験を足すと赤(repo):
    _write(repo, "tests/test_old.py", OLD + "\n\nclass TestD:\n    def test_d(self):\n        assert 1\n")
    res = run(repo)
    assert res.returncode == 1 and "TestD.test_d" in res.stdout, res.stdout


def test_parametrize_の軸を足すと赤(repo):
    axis = '@pytest.mark.parametrize("y", [1, 2, 3])'
    _write(repo, "tests/test_old.py", OLD.replace("\ndef test_a():", "\n" + axis + "\ndef test_a(y):"))
    res = run(repo)
    assert res.returncode == 1 and "parametrize の軸" in res.stdout and "test_a" in res.stdout, res.stdout


def test_在る_parametrize_の行を足すのは緑(repo):
    _write(repo, "tests/test_old.py", OLD.replace("[1, 2]", "[1, 2, 3, 4]"))
    res = run(repo)
    assert res.returncode == 0, res.stdout


def test_git_が名の変更と見る_R_で試験を足すと赤(repo):
    git(repo, "mv", "tests/test_old.py", "tests/test_renamed.py")
    with (repo / "tests" / "test_renamed.py").open("a", encoding="utf-8") as f:
        f.write("\n\ndef test_tail():\n    assert 1\n")
    res = run(repo)
    assert res.returncode == 1 and "tests/test_renamed.py（元は tests/test_old.py）" in res.stdout, res.stdout


def test_git_が名の変更と見ない_D_A_で試験を足すと赤(repo):
    (repo / "tests" / "test_old.py").unlink()
    # 中身を大きく変えて git の似ている度合いの外にする（それでも元の試験 test_a を持つ＝移した物）
    _write(repo, "tests/test_moved.py", "def test_a():\n    assert 1\n\n\n" + "".join(
        f"def test_new{i}():\n    assert {i} == {i}  # 足した\n\n\n" for i in range(12)))
    res = run(repo)
    assert res.returncode == 1 and "tests/test_moved.py（元は tests/test_old.py）" in res.stdout, res.stdout


def test_型を_symlink_に替えて試験を増やすと赤(repo):
    (repo / "tests" / "test_old.py").unlink()
    _write(repo, "tests/big.py", OLD + "\n\ndef test_e():\n    assert 1\n")
    os.symlink("big.py", repo / "tests" / "test_old.py")
    res = run(repo)
    assert res.returncode == 1 and "tests/test_old.py" in res.stdout, res.stdout


def test_試験を移さない新しい試験の_file_は緑(repo):
    (repo / "tests" / "test_old.py").unlink()
    _write(repo, "tests/test_new_promise.py", "def test_new():\n    assert 1\n")
    res = run(repo)
    assert res.returncode == 0, res.stdout


def test_名を変えるだけは緑(repo):
    git(repo, "mv", "tests/test_old.py", "tests/test_renamed.py")
    res = run(repo)
    assert res.returncode == 0, res.stdout
