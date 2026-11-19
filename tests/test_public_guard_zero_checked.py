"""公開の検査は、照らす物が 0 の時・照らしていない物が在る時に緑と言わない（注入の試験）。

前の形: 置かない語の表に語が 0 でも 0 語で緑・手元では PR の題・本文を照らさず緑・枝の先端が main と同じ（範囲の
commit が 0）でも緑だった。今の形: どれも当たり 0 なら exit 3（照らしていない）で何を照らしていないかを名指す。
"""
import json

from public_guard_box import CLEAN_CUSTOMER, TOKEN, cli, commit, git, make_repo

ENV = {"AF_DENY_WORDS": CLEAN_CUSTOMER}


def test_1段目_置かない語の表に語が0でも止めず緑とは言わない(tmp_path):
    """前の形は語が 0 でも exit 0 で ✅。1 段目は止めない（exit 0）が ✅ とは言わず名指す。2 段目で exit 3。"""
    repo = make_repo(tmp_path / "r")
    commit(repo, {"deny.txt": "# 表（語を 0 にした注入）\n\n"})
    r = cli(repo, "--range", "ALL", "--deny-words-file", "deny.txt", env_extra=ENV)
    assert r.returncode == 0 and "語が 0" in r.stdout and "置かない物 0" not in r.stdout, r.stdout
    commit(repo, {"deny.txt": "# 表\n作り物ノ禁句\n"})
    r = cli(repo, "--range", "ALL", "--deny-words-file", "deny.txt", env_extra=ENV)
    assert r.returncode == 0 and "置かない物 0" in r.stdout, r.stdout


def test_名指した置かない語の表が無ければ空と取り違えず止める(tmp_path):
    repo = make_repo(tmp_path / "r")
    r = cli(repo, "--range", "ALL", "--deny-words-file", "無い表.txt", env_extra=ENV)
    assert r.returncode == 2 and "置かない語の表" in r.stdout, r.stdout


def _origin_and_branch(tmp_path):
    up = tmp_path / "up.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(up))
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(up), str(work))
    commit(work, {"README.md": "見本\n"}, msg="base")
    git(work, "push", "-q", "origin", "HEAD:main")
    git(work, "fetch", "-q", "origin")
    return work


def test_注入_範囲の_commit_が0なら緑と言わない(tmp_path):
    """枝の先端が出所の main と同じ（照らす歴史が 0）。前の形は 0 commit を照らして緑だった。"""
    work = _origin_and_branch(tmp_path)
    r = cli(work, env_extra=ENV)
    assert r.returncode == 3 and "commit が 0" in r.stdout, r.stdout


def test_注入_手元で_PR_の題と本文を照らしていなければ緑と言わない(tmp_path):
    work = _origin_and_branch(tmp_path)
    git(work, "checkout", "-q", "-b", "claude/20261120-x")
    base = git(work, "rev-parse", "HEAD")
    head = commit(work, {"b.md": "枝の物\n"}, msg="枝で足した")
    r = cli(work, env_extra=ENV)
    assert r.returncode == 3 and "PR の題・本文" in r.stdout and "当たりは 0" in r.stdout, r.stdout
    # PR の event を渡せば題・本文も照らす＝照らしていない物が無くなり緑
    ev = tmp_path / "event.json"
    ev.write_text(json.dumps({"pull_request": {"title": "題", "body": "本文", "base": {"sha": base, "ref": "main"},
                                               "head": {"sha": head}}}), encoding="utf-8")
    r = cli(work, env_extra={**ENV, "GITHUB_EVENT_PATH": str(ev)})
    assert r.returncode == 0 and "1 commit" in r.stdout, r.stdout
    # 題に当たりが在れば赤（題を本当に照らしている）
    ev.write_text(json.dumps({"pull_request": {"title": "鍵 " + TOKEN, "body": "", "base": {"sha": base, "ref": "main"},
                                               "head": {"sha": head}}}), encoding="utf-8")
    r = cli(work, env_extra={**ENV, "GITHUB_EVENT_PATH": str(ev)})
    assert r.returncode == 1 and "PR の題" in r.stdout, r.stdout


def test_緑の行は照らした物の数を言い_中身だけの時はそう言う(tmp_path):
    repo = make_repo(tmp_path / "r")
    r = cli(repo, "--files-only", env_extra=ENV)
    assert r.returncode == 0 and "中身 1 個" in r.stdout and "--files-only" in r.stdout, r.stdout
    assert "中身・歴史・外側" not in r.stdout
