"""チェック役: どの窓が見たかは照らさず先端は照らす・札と段を SKILL.md 1 か所から読む（注入の試験）。"""
import os
import subprocess
import sys

import pytest

from test_checker import GREEN, PLUGIN, rules_git, vf

FORM = PLUGIN / "scripts" / "verdict_form.py"
SKILL = PLUGIN / "skills" / "review-pr" / "SKILL.md"


def run(tmp_path, text, *args):
    """作り物の決まりの git（今の SKILL.md の 1 版）を置き、判定の 3 行目をその版にして、初めの判定として照らす。"""
    clone, sha = rules_git.make(tmp_path)
    f = tmp_path / "判定.md"
    f.write_text(text.replace("決まりの版: 0123456789ab", "決まりの版: " + sha[:12]), encoding="utf-8")
    first = ["--first", "なし"] if "--head" in args else []
    return subprocess.run([sys.executable, "-B", str(FORM), str(f), *args, *first], capture_output=True, text=True,
                          env=dict(os.environ, AF_RULES_GIT=str(clone)))


@pytest.mark.parametrize("args", [[], ["--writer", "session_WRITER01"], ["--head"]])
def test_先端が欠けたら形を通さない(tmp_path, args):
    res = run(tmp_path, GREEN, *args)
    assert res.returncode == 2, args


def test_書いた窓が立てた助手の判定も窓では止めない(tmp_path):
    helper = GREEN.replace("session_REVIEW01", "session_WRITER01", 1)
    res = run(tmp_path, helper, "--writer", "session_WRITER01", "--head", "0123456789ab")
    assert res.returncode == 0, res.stdout


def test_レビューの判定は通り_見た先端が違えば赤(tmp_path):
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    assert run(tmp_path / "a", GREEN, "--head", "0123456789abcdef").returncode == 0
    res = run(tmp_path / "b", GREEN, "--head", "fedcba9876543210")
    assert res.returncode == 1 and "先端" in res.stdout, res.stdout


def test_skill_は窓を照らさず理由を書く():
    text = SKILL.read_text(encoding="utf-8")
    assert "どの窓が書き、どの窓が見たかは照らさない" in text
    for old in ["書いた窓が立てた助手は別の目にならない", "1 PR に 1 つのレビューの窓"]:
        assert old not in text, old


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
