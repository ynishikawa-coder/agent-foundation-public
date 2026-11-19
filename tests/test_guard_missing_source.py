"""guard の見張りが正本を読めない時（plugin の版がずれた窓）の扱いを、安全の守りかどうかで揃える。
- 窓の題の形（outbound の title・正本は session-watch）: 照らせない時は止めず、出した後に知らせる（黙って抜けない）。
- 問いのページ（qa_page・正本は docs-kit の check.mjs）: オーナーや相手に直に出る物なので、照らせない時は止めたまま。
- 整地の欄（pr_text）: 本文の注記とコードの囲みを消すのは strip_notes の 1 か所（本文も雛形の置き場の字もここを読む）。
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
    """注記（COMMENT）とコードの囲み（FENCE）の .sub は strip_notes の中だけ。片方だけ写しても赤。"""
    import ast
    src = (PLUGIN / "scripts" / "pr_text.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    owner = {}
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for n in ast.walk(fn):
                owner.setdefault(id(n), fn.name)
    outside = []
    for n in ast.walk(tree):
        if (isinstance(n, ast.Attribute) and n.attr == "sub" and isinstance(n.value, ast.Name)
                and n.value.id in ("COMMENT", "FENCE") and owner.get(id(n)) != "strip_notes"):
            outside.append("%s.sub（%d 行・%s）" % (n.value.id, n.lineno, owner.get(id(n), "外")))
    assert not outside, "本文の注記・コードの囲みを消す処理が strip_notes の外に写った: %s" % outside


def test_消しの_1_か所の試験は写しを拒む(tmp_path, monkeypatch):
    """注入: COMMENT.sub だけ・FENCE.sub だけを別の所へ写した版を、上の試験が赤にする。"""
    import pytest
    src = (PLUGIN / "scripts" / "pr_text.py").read_text(encoding="utf-8")
    for leak in ('COMMENT.sub("", "x")', 'FENCE.sub("", "x")'):
        fake = tmp_path / leak[:7] / "scripts"
        fake.mkdir(parents=True)
        (fake / "pr_text.py").write_text(src + "\n\ndef _copy():\n    return %s\n" % leak, encoding="utf-8")
        monkeypatch.setattr(sys.modules[__name__], "PLUGIN", fake.parent)
        with pytest.raises(AssertionError, match="strip_notes の外に写った"):
            test_整地の本文を消すのは_1_か所()
