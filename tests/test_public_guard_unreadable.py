"""公開の検査は、UTF-8 で読めない中身・作業の木で消した追跡のファイル・歴史のバイナリの差分も照らす（注入の試験）。

前の形: UTF-8 で読めないファイルは中身を空として名だけ照らし、作業の木に無い追跡のファイルは飛ばし、歴史の
git log -p はバイナリの差分（Binary files differ）を照らさなかった。どれも鍵が入っていても緑だった。
"""
from public_guard_box import CLEAN_CUSTOMER, TOKEN, cli, commit, make_repo

ENV = {"AF_DENY_WORDS": CLEAN_CUSTOMER}


def test_注入_UTF8_で読めない中身の鍵も照らす(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"blob.bin": b"\xff\xfe\x00 " + TOKEN.encode() + b" \x00\x80"})
    r = cli(repo, "--files-only", env_extra=ENV)
    assert r.returncode == 1 and "blob.bin: GitHub のトークン" in r.stdout, r.stdout


def test_注入_作業の木で消した追跡のファイルは_index_の中身を照らす(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit(repo, {"a.md": "鍵 " + TOKEN + "\n"})
    (repo / "a.md").unlink()          # 作業の木だけで消す（index には在る＝まだ公開に出うる）
    r = cli(repo, "--files-only", env_extra=ENV)
    assert r.returncode == 1 and "a.md: GitHub のトークン" in r.stdout, r.stdout


def test_注入_歴史のバイナリの差分も照らす(tmp_path):
    repo = make_repo(tmp_path / "r")
    # 中身に区切りの字 \x1e も入れる（区切りを取り違えて照らし損ねない）
    commit(repo, {"img.bin": b"\x00\x01\x1e\x1f" + TOKEN.encode() + b"\x00\xff"}, msg="足した")
    commit(repo, remove=["img.bin"], msg="消した")
    r = cli(repo, "--range", "ALL", env_extra=ENV)
    assert r.returncode == 1 and "img.bin: GitHub のトークン" in r.stdout and "commit" in r.stdout, r.stdout
