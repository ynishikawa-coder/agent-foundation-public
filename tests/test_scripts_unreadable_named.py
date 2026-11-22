"""scripts の pr_shape と pr_overlap が、読めない物を「無い」「空の差分」「1 頁目で全部」に畳まず名指すか（注入の試験）。

pr_shape: git が分かれ目の中身を読めない・symlink の指す先が無い・作業の木の file が読めない時、試験 0 本の空として
  数えず「照らせない」（exit 2）で path と訳を名指す。
pr_overlap: patch の無い file を空の差分と見ず file の全部と見て名指す。開いている PR の一覧・PR の file の一覧は
  頁を全部辿り、GitHub が全部を返さない量に届いたら見ていない（exit 3）と言う。
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ps = _load("af_pr_shape_unreadable", ROOT / "scripts" / "pr_shape.py")
po = _load("af_pr_overlap_unreadable", ROOT / "scripts" / "pr_overlap.py")
BR = "claude/20261122-yomenai"


# ── pr_shape ──

def git(cwd, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "tests").mkdir(parents=True)
    (r / "tests" / "test_old.py").write_text("def test_a():\n    assert 1\n", encoding="utf-8")
    git(r, "init", "-q", "-b", "main")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "元")
    git(r, "checkout", "-qb", BR)
    return r


def commit(r):
    git(r, "add", "-A")
    git(r, "commit", "-qm", "枝")


def test_git_が分かれ目を読めない時は無いと畳まず_OSError(repo):
    with pytest.raises(OSError, match="ls-tree"):
        ps._blob(repo, "無い-ref", "tests/test_old.py")


def test_分かれ目に無い時だけ_None(repo):
    assert ps._blob(repo, "main", "tests/無い.py") is None
    assert "test_a" in ps._blob(repo, "main", "tests/test_old.py")


def test_symlink_の指す先が無い時は_OSError(tmp_path):
    r = tmp_path / "r"
    (r / "tests").mkdir(parents=True)
    os.symlink("無い先.py", r / "tests" / "test_link.py")
    git(r, "init", "-q", "-b", "main")
    commit(r)
    with pytest.raises(OSError, match="指す先"):
        ps._blob(r, "main", "tests/test_link.py")


def test_分かれ目で_UTF8_でない中身は_OSError(tmp_path):
    r = tmp_path / "r"
    (r / "tests").mkdir(parents=True)
    (r / "tests" / "test_bin.py").write_bytes(b"\xff\xfe\x00def test_a(): pass\n")
    git(r, "init", "-q", "-b", "main")
    commit(r)
    with pytest.raises(OSError, match="UTF-8"):
        ps._blob(r, "main", "tests/test_bin.py")


def test_作業の木の試験の_file_が読めない時は空と見ず_OSError(repo):
    (repo / "tests" / "test_old.py").unlink()
    os.symlink("無い先.py", repo / "tests" / "test_old.py")
    with pytest.raises(OSError, match="tests/test_old.py"):
        ps._now(repo, "tests/test_old.py")


def test_git_が書き換えた試験の_file_を読めない時は照らせないで_path_を名指す(repo, monkeypatch, capsys):
    (repo / "tests" / "test_old.py").write_text("def test_a():\n    assert 2\n", encoding="utf-8")
    commit(repo)
    real = ps.git

    def flaky(root, *args):
        if args[:1] == ("ls-tree",):
            raise OSError("git ls-tree: 作り物の読めない")
        return real(root, *args)

    monkeypatch.setattr(ps, "git", flaky)
    monkeypatch.delenv("AF_CHECK_UNCHECKED", raising=False)
    assert ps.main(["--branch", BR, "--base", "main", "--repo", str(repo)]) == 2
    out = capsys.readouterr().out
    assert "照らせない" in out and "作り物の読めない" in out and "緑" not in out


def test_消した試験の_file_の構文が読めない時は畳まず名指す(tmp_path):
    r = tmp_path / "r"
    (r / "tests").mkdir(parents=True)
    (r / "tests" / "test_broken.py").write_text("def test_a(:\n", encoding="utf-8")
    git(r, "init", "-q", "-b", "main")
    commit(r)
    git(r, "checkout", "-qb", BR)
    (r / "tests" / "test_broken.py").unlink()
    commit(r)
    errs = ps.check(r, BR, "main")
    assert any("tests/test_broken.py" in e and "読めない" in e for e in errs), errs


# ── pr_overlap ──

def test_patch_の無い_file_は空でなく全部と見る():
    assert po.ranges(None) == [po.WHOLE]
    assert po.carry((10, 12), None) == po.WHOLE
    assert po.carry(po.WHOLE, "@@ -1,1 +1,3 @@\n") == po.WHOLE
    # 自分は patch の無い file（バイナリ等）、相手は 500 行目を書き換え＝重なる（前は空の差分で重ならないと言った）
    hits = po.overlaps({"img.bin": None}, {"#2": {"img.bin": "@@ -500,1 +500,1 @@\n"}})
    assert [(h[0], h[1]) for h in hits] == [("#2", "img.bin")]


def test_compare_は_patch_の無い_file_を_None_で返す(monkeypatch):
    monkeypatch.setattr(po, "_get", lambda url, tok: {"merge_base_commit": {"sha": "m"},
                                                     "files": [{"filename": "a.bin"}, {"filename": "b.md", "patch": "@@ -1 +1 @@\n"}]})
    assert po.compare("o/r", "x", "y", "t") == ("m", {"a.bin": None, "b.md": "@@ -1 +1 @@\n"})


def test_compare_の上限に届いたら全部と言わず例外(monkeypatch):
    files = [{"filename": f"f{i}", "patch": "@@ -1 +1 @@\n"} for i in range(po.COMPARE_CAP)]
    monkeypatch.setattr(po, "_get", lambda url, tok: {"merge_base_commit": {"sha": "m"}, "files": files})
    with pytest.raises(OSError, match="上限"):
        po.compare("o/r", "x", "y", "t")


def test_試験の口で_patch_が_null_の_file_を名指す(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps({"img.bin": None}), encoding="utf-8")
    b.write_text(json.dumps({"#2": {"img.bin": "@@ -500,1 +500,1 @@\n"}}), encoding="utf-8")
    res = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "pr_overlap.py"), "--self", str(a), "--others", str(b)],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "#2 も img.bin の 全部" in res.stdout and "patch が無く行が分からない" in res.stdout and "img.bin" in res.stdout
    assert "重なる PR は無い" not in res.stdout


def _pages(book):
    """{url: (中身, 次の url)} の作り物の GitHub（読み口 _get の形＝一覧は次の頁の URL つきの Page）。"""
    def get(url, tok):
        data, nxt = book[url]
        if isinstance(data, list):
            data = po.Page(data)
            data.next = nxt
        return data
    return get


def test_開いている_PR_の一覧は頁を全部辿る(monkeypatch):
    base = "https://api.github.com/repos/o/r/pulls?state=open&per_page=100"
    first = [{"number": n, "head": {"ref": f"b{n}"}} for n in range(1, 101)]
    book = {base: (first, base + "&page=2"), base + "&page=2": ([{"number": 101, "head": {"ref": "b101"}}], None)}
    for n in range(1, 102):
        book[f"https://api.github.com/repos/o/r/pulls/{n}/files?per_page=100"] = (
            [{"filename": "core.md" if n == 101 else f"x{n}.md"}], None)
    monkeypatch.setattr(po, "_get", _pages(book))
    assert len(po.open_prs("o/r", "t")) == 101
    # 101 本目（2 頁目）の PR が宣言した file を書き換えている＝前は 1 頁目で切って重ならないと言った
    assert po.claimed(["core.md"], po.open_files("o/r", "t")) == [("#101 b101", "core.md")]


def test_PR_の_file_が上限に届いたら見ていない_exit_3(monkeypatch, capsys):
    base = "https://api.github.com/repos/o/r/pulls?state=open&per_page=100"
    files = "https://api.github.com/repos/o/r/pulls/7/files?per_page=100"
    book = {base: ([{"number": 7, "head": {"ref": "b7"}}], None),
            files: ([{"filename": f"f{i}"} for i in range(po.PR_FILES_CAP)], None)}
    monkeypatch.setattr(po, "_get", _pages(book))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert po.main(["--repo", "o/r", "--files", "core.md"]) == 3
    out = capsys.readouterr().out
    assert "見ていない" in out and "#7" in out and "上限" in out and "重ならない" not in out.replace("重ならないとは言えない", "")


def test_一覧でない物が返ったら例外(monkeypatch):
    monkeypatch.setattr(po, "_get", lambda url, tok: {"message": "Bad credentials"})
    with pytest.raises(OSError, match="一覧のはず"):
        po.open_prs("o/r", "t")
