"""scripts/pr_shape.py: git が読めない時を「path が無い」と読まず止めるか（注入の試験）。

原因の台帳: _blob と show が git の失敗（ref が無い・壊れた取り出し）を None に変え、「元の試験の file が無い」と読んで
照らす物を 0 にしたまま進んだ。在る・無いは ls-tree の答えで決め、git の失敗は OSError（入口が exit 2 で名指す）。
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pr_shape  # noqa: E402


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.py").write_text("def test_a():\n    assert 1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def test_在る_path_は中身を返す(repo):
    assert "test_a" in pr_shape._blob(repo, "HEAD", "a.py")


def test_本当に無い_path_は_None(repo):
    assert pr_shape._blob(repo, "HEAD", "無い.py") is None


def test_注入_ref_が無い時は無いと読まず止める(repo):
    with pytest.raises(OSError):
        pr_shape._blob(repo, "0" * 40, "a.py")


def test_注入_show_が失敗したら止める(repo, monkeypatch):
    real = subprocess.run

    def broken(cmd, *a, **k):
        if cmd[:2] == ["git", "show"]:
            return subprocess.CompletedProcess(cmd, 128, "", "fatal: 壊れた取り出し")
        return real(cmd, *a, **k)
    monkeypatch.setattr(pr_shape.subprocess, "run", broken)
    with pytest.raises(OSError):
        pr_shape._blob(repo, "HEAD", "a.py")
