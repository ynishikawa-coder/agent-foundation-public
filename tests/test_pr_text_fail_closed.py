"""pr_text の公開の照らしが、出す先が公開かを決められない時に「公開でない」と読んで飛ばさず、公開として照らすか。

決められない時: 出す先の取り出しが手元に無く GitHub の記録（gh api の visibility）も引けない・答えが分からない／取り出しの
workflow が開けない・壊れている。どれも公開の検査（public-guard/guard.py --text）を走らせ、置かない物が在れば止める。
gh は作り物（PATH の頭・実の GitHub へは出ない）。
"""
from pathlib import Path

import pytest

from test_pr_text import MAIL, PUBLIC_WORD, _fake_gh, _fake_public_repo, deny_reason, env, gh  # noqa: F401

FAR = dict(repo="far-repo")                       # 手元に取り出しの無い repo


def _comment(**kw):
    return gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL, **kw)


@pytest.mark.parametrize("visibility", [None, "public", "", "作り物の答え"])
def test_取り出しの無い_repo_は記録が公開でないと言い切らなければ照らして止める(env, visibility):
    """引けない（None）・公開・空・分からない答えは、どれも公開として照らす。"""
    _fake_gh(env, visibility=visibility)
    why = deny_reason(env, _comment(**FAR))
    assert "[public]" in why and "メールアドレス" in why


@pytest.mark.parametrize("visibility", ["private", "internal"])
def test_取り出しの無い_repo_は記録が公開でないと言い切る時だけ照らさない(env, visibility):
    _fake_gh(env, visibility=visibility)
    assert deny_reason(env, _comment(**FAR)) == ""


def test_取り出しの無い_repo_で_gh_そのものが無くても照らして止める(env):
    env["PATH"] = str(Path(env["CLAUDE_PROJECT_DIR"]).parent / "空")
    assert "[public]" in deny_reason(env, _comment(**FAR))


def test_取り出しの無い_repo_で_gh_が全部落ちても照らして止める(env):
    _fake_gh(env, fail=True)
    assert "[public]" in deny_reason(env, _comment(**FAR))


def test_記録が_private_でも値の表の公開の鍵は効く(env, tmp_path):
    import json
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"guard": {"public_repos_extra": ["^fake-owner/far-repo$"]}}), encoding="utf-8")
    env["SKILL_VALUES"] = str(table)
    _fake_gh(env, visibility="private")
    assert "[public]" in deny_reason(env, _comment(**FAR))


def _only_workflow_unreadable(proj, how):
    wf = proj / ".github" / "workflows" / "public-guard.yml"
    if how == "開けない":
        wf.unlink()
        wf.mkdir()                                # file でない＝開けない
    else:
        wf.write_text(":::\n- - x\n  y: [\n", encoding="utf-8")   # 読み手が形を読めない


@pytest.mark.parametrize("how", ["開けない", "壊れた"])
def test_公開の検査を呼ぶ_workflow_が読めない取り出しは公開として照らして止める(env, how):
    """唯一の呼び口の workflow が読めないと、前は「公開でない」と読んで照らさずに出した。"""
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_public_repo(proj, PUBLIC_WORD)
    _only_workflow_unreadable(proj, how)
    _fake_gh(env, visibility="private")           # 取り出しが在る時は GitHub の記録で外さない
    why = deny_reason(env, _comment(repo="fake-public"))
    assert "[public]" in why and "メールアドレス" in why
    assert deny_reason(env, gh("add_issue_comment", issue_number=1, body="作り物の確かめ", repo="fake-public")) == ""


def test_読める_workflow_が呼び口を持たない取り出しは公開でない(env):
    """決められる時（全部読めて呼び口が無い）は今までどおり照らさない＝止めすぎない。"""
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_public_repo(proj, PUBLIC_WORD)
    (proj / ".github" / "workflows" / "public-guard.yml").write_text(
        "on: [pull_request]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo 作り物\n",
        encoding="utf-8")
    _fake_gh(env, visibility=None)
    assert deny_reason(env, _comment(repo="fake-public")) == ""
