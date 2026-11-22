"""閉じた語彙の注入の試験（判定の形）: verdict の行と 1 行目の判定は review-pr の SKILL.md の雛形の形だけを通す。

前の形は `green（blocked: …）`（blocked は red だけの決まり）を受け、blocked と見て止める札・点の fail との照らしを飛ばした。
雛形に無い判定の字（yellow など）も、知らない値として拒む。
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("verdict_form_cv", ROOT / "plugins" / "checker" / "scripts" / "verdict_form.py")
vf = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(vf)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_checker import GREEN, RED  # noqa: E402


def test_雛形の形は_3_つで_blocked_は_red_だけ():
    assert vf.load_verdicts() == [("green", False), ("red", False), ("red", True)]


@pytest.mark.parametrize("line", ["green（blocked: 物差しが回らない）", "yellow", "green です", "Green", "red（blocked: ）"])
def test_雛形に無い_verdict_の行は誤り(line):
    text = GREEN.replace("## verdict\ngreen", "## verdict\n" + line)
    errs = vf.check(text)
    assert any("判定の形の雛形" in e for e in errs), errs


def test_green_に_blocked_を付けて止める札の照らしを飛ばせない():
    """止める札が在るのに green（blocked: …）で出すと、前は blocked として判定の照らしを飛ばした。"""
    text = GREEN.replace("## verdict\ngreen", "## verdict\ngreen（blocked: 測れない）").replace(
        "- [台帳へ｜整地] 作り物の気づき", "- [止める｜実装] 作り物の止め")
    errs = vf.check(text)
    assert any("判定は red" in e for e in errs), errs


def test_1_行目の判定の字も雛形の判定だけ():
    text = GREEN.replace("判定: green", "判定: yellow")
    errs = vf.check(text)
    assert any("1 行目の判定 yellow" in e for e in errs), errs


def test_red_の_blocked_は今までどおり通る():
    text = RED.replace("## verdict\nred\n直し: 細目 §3「まず構造を疑う」", "## verdict\nred（blocked: 物差しが回らない）")
    assert vf.check(text) == []


def test_雛形の_verdict_の行を読めなければ止まる(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text("# 無い\n", encoding="utf-8")
    with pytest.raises(ValueError):
        vf.load_verdicts(p)
