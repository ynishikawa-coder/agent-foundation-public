"""公開の検査は、作業の木の symlink の指す先を照らし、読めない物は照らした物に数えず名指す（注入の試験）。

前の形: まだ git に入れていない symlink は index に中身（blob）が無いので空として照らした物に数え、
指す先の字（git が次の commit で入れる中身）に鍵が在っても緑だった。普通の file でも symlink でもない物も
空として数え（並べた後に作業の木から消えた・index に中身の無い物）、照らしていない物の一覧に出なかった。
"""
import os

from public_guard_box import CLEAN_CUSTOMER, TOKEN, cli, commit, guard, make_repo

ENV = {"AF_DENY_WORDS": CLEAN_CUSTOMER}


def test_注入_まだ_git_に入れていない_symlink_の指す先も照らす(tmp_path):
    repo = make_repo(tmp_path / "r")
    os.symlink("鍵 " + TOKEN, repo / "link")   # add しない・指す先は無くてよい（git は指す先の字を入れる）
    r = cli(repo, "--files-only", env_extra=ENV)
    assert r.returncode == 1 and "link: GitHub のトークン" in r.stdout, r.stdout


def test_注入_追跡の_symlink_は作業の木の今の指す先を照らす(tmp_path):
    repo = make_repo(tmp_path / "r")
    os.symlink("clean-target", repo / "link")
    commit(repo, {})
    (repo / "link").unlink()
    os.symlink("鍵 " + TOKEN, repo / "link")   # index は古い指す先のまま
    r = cli(repo, "--files-only", env_extra=ENV)
    assert r.returncode == 1 and "link: GitHub のトークン" in r.stdout, r.stdout


def test_きれいな_symlink_は緑(tmp_path):
    repo = make_repo(tmp_path / "r")
    os.symlink("clean-target", repo / "link")
    r = cli(repo, "--files-only", env_extra=ENV)
    assert r.returncode == 0, r.stdout


def test_注入_並べた後に読めなくなった物は照らした物に数えず名指す(tmp_path):
    # git は FIFO などを並べないので、並べた後に作業の木から消えた・index に中身の無い物がこの道に来る
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a.md": "きれい\n"})
    (repo / "z.md").write_text("きれい\n", encoding="utf-8")   # add しない（index に中身が無い）
    g = guard.Guard(repo, [], set())
    it = g.tracked_files()
    seen = [next(it)[0]]                     # ここで並べ終わる
    (repo / "z.md").unlink()                 # 並べた後に消える
    seen += [rel for rel, _ in it]
    assert "z.md" in seen
    assert any("z.md" in u for u in g.unchecked), g.unchecked
