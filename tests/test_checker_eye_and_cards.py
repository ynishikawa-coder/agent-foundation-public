"""チェック役: 書いた窓が立てた助手の判定を別の目と取り違えない・札と段を SKILL.md 1 か所から読む（注入の試験）。"""
import os
import subprocess
import sys

import pytest

from test_checker import GREEN, PLUGIN, vf

FORM = PLUGIN / "scripts" / "verdict_form.py"
SKILL = PLUGIN / "skills" / "review-pr" / "SKILL.md"


def run(tmp_path, text, *args, me="cse_REVIEW01"):
    """me は回した窓の環境の id（cse_<x>）。None なら環境から外す。"""
    f = tmp_path / "判定.md"
    f.write_text(text, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_REMOTE_SESSION_ID"}
    if me is not None:
        env["CLAUDE_CODE_REMOTE_SESSION_ID"] = me
    return subprocess.run([sys.executable, "-B", str(FORM), str(f), *args], capture_output=True, text=True, env=env)


@pytest.mark.parametrize("args", [[], ["--head", "0123456789ab"], ["--writer", "session_WRITER01"],
                                  ["--writer", "--head", "0123456789ab"]])
def test_書いた窓か先端が欠けたら形を通さない(tmp_path, args):
    res = run(tmp_path, GREEN, *args)
    assert res.returncode == 2 and "--writer" in res.stderr, args


def test_書いた窓が立てた助手の判定は書いた窓と同じ_id_になり誤り(tmp_path):
    helper = GREEN.replace("session_REVIEW01", "session_WRITER01", 1)
    res = run(tmp_path, helper, "--writer", "session_WRITER01", "--head", "0123456789ab", me="cse_WRITER01")
    assert res.returncode == 1 and "別の目でない" in res.stdout


def test_レビューの窓の判定は通る(tmp_path):
    res = run(tmp_path, GREEN, "--writer", "session_WRITER01", "--head", "0123456789abcdef")
    assert res.returncode == 0, res.stdout


def test_skill_は書いた窓が立てた助手を別の目と言わない():
    text = SKILL.read_text(encoding="utf-8")
    head = text.split("\n---", 1)[0]
    assert "書いた窓が立てた助手は別の目にならない" in head
    assert "書いた窓と別の目を立てる時は読むだけの助手" not in text


def test_札と段は_skill_の行から読み_足した段も通る(tmp_path):
    text = SKILL.read_text(encoding="utf-8")
    assert vf.load_cards(SKILL) == (("止める", "台帳へ", "直った"), ("設計", "整地", "見本", "承認", "実装", "レビュー"))
    alt = tmp_path / "SKILL.md"
    alt.write_text(text.replace("・`レビュー`（", "・`レビュー`・`作り物の段`（"), encoding="utf-8")
    cards = vf.load_cards(alt)
    ok = GREEN.replace("## 所見\n", "## 所見\n- [台帳へ｜作り物の段] 作り物の気づき\n")
    assert vf.check(ok, cards=cards) == []
    assert vf.check(ok)   # 今の SKILL には無い段なので誤り


def test_札の行が読めない時は止まる(tmp_path):
    alt = tmp_path / "SKILL.md"
    alt.write_text("# 作り物\n- 札の話は無い\n", encoding="utf-8")
    with pytest.raises(ValueError):
        vf.load_cards(alt)
