"""全体の絵は設計の時に掘り下げる元の図で、合流（main へ入れる）を止めない（オーナーの意図 2026-11-22）。
核 §7・細目 §7・review-pr・判定の形の道具に、絵を合流の条件にする文や点が戻ると red。"""
from pathlib import Path

from saimoku import 全文 as 細目の全文

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "plugins" / "core" / "核.md"
REVIEW = ROOT / "plugins" / "checker" / "skills" / "review-pr" / "SKILL.md"
VERDICT = ROOT / "plugins" / "checker" / "scripts" / "verdict_form.py"
CONTRIB = ROOT / "CONTRIBUTING.md"

戻ってはいけない = ["差がある・照らせない時は止めて聞く", "先に絵を描き", "③の照らし方", "点 13"]


def _節7(text):
    a = text.index("## 7. ")
    b = text.find("\n## ", a + 1)
    return text[a:] if b < 0 else text[a:b]


def test_核_7_は絵を設計の元の図とし合流を止めない():
    s = _節7(CORE.read_text(encoding="utf-8"))
    assert "全体の絵は設計の時に掘り下げる元の図で、合流を止めない" in s
    assert "別の窓のレビュー green・試験が緑で衝突なし" in s
    for w in 戻ってはいけない:
        assert w not in s, w


def test_細目_7_は絵を合流の条件にしない():
    s = 細目の全文()
    assert "合流の前にオーナーへ「入れてよいですか」と聞かない" in s
    assert "合流の条件にしない" in s
    assert "絵と違う・絵が無い・照らせないを理由に止めない" in s
    for w in 戻ってはいけない:
        assert w not in s, w


def test_review_pr_に全体の絵の点が無く_判定の道具も絵の形を求めない():
    r = REVIEW.read_text(encoding="utf-8")
    assert "全体の絵" not in r
    assert "PICTURE" not in VERDICT.read_text(encoding="utf-8")


def test_CONTRIBUTING_は合流の条件を核と細目へ指し絵で止めない():
    c = CONTRIB.read_text(encoding="utf-8")
    assert "核 §7 と細目 §7 の「main へ入れる」" in c
    assert "全体の絵は設計の元の図で、合流を止めない" in c
