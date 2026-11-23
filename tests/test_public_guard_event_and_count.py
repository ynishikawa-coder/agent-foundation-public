"""公開の検査は、CI の event を読めない時と、中身を読めなかった file を、照らした物と取り違えない（注入の試験）。

前の形: CI で event の file が無い・壊れていると {} と同じに読み、PR の題・本文を照らさないまま緑になれた。
中身を読めなかった物（submodule・並べた後に消えた物）も「照らした中身」の数に入り、0 件の名指しが出なかった。
"""
import json

from public_guard_box import CLEAN_CUSTOMER, cli, commit, guard, make_repo

ENV = {"AF_DENY_WORDS": CLEAN_CUSTOMER}


def test_注入_CI_で_event_の_path_が無いと照らしていない物に名指す(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    assert guard.EVENT_UNREADABLE in guard.load_event()


def test_注入_CI_で_event_が壊れていると照らしていない物に名指す(monkeypatch, tmp_path):
    bad = tmp_path / "event.json"
    bad.write_text("{壊れた", encoding="utf-8")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(bad))
    assert guard.EVENT_UNREADABLE in guard.load_event()
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "無い.json"))
    assert guard.EVENT_UNREADABLE in guard.load_event()


def test_読めない_event_は_revs_が照らしていない物に入れる(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a.md": "きれい\n"})
    g = guard.Guard(repo, [], set())
    g.revs("HEAD~0..HEAD", {guard.EVENT_UNREADABLE: "x"})   # 範囲を渡した時は event を使わない
    assert not g.unchecked
    try:
        g.revs(None, {guard.EVENT_UNREADABLE: "GITHUB_EVENT_PATH が無い"})
    except Exception:   # 手元の範囲の元が取れない repo でも、名指しは先に入っている
        pass
    assert any("CI の event を読めない" in u for u in g.unchecked), g.unchecked


def test_手元で_event_が在れば読む(monkeypatch, tmp_path):
    ok = tmp_path / "event.json"
    ok.write_text(json.dumps({"after": "x"}), encoding="utf-8")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(ok))
    assert guard.load_event() == {"after": "x"}
    monkeypatch.delenv("GITHUB_EVENT_PATH")
    assert guard.load_event() == {}


def test_注入_中身を読めなかった物は照らした数に入れない(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a.md": "きれい\n"})
    (repo / "z.md").write_text("きれい\n", encoding="utf-8")   # add しない（index に中身が無い）
    whole = guard.Guard(repo, [], set())
    whole.check_files()
    g = guard.Guard(repo, [], set())
    real = g.tracked_files

    def vanish():
        it = real()
        first = next(it)
        (repo / "z.md").unlink()   # 並べた後に消える（中身を読めない）
        yield first
        yield from it
    g.tracked_files = vanish
    g.check_files()
    assert g.files_n == whole.files_n - 1, (g.files_n, whole.files_n)
    assert any("z.md" in u for u in g.unchecked), g.unchecked


def test_注入_中身を読めた物が_0_なら_0_件と名指す(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a.md": "きれい\n"})
    g = guard.Guard(repo, [], set())
    g.tracked_files = lambda: iter([("sub", None)])   # submodule だけ（中身は別の repo）
    g.check_files()
    assert g.files_n == 0
    assert "中身: 照らすファイルが 0" in g.unchecked, g.unchecked
