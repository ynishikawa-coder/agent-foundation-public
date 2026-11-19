"""衝突の印（<<<<<<<・=======・>>>>>>>）が残った file を検査の入口が拒む。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "conflict_markers.py"


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), "--root", str(root)], capture_output=True, text=True)


def repo(tmp_path: Path, body: str, name: str = "SKILL.md", add: bool = True) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / name).write_text(body, encoding="utf-8")
    if add:
        subprocess.run(["git", "-C", str(tmp_path), "add", name], check=True)
    return tmp_path


def test_この_repo_の木に衝突の印が無い():
    r = run(ROOT)
    assert r.returncode == 0, r.stdout


CONFLICT = "前\n<<<<<<< HEAD\n甲の文\n=======\n乙の文\n>>>>>>> origin/main\n後\n"


@pytest.mark.parametrize("body, n", [
    (CONFLICT, 3),                                                   # PR #51 で起きた形
    ("前\n<<<<<<< HEAD\n甲\n||||||| merged common ancestors\n元\n=======\n乙\n>>>>>>> b\n", 4),  # diff3 の形
    ("<<<<<<<\n甲\n>>>>>>>\n", 2),                                   # 印の後の名が無い形
    ("甲\r\n=======\r\n乙\r\n", 1),                                  # CRLF の行
])
def test_印をわざと入れると赤で場所を名指す(tmp_path, body, n):
    r = run(repo(tmp_path, body))
    assert r.returncode == 1, r.stdout
    assert r.stdout.count("✗ SKILL.md:") == n and "まず構造を疑う" in r.stdout


def test_まだ_git_に載せていない新しい_file_の印も赤(tmp_path):
    r = run(repo(tmp_path, CONFLICT, add=False))
    assert r.returncode == 1 and "SKILL.md:2" in r.stdout


@pytest.mark.parametrize("body", [
    "見出し\n========\n",               # 8 字の下線
    "a <<<<<<< b\n",                   # 行の頭でない
    "<<<<<<<<\n",                      # 8 字
    "```\n# >>>>>>>x\n```\n",          # 印の後に空白が無い
])
def test_印に似た別の形は通す(tmp_path, body):
    assert run(repo(tmp_path, body)).returncode == 0


def test_検査の入口が回す():
    sh = ROOT / "scripts" / "checks" / "conflict_markers.sh"
    assert sh.is_file() and "conflict_markers.py" in sh.read_text(encoding="utf-8")
