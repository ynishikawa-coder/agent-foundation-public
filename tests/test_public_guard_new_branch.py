"""新しい枝の push（before が 0 の並び）は、先端の 1 つでなく既定の枝に無い commit を全部照らす（注入の試験）。

前の形: before が 0 なら `-1 <after>`＝先端の 1 commit だけを見て、前の commit で足して消した鍵を照らさなかった。
"""
import pytest

from public_guard_box import ENV_KEYS, TOKEN, commit, git, guard, make_repo

ZERO = "0" * 40


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)


def _push(ref, after, default="main"):
    return {"ref": "refs/heads/" + ref, "before": ZERO, "after": after, "repository": {"default_branch": default}}


def _secret_in_history(repo):
    commit(repo, {"a.md": "鍵 " + TOKEN + "\n"}, msg="足した")
    commit(repo, remove=["a.md"], msg="消した")
    return commit(repo, {"b.md": "きれい\n"}, msg="先端")


def test_注入_新しい枝の前の_commit_も照らす(tmp_path):
    up = tmp_path / "up.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(up))
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(up), str(work))
    commit(work, {"README.md": "見本\n"}, msg="base")
    git(work, "push", "-q", "origin", "HEAD:main")
    git(work, "checkout", "-q", "-b", "feature")
    after = _secret_in_history(work)
    g = guard.Guard(work, [], set())
    revs = g.revs(None, _push("feature", after))
    assert revs != ["-1", after]
    assert any("GitHub のトークン" in h for h in g.check_history(revs)), revs
    # main に在る base の commit は照らさない（範囲は既定の枝の今の先端から）
    assert g.check_meta(revs, {}) == [] and g.commits_n == 3


@pytest.mark.parametrize("ref", ["main", "feature"])
def test_既定の枝の初めての_push_と先端を聞けない時は全ての歴史(tmp_path, ref):
    repo = make_repo(tmp_path / "r")          # 出所が無い＝既定の枝の先端を聞けない
    after = _secret_in_history(repo)
    hits = guard.run(repo, None, None, [], _push(ref, after))
    assert any("GitHub のトークン" in h for h in hits), hits
