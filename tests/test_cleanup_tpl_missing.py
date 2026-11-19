"""整地の雛形（dev-flow の 整地受領証.template.md）が無い・読めない時、guard の pr_text は PR 本文の整地の欄を照らせない。
その時は止めず（PR 本文まで止めない＝オーナーの同意の無い止める範囲の広がりを作らない）、出した後に知らせる。
公開の検査が無い時は今までどおり止める（安全の守り・tests/test_pr_text.py が縛る）。雛形をわざと消す・壊して、
入口（guard.py pre／post）から当てる。
"""
from test_pr_text import (_fake_gh, cleanup_body, deny_reason, env, gh)  # noqa: F401
from test_verdict_tool_missing import post_notice


def pr(body):
    return gh("create_pull_request", title="作り物", head="b", base="main", body=body)


def test_雛形が無い時は_PR_本文を止めず知らせる(env, tmp_path):
    _fake_gh(env)
    broken = tmp_path / "壊れた.md"
    broken.write_text("見出しの無い作り物\n", encoding="utf-8")
    for path, word in ((tmp_path / "無い.md", "見つからない"), (broken, "読めない")):
        env["AF_CLEANUP_TEMPLATE"] = str(path)
        payload = pr("## 何をどう変えたか\n作り物の直し。整地の欄が無い。\n")
        assert deny_reason(env, payload) == ""
        note = post_notice(env, payload)
        assert "整地の欄を照らさずに通した" in note and word in note and "止めていない" in note


def test_雛形が在れば欄を照らし知らせない(env):
    _fake_gh(env)
    payload = pr("## 何をどう変えたか\n作り物の直し。整地の欄が無い。\n")
    assert "整地の見出しが無い" in deny_reason(env, payload)
    assert post_notice(env, pr(cleanup_body())) == ""


def test_整地が要らない本文は雛形が無くても知らせない(env, tmp_path):
    _fake_gh(env)
    env["AF_CLEANUP_TEMPLATE"] = str(tmp_path / "無い.md")
    payload = pr("## 何をどう変えたか\n誤字の直し。\n\n整地: 不要（振る舞いを変えない誤字の直し）\n")
    assert deny_reason(env, payload) == "" and post_notice(env, payload) == ""

