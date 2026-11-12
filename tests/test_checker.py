"""チェック役（plugins/checker）の判定の形の道具が、作り物の判定で合う／合わないを見る。"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "checker"

spec = importlib.util.spec_from_file_location("verdict_form", PLUGIN / "scripts" / "verdict_form.py")
vf = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True   # 写しの置き場（plugins/）に __pycache__ を作らない＝写しの照らしを汚さない
spec.loader.exec_module(vf)

GREEN = """レビューした窓: session_REVIEW01 判定: green
見た先端: 0123456789ab
job: 作り物

## verdict
green

## 所見
- [後の便｜整地] 作り物の気づき
"""

RED = """レビューした窓: session_REVIEW01 判定: red
見た先端: 0123456789ab

## verdict
red

## 所見
- [止める｜実装] plugins/x.py — 作り物の欠け
- [後の便｜設計] 作り物の気づき
"""


def test_型どおりの判定は通る():
    assert vf.check(GREEN, writer="session_WRITER01", head="0123456789abcdef") == []
    assert vf.check(RED, writer="session_WRITER01") == []


def test_書いた窓とレビューした窓が同じなら誤り():
    errs = vf.check(GREEN, writer="session_REVIEW01")
    assert any("別の目" in e for e in errs)


def test_止めるが在るのに_green_は誤り():
    errs = vf.check(GREEN.replace("[後の便｜整地]", "[止める｜実装]"))
    assert any("判定は red" in e for e in errs)


def test_見た先端が今の先端と違えば誤り():
    errs = vf.check(GREEN, head="fedcba9876543210")
    assert any("見た先端" in e for e in errs)


def test_blocked_の_red_は止めるが無くてよい():
    text = RED.replace("## verdict\nred", "## verdict\nred（blocked: 物差しが回らない）").replace(
        "- [止める｜実装] plugins/x.py — 作り物の欠け\n", "")
    assert vf.check(text) == []


def test_札と形の崩れを拾う():
    errs = vf.check("レビューした窓: 自分 判定: ok\n\n## verdict\nたぶん良い\n\n## 所見\n- 良さそう\n")
    assert len(errs) >= 4


def test_skill_が判定の形の道具を指す():
    skill = (PLUGIN / "skills" / "review-pr" / "SKILL.md").read_text(encoding="utf-8")
    assert "verdict_form.py" in skill
    assert json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["name"] == "checker"


def test_見る点が写す元の一般の観点を全部持つ():
    skill = (PLUGIN / "skills" / "review-pr" / "SKILL.md").read_text(encoding="utf-8")
    for word in [
        "オーナーの原文",                       # 依頼文の範囲が原文より縮んでいないか
        "本番の効き目",                         # 直したを本番の効き目で確かめたか
        "壊すと赤・戻すと緑",                   # 歯の実証
        "守備範囲", "迂回",                      # 退役した仕組み・新しい関所の迂回
        "呼ぶ側と呼ばれる側",                   # 共通の仕組みの参照切れ
        "except: pass", "shell=True", "set -euo pipefail", "未クォート", "await",  # 言語ごとの点
    ]:
        assert word in skill, f"見る点に無い: {word}"
    points = [l.split("|")[1].strip().split(" ")[0] for l in skill.splitlines() if l.startswith("| ") and l.split("|")[1].strip()[:2].strip().isdigit()]
    assert points == [str(i) for i in range(1, 12)], points
