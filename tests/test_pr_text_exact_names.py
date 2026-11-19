"""守りの hook pr_text が、公開の repo の見分けと値の表の repo の名を「含むか」でなく全体の一致で決めるか（注入の試験）。

似た名の action・fork・名を道に含む別の出所・コメントの行・job の名だけの workflow を公開の repo と取り違えない事と、
値の表の repo の名の正規表現が似た名の repo を外さない事を見る。直す前（`uses:\\s*\\S*public-guard\\b` の部分一致・錨なしの
re.search）では、ここの「取り違えない」側の試験が赤になる。
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
sys.path.insert(0, str(ROOT / "public-guard"))
import pr_text as P  # noqa: E402
import patrol  # noqa: E402

from test_pr_text import MAIL, deny_reason, env, gh  # noqa: E402,F401  作り物の箱と GitHub の道具の入力を共に使う

F = patrol.FOUNDATION


def test_土台の名は見回りの正本から読む():
    assert P._foundation() == F


@pytest.mark.parametrize("wf", [
    "      - uses: %s/public-guard@main\n" % F,                                 # 雛形そのもの
    "      - uses: '%s/public-guard@v0.4.18'\n" % F,                            # 版で止めても公開の repo
    '    steps:\n      - name: x\n        uses: "%s/public-guard@main"  # 呼び口\n' % F.upper(),  # 大小・行末のコメント
    "      - uses: ./public-guard\n",                                           # 土台そのもの
])
def test_土台の_action_を呼ぶ_workflow_は公開(wf):
    assert P.calls_public_guard(wf, F)


@pytest.mark.parametrize("wf", [
    "      - uses: someone/not-public-guard@v1\n",                              # 似た名の action
    "      - uses: someone/agent-foundation-public/public-guard@main\n",        # fork
    "      - uses: %s/public-guard-old@main\n" % F,                             # 土台の別の dir
    "      - uses: %s-fork/public-guard@main\n" % F,                            # 名を含む別の repo
    "      - uses: other/x/%s/public-guard@main\n" % F,                         # 名を道に含む別の出所
    "      # - uses: %s/public-guard@main\n" % F,                               # コメントの行
    "jobs:\n  public-guard:\n    steps:\n      - run: echo hi\n",               # job の名だけ
    "      - uses: ./public-guard-copy\n",
])
def test_似た名_他の出所_コメント_job_の名は公開と取り違えない(wf):
    assert not P.calls_public_guard(wf, F)


def test_土台の名が読めない時は道の最後が_public_guard_なら多く照らす向きに倒す():
    assert P.calls_public_guard("      - uses: someone/agent-foundation-public/public-guard@main\n", "")
    assert not P.calls_public_guard("      - uses: someone/not-public-guard@v1\n", "")


@pytest.mark.parametrize("pats,repo,want", [
    (["^fake-owner/fake-private$"], "fake-owner/fake-private", True),
    (["fake-owner/fake-private"], "fake-owner/fake-private", True),
    (["fake-owner/fake-private"], "Fake-Owner/Fake-Private", True),   # GitHub の名は大小を問わない
    (["fake-owner/.*"], "fake-owner/anything", True),
    (["fake-owner/fake-private"], "fake-owner/fake-private-public", False),  # 似た名（錨なしでは外していた）
    (["fake-owner/fake-private"], "xfake-owner/fake-private", False),
    (["^fake-owner/"], "fake-owner/fake-private", False),               # 頭だけの形は全体に当たらない（古い形.json が名指す）
    (["private"], "fake-owner/fake-private", False),
])
def test_値の表の_repo_の名は全体で当てる(pats, repo, want):
    assert P._matches(pats, repo) is want


def test_公開と見る値の表は前の形でも黙って外さない():
    # 1 段目: 錨なしの前の形の行で当たる名は公開と見る（多く照らす向きだけ）
    assert P._public_extra(["^fake-owner/"], "fake-owner/far-public")
    assert not P._public_extra(["^other/"], "fake-owner/far-public")


def test_似た名の_repo_は値の表の外す行で外れない(env, tmp_path):  # noqa: F811
    table = tmp_path / "values.json"
    env["SKILL_VALUES"] = str(table)
    table.write_text(json.dumps({"guard": {"pr_words_exempt_repos": ["fake-owner/fake"]}}), encoding="utf-8")
    body = "## 整地（根治の 4 段）\n整地: 不要（試し）\n連絡: session_01CCCCCCCCCCCCCCCCCCCCCCCC\n"
    assert deny_reason(env, gh("update_pull_request", repo="fake", pullNumber=1, body=body)) == ""
    assert "[words]" in deny_reason(env, gh("update_pull_request", repo="fake-private", pullNumber=1, body=body))
