"""衝突の印の検査（scripts/conflict_markers.py）が、照らさなかった file を緑（印 0）に数えないか。

symlink・頭に NUL がある file（UTF-16・UTF-32 を含む）・手元で消した追跡中の file に印をわざと入れて赤になる事、
読めない物は数えて名指し exit 3（照らしていない＝check_all が緑に数えない）で終える事を見る注入の試験。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "conflict_markers.py"
CONFLICT = "前\n<<<<<<< HEAD\n甲の文\n=======\n乙の文\n>>>>>>> origin/main\n後\n"


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), "--root", str(root)], capture_output=True, text=True)


def git(root: Path, *args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=root,
                          check=True, capture_output=True, **kw)


def init(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    return tmp_path


@pytest.mark.parametrize("data", [
    CONFLICT.encode("utf-16"),                         # UTF-16 の BOM つき（Windows の道具が書く形）
    CONFLICT.encode("utf-16-be"),                      # BOM の無い UTF-16
    b"\xff\xfe\x00\x00" + CONFLICT.encode("utf-32-le"),  # UTF-32 の BOM つき
    b"\x00\x01head\n<<<<<<< HEAD\n\x00\n>>>>>>> b\n",  # 頭に NUL が在る字の混ざった物
], ids=["utf16-bom", "utf16-be-nobom", "utf32-bom", "nul-mixed"])
def test_頭に_NUL_がある_file_の印も赤(tmp_path, data):
    root = init(tmp_path)
    (root / "x.txt").write_bytes(data)
    git(root, "add", "x.txt")
    r = run(root)
    assert r.returncode == 1 and "x.txt:" in r.stdout, r.stdout


def test_印の無い_NUL_の_file_は緑(tmp_path):
    root = init(tmp_path)
    (root / "a.bin").write_bytes(bytes(range(256)) * 4)
    (root / "b.txt").write_bytes("印の無い文\n".encode("utf-16"))
    git(root, "add", "-A")
    r = run(root)
    assert r.returncode == 0, r.stdout


def test_symlink_の中身_指す先の字_の印も赤(tmp_path):
    root = init(tmp_path)
    os.symlink("=======", root / "link")
    git(root, "add", "link")
    r = run(root)
    assert r.returncode == 1 and "link:1" in r.stdout, r.stdout


def test_手元で消した追跡中の_file_は_index_の中身を照らす(tmp_path):
    root = init(tmp_path)
    (root / "SKILL.md").write_text(CONFLICT, encoding="utf-8")
    git(root, "add", "SKILL.md")
    (root / "SKILL.md").unlink()
    r = run(root)
    assert r.returncode == 1 and "SKILL.md:2" in r.stdout, r.stdout


def test_読めない物は数えて名指し_緑に数えない_exit_3(tmp_path):
    root = init(tmp_path)
    blob = git(root, "hash-object", "-w", "--stdin", input=b"a\n").stdout.decode().strip()
    # 解けていない衝突（stage 1〜3 だけ・stage 0 の中身が無い）の file を手元から消した形
    info = "".join(f"100644 {blob} {st}\tgone.md\n" for st in (1, 2, 3))
    git(root, "update-index", "--index-info", input=info.encode())
    r = run(root)
    assert r.returncode == 3 and "照らしていない" in r.stdout and "gone.md" in r.stdout, r.stdout
    assert "緑" not in r.stdout
