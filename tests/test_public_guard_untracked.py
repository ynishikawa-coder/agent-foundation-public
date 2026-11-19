"""手元の公開の検査は、まだ git に入れていない新しい file（.gitignore の外）も照らす（注入の試験）。

前の形: git ls-files の物と歴史だけを見て、add する前の新しい file の鍵を照らさず緑だった（次の commit で公開に出る）。
"""
from public_guard_box import CLEAN_CUSTOMER, TOKEN, cli, commit, make_repo

ENV = {"AF_DENY_WORDS": CLEAN_CUSTOMER}


def test_注入_まだ_git_に入れていない新しい_file_も照らす(tmp_path):
    repo = make_repo(tmp_path / "r")
    (repo / "new.md").write_text("鍵 " + TOKEN + "\n", encoding="utf-8")   # add しない
    r = cli(repo, "--files-only", env_extra=ENV)
    assert r.returncode == 1 and "new.md: GitHub のトークン" in r.stdout, r.stdout


def test_gitignore_の中の_file_は照らさない(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {".gitignore": "local/\n"})
    (repo / "local").mkdir()
    (repo / "local" / "x.md").write_text("鍵 " + TOKEN + "\n", encoding="utf-8")
    r = cli(repo, "--files-only", env_extra=ENV)
    assert r.returncode == 0, r.stdout
