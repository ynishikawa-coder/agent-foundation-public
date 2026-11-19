"""guard の見張りが正本を読めない時（plugin の版がずれた窓）の扱いを、安全の守りかどうかで揃える。
- 窓の題の形（outbound の title・正本は session-watch）: 照らせない時は止めず、出した後に知らせる（黙って抜けない）。
- 問いのページ（qa_page・正本は docs-kit の check.mjs）: オーナーや相手に直に出る物なので、照らせない時は止めたまま。
- 整地の欄（pr_text）: 本文の注記とコードの囲みを消すのは cleanup_text の 1 か所。
正本をわざと消す・古くする・壊して、入口（guard.py pre／post）から当てる。
"""
import sys

from test_guard import PLUGIN, STATE_PAGE, deny_reason, env, hook, publish, without_check  # noqa: F401
from test_guard_outbound import SET_TITLE, CREATE, tool

BAD_TITLE = "作り物の題"          # 種類の印の無い崩れた題


def post_notice(env, payload):
    return hook(env, "post", payload).get("additionalContext", "")


def test_題の形の正本が無い時は止めず知らせる(env, tmp_path):
    old = tmp_path / "session_watch.py"
    old.write_text("import re\n", encoding="utf-8")            # 題の形の見分けの無い古い版
    broke = tmp_path / "broke.py"
    broke.write_text("raise RuntimeError('作り物の故障')\n", encoding="utf-8")
    for path, word in ((tmp_path / "無い.py", "見つからない"), (old, "古い版"), (broke, "読めない")):
        e = dict(env, AF_SESSION_WATCH=str(path))
        for p in (tool(SET_TITLE, session_id="s", title=BAD_TITLE), tool(CREATE, title=BAD_TITLE, prompt="作り物の頼み")):
            assert deny_reason(e, p) == ""
            note = post_notice(e, p)
            assert "照らさずに通した" in note and word in note and "止めていない" in note


def test_題の形の正本が在れば崩れた題は止め知らせない(env):
    p = tool(SET_TITLE, session_id="s", title=BAD_TITLE)
    assert deny_reason(env, p) != ""
    assert post_notice(env, tool(SET_TITLE, session_id="s", title="🤖 作り物の作業")) == ""


def test_問いのページは検査が無い時も止めたまま(env, tmp_path):
    page = tmp_path / "kakunin.html"
    page.write_text(STATE_PAGE, encoding="utf-8")
    assert "緑を確かめられない" in deny_reason(without_check(env, tmp_path), publish(page))


def test_整地の本文を消すのは_1_か所():
    src = (PLUGIN / "scripts" / "pr_text.py").read_text(encoding="utf-8")
    assert src.count("FENCE.sub(") == 1, "本文の注記・コードの囲みを消す処理が 2 か所に戻った"
