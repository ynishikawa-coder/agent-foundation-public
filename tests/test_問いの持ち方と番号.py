"""オーナーへの問いの持ち方と番号の約束（決定 2026-11-22）。古い形を戻すと赤。"""
from pathlib import Path

from saimoku import 全文 as 細目の全文

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "core"


def _節(text, n):
    a = text.index(f"## {n}. ")
    b = text.find("\n## ", a + 1)
    return text[a:] if b < 0 else text[a:b]


def test_答えの無い問いを時間で数えて親が知らせ直す仕組みを前提にしない():
    """「1 時間答えの無い問いは親が知らせ直す」形を細目 §4・guard の注に戻すと赤（決定 2026-11-22）。"""
    s4d = _節(細目の全文(), 4)
    assert "時間で数えて親が知らせ直す仕組みは持たない" in (ROOT / "plugins" / "guard" / "scripts" / "unanswered.py").read_text(encoding="utf-8")
    unanswered = (ROOT / "plugins" / "guard" / "scripts" / "unanswered.py").read_text(encoding="utf-8")
    for text in (s4d, unanswered):
        assert "1 時間答えの無い問い" not in text and "1時間答えの無い問い" not in text


def test_オーナーへ確かめる事は通し番号と中身で並べ_出さない番号は節の番号と窓の_id():
    """「番号は出さない」だけの形に核 §2 を戻す・細目 §4 の「番号で並べる」を消す・細目 §2 と重ねると赤（決定 2026-11-22「番号振って」）。"""
    s2 = _節((PLUGIN / "核.md").read_text(encoding="utf-8"), 2)
    for word in ["初めて読む人が分かる言葉で書き", "物は本当の名で呼ぶ", "例え話にせず具体の意味を添え",
                 "決まりの言葉・AI 同士の呼び名・節番号・窓 id は出さず", "確かめる事は通し番号＋中身"]:
        assert word in s2, f"核 §2 に無い: {word}"
    assert "呼び名・番号は出さない" not in s2, "核 §2 が番号を一律に出さない形に戻った"
    s4d = _節(細目の全文(), 4)
    for word in ["**番号で並べる**", "オーナーへ確かめる事は通し番号と同じ行の中身（物の名と何を確かめるか）で並べる",
                 "番号の答えは中身に戻す"]:
        assert word in s4d, f"細目 §4 に無い: {word}"
    s2d = _節(細目の全文(), 2)
    assert "番号" not in s2d, "番号の形が細目 §2 と §4 に重なった（§4 の「番号で並べる」1 か所にする）"
    rules = (ROOT / "plugins" / "guard" / "skills" / "guard-rules" / "SKILL.md").read_text(encoding="utf-8")
    assert "オーナーが番号で返した答え（「1 は残す」）を他の窓へ渡す時も、番号を中身に戻して渡す" in rules
