"""public-guard/guard.py: 読めない物を「読んで照らした」「event が無い所」に畳まないか（わざと読めない形を入れる注入の試験）。

- 「中身 N 個」（files_n）は中身を読んで照らした物だけを数える。読めずに名指した物は数えず、全部読めない repo では
  「照らすファイルが 0」を名指す。読めない file の名は照らす。git が index の中身を読めない時も落ちずに名指す。
- event（GITHUB_EVENT_PATH）は CI で無い・file が無い・読めない・形が違う時に {} へ畳まず、照らしていない物に名指す。
"""
import json
import os
import pathlib

from public_guard_box import CLEAN_CUSTOMER, TOKEN, commit, git, guard, make_repo


def _ci(monkeypatch, event_path=None, ci=True):
    monkeypatch.setenv("AF_DENY_WORDS", CLEAN_CUSTOMER)
    for k in ("GITHUB_ACTIONS", "GITHUB_EVENT_PATH", "AF_DENY_WORDS_FILE", "AF_DENY_BUNDLE"):
        monkeypatch.delenv(k, raising=False)
    if ci:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
    if event_path is not None:
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))


def _unreadable_worktree(monkeypatch, repo):
    real = pathlib.Path.read_bytes

    def boom(self):
        if str(self).startswith(str(repo)):
            raise PermissionError("読めない作り物")
        return real(self)
    monkeypatch.setattr(pathlib.Path, "read_bytes", boom)


def test_注入_全部読めない_repo_は照らした数_0_と名指す(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "r")
    _unreadable_worktree(monkeypatch, repo)
    g = guard.Guard(repo, [], set())
    g.check_files()
    assert g.files_n == 0
    assert any("照らすファイルが 0" in u for u in g.unchecked), g.unchecked
    assert any("README.md" in u and "読めない" in u for u in g.unchecked), g.unchecked


def test_注入_読めない_file_は数えないが名は照らす(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "r")
    commit(repo, {f"d/{TOKEN}.md": "きれい\n"})
    _unreadable_worktree(monkeypatch, repo)
    g = guard.Guard(repo, [], set())
    hits = g.check_files()
    assert g.files_n == 0
    assert any("トークン" in h for h in hits), hits   # 読めない file の名も照らす


def test_読めた物だけ数える(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a.md": "きれい\n"})
    os.symlink("a.md", repo / "l")
    g = guard.Guard(repo, [], set())
    g.check_files()
    assert g.files_n == 3 and not g.unchecked, (g.files_n, g.unchecked)


def test_注入_git_が_index_の中身を読めない時は落ちずに名指す(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"gone.md": "きれい\n"})
    blob = git(repo, "rev-parse", "HEAD:gone.md")
    (repo / "gone.md").unlink()
    (repo / ".git" / "objects" / blob[:2] / blob[2:]).unlink()
    g = guard.Guard(repo, [], set())
    g.check_files()
    assert g.files_n == 1   # README.md だけ
    assert any("gone.md" in u and "git が読めない" in u for u in g.unchecked), g.unchecked


def _event_items(repo):
    _, unchecked, _ = guard.scan(repo, "HEAD~1..HEAD", None, [])
    return [u for u in unchecked if "event を読めない" in u]


def test_注入_CI_で_GITHUB_EVENT_PATH_が無ければ名指す(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a.md": "きれい\n"})
    _ci(monkeypatch)
    items = _event_items(repo)
    assert items and "GITHUB_EVENT_PATH が無い" in items[0]


def test_注入_event_の_file_が無い_壊れている_形が違うと名指す(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a.md": "きれい\n"})
    broken, notdict = tmp_path / "broken.json", tmp_path / "list.json"
    broken.write_text("{壊れた", encoding="utf-8")
    notdict.write_text("[]", encoding="utf-8")
    for path, word, ci in ((tmp_path / "無い.json", "が無い", True), (broken, "読めない", True),
                           (notdict, "object でない", True), (broken, "読めない", False)):
        _ci(monkeypatch, path, ci)
        items = _event_items(repo)
        assert items and word in items[0], (path, ci, items)


def test_読めた_event_と手元で渡さない時は_event_を名指さない(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a.md": "きれい\n"})
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"pull_request": {"title": "t", "body": ""}}), encoding="utf-8")
    _ci(monkeypatch, ok)
    assert guard.load_event()[1] is None and _event_items(repo) == []
    _ci(monkeypatch, ci=False)
    assert guard.load_event() == ({}, None) and _event_items(repo) == []
