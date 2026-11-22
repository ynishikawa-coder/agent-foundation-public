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
    assert "全体の絵は設計の元の図で合流を止めず" in s
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


BIG = ROOT / "plugins" / "docs-kit" / "skills" / "big-picture" / "SKILL.md"
SPEC = ROOT / "plugins" / "dev-flow" / "skills" / "spec-doc" / "SKILL.md"
PICK = ROOT / "plugins" / "guard" / "scripts" / "pick_one.py"
GUARD = ROOT / "plugins" / "guard" / "skills" / "guard-rules" / "SKILL.md"


def test_設計図どおりかは設計の仕事の終わりに_1_回照らして完了の報告に書く():
    """決定 2026-11-22: PR ごとに照らさない・絵の無い仕事は照らさない・作り方のずれは AI が直す・設計を変える時だけ合意し直す。"""
    k = _節7(CORE.read_text(encoding="utf-8"))
    assert "全体の絵は設計の元の図で合流を止めず、設計の仕事の終わりに 1 回照らし報告に書く。" in k
    s = 細目の全文()
    for w in ["**設計図どおりかの照らし** — 合意した設計の仕事（案件・段の区切り）が全部終わった時に 1 回、AI が箱ごとに確かめ、完了の報告に「設計図どおり」か「差とその扱い」を 1 か所書く。",
              "PR ごとには照らさず、合意した絵の無い仕事は照らさない。",
              "作り方のずれは AI が設計どおりに直す（聞かない）。",
              "設計そのものを変える時だけ、絵に戻ってオーナーと合意し直す。"]:
        assert w in s, w
    b = BIG.read_text(encoding="utf-8")
    assert "3. **設計の仕事が終わった時（と「絵どおりか照らして」と頼まれた時）**" in b
    assert "途中の細部の変化は AI が絵を直して最新に保つ（聞かない）。箱・流れ・意図が変わる時だけオーナーの OK を取って版を上げる。" in b
    assert "絵を直したい時は OK を取って版を上げる" not in b


def test_絵が無い事を理由に止めず_原因の見立ては絵があれば絵の上で():
    sp = SPEC.read_text(encoding="utf-8")
    assert "先に big-picture で絵を描いて OK を取る" not in sp
    assert "全体の絵が無い仕組みでも、絵が無い事を理由に止めない" in sp
    for f in (PICK, GUARD):
        t = f.read_text(encoding="utf-8")
        assert "全体の絵の上で" not in t, f
        assert "（合意した全体の絵があれば絵の上で）" in t, f
