"""閉じた語彙の注入の試験（PR の文の照らし・guard の pr_text）。前の形がそれぞれ通した入力をわざと入れ、止まる事を見る。

- 判定の行: 前は `判定: green|red` の行だけを判定と見分け、表に無い判定の字（yellow・緑）の判定は形の照らしの外へ出た
- 雛形の置き場: 前は 4 字未満の `〔…〕`（〔URL〕・〔所在〕・〔行き先〕）を拾わなかった
- 整地の見出し: 前は見出しの頭が合えば通した（`## 3. 解決しない`）
- 整地の不要の行: 前は行の頭だけを見た（`整地: 不要（…）` と置き場の字・別の値）
- 公開の repo: 前は窓に取り出しの無い repo を公開と見ず、公開の検査を飛ばした（GitHub の visibility を引かない）
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pr_text import MAIL, cleanup_body, deny_reason, env, gh, verdict_comment, _fake_gh  # noqa: E402,F401


@pytest.mark.parametrize("word", ["yellow", "緑", "GREEN?"])
def test_表に無い判定の字の判定も形の道具が拒む(env, word):  # noqa: F811
    _fake_gh(env)
    body = verdict_comment().replace("判定: green", "判定: " + word)
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body=body))
    assert "[verdict]" in why, why


@pytest.mark.parametrize("left", ["〔URL〕", "〔所在〕", "〔行き先〕", "〔どこで〕"])
def test_雛形の短い置き場も残れば止める(env, left):  # noqa: F811
    why = deny_reason(env, gh("update_pull_request", pullNumber=1, body=cleanup_body("\n- 直す窓 %s\n" % left)))
    assert "[cleanup]" in why and left in why, why


def test_字で引いた置き場は残りと数えない(env):  # noqa: F811
    assert deny_reason(env, gh("update_pull_request", pullNumber=1,
                               body=cleanup_body("\n雛形の `〔URL〕` を拾う直し。\n"))) == ""


@pytest.mark.parametrize("bad", ["## 3. 解決しない", "## 1. 問題なし", "## 4. 未来の話"])
def test_整地の見出しは名の後に字を足した行を数えない(env, bad):  # noqa: F811
    no = bad.split(".")[0][-1]
    body = re.sub(r"^## %s\. [^\n]+$" % no, bad, cleanup_body(), flags=re.M)
    assert bad in body
    why = deny_reason(env, gh("update_pull_request", pullNumber=1, body=body))
    assert "[cleanup]" in why and "見出しが無い" in why, why


def test_雛形の見出しの行そのままと名の頭だけの行は通る(env):  # noqa: F811
    body = cleanup_body()
    assert "## 3. 解決（足す物・畳む物・注入の試験と残る穴）" in body
    assert deny_reason(env, gh("update_pull_request", pullNumber=1, body=body)) == ""
    short = body.replace("## 3. 解決（足す物・畳む物・注入の試験と残る穴）", "## 3. 解決")
    assert deny_reason(env, gh("update_pull_request", pullNumber=1, body=short)) == ""


@pytest.mark.parametrize("line", ["整地: 不要（…）", "整地: 不要（ …）", "整地: 不要かも（誤字だけ）", "整地: 要らない（誤字だけ）",
                                  "整地: 不要（誤字だけ）ただし後で書く", "整地: 不要（〔訳〕）"])
def test_整地の不要の行は値と訳の形が字どおりの時だけ(env, line):  # noqa: F811
    body = "## 何をどう変えたか\n誤字。\n\n%s\n" % line
    why = deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=body))
    assert "[cleanup]" in why, why


def test_整地の不要の行の正しい形は通る(env):  # noqa: F811
    body = "## 何をどう変えたか\n誤字。\n\n- 整地: 不要（振る舞いを変えない誤字の直しだけ）\n"
    assert deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=body)) == ""


@pytest.mark.parametrize("repo", ["gh-public", "gh-unknown"])
def test_取り出しの無い_repo_は_GitHub_の見え方で公開を決め_引けなければ公開として照らす(env, repo):  # noqa: F811
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL, repo=repo))
    assert "[public]" in why, why


@pytest.mark.parametrize("repo", ["fake-private", "gh-internal"])
def test_非公開と言い切れる_repo_だけ公開の検査を当てない(env, repo):  # noqa: F811
    assert deny_reason(env, gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL, repo=repo)) == ""
