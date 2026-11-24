"""全体の絵は設計の時に掘り下げる元の図で、合流（main へ入れる）を止めない（オーナーの意図 2026-11-22）。
核 §7・細目 §7・review-pr に、絵を合流の条件にする文や点が戻ると red。"""
import re
from pathlib import Path

from test_core_plugin import used_texts

from saimoku import 全文 as 細目の全文

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "plugins" / "core" / "核.md"
REVIEW = ROOT / "plugins" / "checker" / "skills" / "review-pr" / "SKILL.md"
CONTRIB = ROOT / "CONTRIBUTING.md"

合流の_1_行 = ("main へ入れる前に、使う側に届く誤りが無い事を、書いた窓と別の目で確かめる。"
              "機械で証明できる所（版の束ね・CHANGELOG の形）は機械の緑がその確かめ。")
戻ってはいけない = ["差がある・照らせない時は止めて聞く", "先に絵を描き", "③の照らし方", "点 13"]


def _節7(text):
    a = text.index("## 7. ")
    b = text.find("\n## ", a + 1)
    return text[a:] if b < 0 else text[a:b]


def test_核_7_は絵を設計の元の図とし合流を止めない():
    s = _節7(CORE.read_text(encoding="utf-8"))
    assert "全体の絵は設計の元の図で合流を止めず" in s
    assert 合流の_1_行 in s
    for w in 戻ってはいけない:
        assert w not in s, w


def test_細目_7_は絵を合流の条件にしない():
    s = 細目の全文()
    assert "合流の前にオーナーへ「入れてよいですか」と聞かない" in s
    assert "合流の条件にしない" in s
    assert "絵と違う・絵が無い・照らせないを理由に止めない" in s
    for w in 戻ってはいけない:
        assert w not in s, w


def test_review_pr_に全体の絵の点が無い():
    r = REVIEW.read_text(encoding="utf-8")
    assert "全体の絵" not in r


def test_CONTRIBUTING_は合流の条件を核と細目へ指し絵で止めない():
    c = CONTRIB.read_text(encoding="utf-8")
    assert "核 §7 と細目 §7 の「main へ入れる」" in c
    assert "全体の絵は設計の元の図で、合流を止めない" in c


BIG = ROOT / "plugins" / "docs-kit" / "skills" / "big-picture" / "SKILL.md"
SPEC = ROOT / "plugins" / "dev-flow" / "skills" / "spec-doc" / "SKILL.md"


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


def test_絵が無い事を理由に止めない():
    sp = SPEC.read_text(encoding="utf-8")
    assert "先に big-picture で絵を描いて OK を取る" not in sp
    assert "全体の絵が無い仕組みでも、絵が無い事を理由に止めない" in sp


# 合流の条件を核 §7 の外で言い直す写し（「レビュー green・試験が緑」の類・数で数える「n 回目」の印）。
# 写しは核が変わっても付いて来ず、2 か所が食い違う（review-pr の 9 点目・細目 §7 と CONTRIBUTING §2 で起きた）。
合流の写し = re.compile(r"レビュー(?:の)?\s*green[^。\n]{0,16}試験が緑|別窓レビュー|前回と同じ類（")


def test_合流の写しの見分けは注入を拾い_核を指す文は拾わない():
    for bad in ["今の先端にレビュー green・試験が緑で衝突なし", "今の先端にレビューの green・試験が緑・衝突なし",
                "条件は核 §7（別窓レビュー green・試験が緑）", "- [止める｜実装] 前回と同じ類（3 回目） a.py"]:
        assert 合流の写し.search(bad), bad
    for ok in ["コードの完了と main へ入れる条件は核 §7・細目 §7 が決める（ここに写さない）。",
               "核 §7 の確かめが済み衝突が無ければ、書いた窓が squash で入れる", "試験が緑", 合流の_1_行]:
        assert not 合流の写し.search(ok), ok


def test_合流の条件は核_7_の_1_か所で_土台の中に写しが無い():
    hits = [f"{rel}: {m.group(0)}" for rel, text in used_texts() if (m := 合流の写し.search(text))]
    assert not hits, hits
    assert 合流の_1_行 in _節7(CORE.read_text(encoding="utf-8"))
