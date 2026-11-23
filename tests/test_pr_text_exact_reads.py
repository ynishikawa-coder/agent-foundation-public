"""守りの hook pr_text と値の表の型が、値の表・workflow を「当の物だけ・今の形だけ」で読むか（注入の試験）。

1. 置かない語の表（deny-words-file）は、action public-guard を呼ぶ step の with: からだけ読む。同じ workflow の
   別の step・別の job の deny-words-file を拾わない（直す前は file 全体から最初の 1 つを拾っていた）。
2. 値の表の repo の名の行（pr_cleanup_exempt_repos・pr_words_exempt_repos・public_repos_extra）は名の全体にだけ当てる。
   前の形（錨なしで名の一部に当てる）を受ける道は畳んだ（直す前は _listed が受けていた）。
3. 値の表の型の正本（skill-values/schema.json）がそれらを型 repo_names（各行を ^ で始め $ で終える）で照らし、
   頭だけ・錨なしの前の形を名指す（直す前は型 list しか照らさず通していた）。
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
sys.path.insert(0, str(ROOT / "skill-values"))
sys.path.insert(0, str(ROOT / "public-guard"))
import pr_text as P  # noqa: E402
import skill_values as SV  # noqa: E402
import workflow_reader as W  # noqa: E402

from test_wf_reader import whole  # noqa: E402  断片を PR で走る workflow の job の steps に包む

from test_pr_text import MAIL, PUBLIC_WORD, _fake_gh, _fake_public_repo, deny_reason, env, gh  # noqa: E402,F401

F = "ynishikawa-coder/agent-foundation-public"
CALL = "uses: %s/public-guard@main" % F
REPO_KEYS = ("public_repos_extra",)


# ── 1. deny-words-file は public-guard を呼ぶ step の with: からだけ ──
@pytest.mark.parametrize("wf,want", [
    ("    steps:\n      - %s\n        with:\n          deny-words-file: data/deny.txt\n" % CALL, "data/deny.txt"),
    ("    steps:\n      - name: x\n        %s\n        with:\n          deny-words-file: 'data/q.txt'  # 注\n" % CALL,
     "data/q.txt"),
    ("    steps:\n      - %s\n        with: {deny-words: x, deny-words-file: data/f.txt}\n" % CALL, "data/f.txt"),
    # 別の step が先に deny-words-file を持つ（直す前はこちらを拾った）
    ("    steps:\n      - uses: someone/other-check@v1\n        with:\n          deny-words-file: other/list.txt\n"
     "      - %s\n        with:\n          deny-words-file: data/deny.txt\n" % CALL, "data/deny.txt"),
    # 別の job の step が持つだけ・public-guard を呼ぶ step は持たない
    ("jobs:\n  a:\n    steps:\n      - run: echo\n        env:\n          deny-words-file: other/list.txt\n"
     "  b:\n    steps:\n      - %s\n" % CALL, ""),
    # step の外（env や with の外の鍵）・コメントの行
    ("env:\n  deny-words-file: other/list.txt\njobs:\n  b:\n    steps:\n      - %s\n"
     "        # with:\n        #   deny-words-file: other/c.txt\n" % CALL, ""),
    # with の下のさらに深い所（別の鍵の値の中）は with の鍵でない
    ("    steps:\n      - %s\n        with:\n          pattern-skip: |\n            deny-words-file: other/x.txt\n" % CALL, ""),
])
def test_置かない語の表は_public_guard_を呼ぶ_step_の_with_からだけ読む(wf, want):
    assert W.deny_words_files(whole(wf), F) == ([want] if want else [])


def test_別の_step_の語の表を公開の検査に渡さない(env):  # noqa: F811
    """入口から: 先の step の語の表（禁句を持たない）でなく、public-guard の step の語の表（禁句を持つ）で照らす。"""
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_public_repo(proj, PUBLIC_WORD)
    (proj / "data" / "other.txt").write_text("作り物の別の語\n", encoding="utf-8")
    (proj / ".github" / "workflows" / "public-guard.yml").write_text(
        "on: [pull_request]\njobs:\n  public-guard:\n    steps:\n      - uses: someone/other-check@v1\n        with:\n"
        "          deny-words-file: data/other.txt\n      - %s\n        with:\n"
        "          deny-words-file: data/deny.txt\n" % CALL, encoding="utf-8")
    why = deny_reason(env, gh("update_pull_request", pullNumber=1, title="%s の直し" % PUBLIC_WORD, repo="fake-public"))
    assert "[public]" in why


# ── 2. 値の表の repo の名は全体にだけ当てる（前の形の受けを畳んだ） ──
def test_前の形の受けは畳んだ():
    assert not hasattr(P, "_listed")


@pytest.mark.parametrize("pats,repo", [
    (["^fake-owner/"], "fake-owner/fake-private"),            # 頭だけ（前の形）
    (["fake-owner/fake"], "fake-owner/fake-private"),         # 錨なしの一部（前の形）
    (["^fake-owner/fake$"], "fake-owner/fake-private"),       # 名の一部だけ合う
    (["^xfake-owner/fake-private$"], "fake-owner/fake-private"),
    (["[壊れた"], "fake-owner/fake-private"),                  # 読めない正規表現は当たらない（落ちない）
])
def test_名の一部にしか当たらない行は外さない(pats, repo):
    assert not P._matches(pats, repo)


def test_公開の鍵は形の違う行でも公開の照らしを黙って外さない(env, tmp_path):  # noqa: F811
    """安全の守り: public_repos_extra の形の違う行は値の表の照らしが落とすが、公開の照らしは外さない。"""
    table = tmp_path / "values.json"
    env["SKILL_VALUES"] = str(table)
    p = gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL, repo="far-public")
    _fake_gh(env)                                          # GitHub の記録は private（決められない時は公開に倒れるので記録を置く）
    table.write_text(json.dumps({"guard": {"public_repos_extra": ["^fake-owner/"]}}), encoding="utf-8")
    assert "[public]" in deny_reason(env, p)
    table.write_text(json.dumps({"guard": {"public_repos_extra": ["^fake-owner/far$"]}}), encoding="utf-8")
    assert deny_reason(env, p) == ""                       # 全体の形の行は名の一部だけでは公開と見ない


# ── 3. 値の表の型の正本が名の全体の形を照らす ──
@pytest.mark.parametrize("key", REPO_KEYS)
def test_型の正本は_repo_の名の鍵を_repo_names_で照らす(key):
    assert SV.keys_of("guard")[key]["type"] == "repo_names"


@pytest.mark.parametrize("key", REPO_KEYS)
@pytest.mark.parametrize("bad", ["^my-owner/", "my-owner/repo", "^my-owner/repo", "my-owner/repo$",
                                 "^my-owner/repo\\$", "^[壊れた$", 3])
def test_前の形_錨なし_読めない行を値の表の照らしが名指す(key, bad):
    got = SV.check({"guard": {key: ["^ok/ok$", bad]}})
    assert len(got) == 1 and got[0].startswith("guard.%s の" % key) and "名の全体" in got[0]


@pytest.mark.parametrize("good", [["^my-owner/repo$"], ["^my-owner/.*$", "^o/(a|b)$"], ["^o/a\\\\$"], []])
def test_全体の形の行は値の表の照らしを通る(good):
    assert SV.check({"guard": {k: good for k in REPO_KEYS}}) == []


def test_run_の塊の中の_uses_の行は呼び口と見ない():
    wf = "    steps:\n      - run: |\n          uses: ./public-guard\n          deny-words-file: other/x.txt\n"
    assert not P.calls_public_guard(whole(wf), F) and W.deny_words_files(whole(wf), F) == []


@pytest.mark.parametrize("rows", [["^fake-owner/far-public$", "^other/"], ["^other/", "^fake-owner/far-public$"],
                                  ["^fake-owner/far-public$", 3]])
def test_形の違う行が混じっても同じ並びの正しい行は効く_公開(env, tmp_path, rows):  # noqa: F811
    """注入: 形の違う行を 1 つ混ぜる → 値の表の照らしが鍵ごと落としても、正しい行の repo の公開の照らしは外れない。"""
    table = tmp_path / "values.json"
    env["SKILL_VALUES"] = str(table)
    table.write_text(json.dumps({"guard": {"public_repos_extra": rows}}), encoding="utf-8")
    p = gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL, repo="far-public")
    assert "[public]" in deny_reason(env, p)

