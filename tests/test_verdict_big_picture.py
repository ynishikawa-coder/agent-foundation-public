"""点 13（全体の絵）: 判定の形の道具が、全体の絵を照らさずに通す判定を赤にするか（注入の試験）。"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("_checker_base", Path(__file__).resolve().parent / "test_checker.py")
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
vf, GREEN = _base.vf, _base.GREEN


# 注入の試験: 点 13（全体の絵）を照らさずに通す形をわざと入れ、形の道具が赤にする事を見る。


def test_全体の絵の点は_N_A_にできない():
    errs = vf.check(GREEN.replace("- 13 全体の絵: pass（差なし・版 2026-11-19.1）", "- 13 全体の絵: N/A"), writer="session_WRITER01")
    assert any("点 13" in e and "N/A" in e for e in errs), errs


def test_全体の絵の_pass_は差なしと版を書く():
    for bad in ["pass", "pass（見た）", "pass（差なし）", "pass（版 2026-11-19.1）"]:
        errs = vf.check(GREEN.replace("pass（差なし・版 2026-11-19.1）", bad), writer="session_WRITER01")
        assert any("点 13" in e for e in errs), (bad, errs)


def test_全体の絵に差があれば_red():
    text = GREEN.replace("- 13 全体の絵: pass（差なし・版 2026-11-19.1）", "- 13 全体の絵: fail（差 2 件）")
    assert any("判定は red" in e for e in vf.check(text, writer="session_WRITER01"))
    red = text.replace("判定: green", "判定: red").replace("## verdict\ngreen", "## verdict\nred\n直し: 細目 §3「まず構造を疑う」").replace(
        "- [台帳へ｜整地] 作り物の気づき", "- [止める｜設計] 全体の絵と差 2 件。main へ入れずに止め、差を見せてオーナーに決めてもらう")
    assert vf.check(red, writer="session_WRITER01") == []


def test_全体の絵が複数なら全部の名と版を書いた_pass_だけ通る():
    ok = "pass（差なし・版 うみ 2026-11-19.1／やま 2026-11-20.1）"
    assert not [e for e in vf.check(GREEN.replace("pass（差なし・版 2026-11-19.1）", ok), writer="session_WRITER01") if "点 13" in e]
    for bad in ["pass（差なし・版 うみ 2026-11-19.1／やま）", "pass（差なし・版 うみ／やま）", "pass（差なし・版 うみ 2026-11-19.1／）"]:
        errs = vf.check(GREEN.replace("pass（差なし・版 2026-11-19.1）", bad), writer="session_WRITER01")
        assert any("点 13" in e for e in errs), (bad, errs)
