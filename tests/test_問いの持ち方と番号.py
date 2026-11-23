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
    unanswered = (ROOT / "plugins" / "guard" / "scripts" / "unanswered.py").read_text(encoding="utf-8")
    assert "時間で数えて親が知らせ直す仕組みは持たない" in unanswered
    for text in (s4d, unanswered):
        assert "1 時間答えの無い問い" not in text and "1時間答えの無い問い" not in text


# 核 §2 の守る中身。言い換えで 1 つでも抜けると赤（抜けた語を名指しする）。
# 核 §2 は「中身の無い番号は出さない」と文の中で限る。通し番号＋中身の形は細目 §4 の「番号で並べる」1 か所に置く。
核2の守る中身 = [
    "返事・実況は日本語",
    "初めて読む人がそれだけで分かる言葉で書く",
    "物は本当の名で呼ぶ",
    "開発・業界の用語は例え話にせず具体の意味を添え",
    "決まりの中だけの言葉",
    "AI 同士の呼び名",
    "中身の無い番号は出さない",
]


def _核2の抜け(s2):
    return [w for w in 核2の守る中身 if w not in s2]


def test_核2の守る中身が全部在る():
    """核 §2 を言い換えて中身（それだけで・開発・業界の・決まりの中だけの・番号は出さない）を落とすと赤（レビュー 2026-11-23）。"""
    s2 = _節((PLUGIN / "核.md").read_text(encoding="utf-8"), 2)
    assert _核2の抜け(s2) == [], f"核 §2 に無い: {_核2の抜け(s2)}"


def test_核2の守る中身を1つ抜いた文は拒まれる():
    """注入: 守る中身を 1 つずつ抜いた文を作り、どれも抜けとして名指しされる事を確かめる。"""
    s2 = _節((PLUGIN / "核.md").read_text(encoding="utf-8"), 2)
    for w in 核2の守る中身:
        broken = s2.replace(w, "")
        assert w in _核2の抜け(broken), f"{w} を抜いても拒まれない"


def test_オーナーへ確かめる事は通し番号と中身で並べ_形は細目4の1か所():
    """細目 §4 の「番号で並べる」を消す・細目 §2 と重ねる・guard-rules の戻す文を消すと赤（決定 2026-11-22「番号振って」）。"""
    s4d = _節(細目の全文(), 4)
    for word in ["**番号で並べる**", "番号には同じ行に中身（物の名と何か）を添え",
                 "オーナーへ確かめる事は通し番号で並べる", "番号の答えは中身に戻す"]:
        assert word in s4d, f"細目 §4 に無い: {word}"
    s2d = _節(細目の全文(), 2)
    assert "窓の中だけの呼び名は、初めて出す所で括弧の注を付ける" in s2d
    assert "番号" not in s2d, "番号の形が細目 §2 と §4 に重なった（§4 の「番号で並べる」1 か所にする）"
    rules = (ROOT / "plugins" / "guard" / "skills" / "guard-rules" / "SKILL.md").read_text(encoding="utf-8")
    for word in ["番号にそれが何か（物の名と中身）を同じ文で添える",
                 "オーナーが番号で返した答え（「1 は残す」）を他の窓へ渡す時も、番号を中身に戻して渡す"]:
        assert word in rules, f"guard-rules に無い: {word}"


def _核2と細目4の食い違い(s2, s4d):
    """核 §2 が番号を限り無しに禁じ、細目 §4 が通し番号で並べさせると、核だけ読む窓は番号で並べるのを禁止と読む。"""
    if "通し番号で並べる" in s4d and "番号は出さない" in s2 and "中身の無い番号は出さない" not in s2:
        return ["核 §2 の「番号は出さない」に「中身の無い」の限りが無く、細目 §4 の「通し番号で並べる」と食い違う"]
    return []


def test_核2の番号の禁止と細目4の通し番号は食い違わない():
    """核 §2 と細目 §4 を並べて読み、番号の決まりが食い違わない事（レビュー 2026-11-23）。"""
    s2 = _節((PLUGIN / "核.md").read_text(encoding="utf-8"), 2)
    assert _核2と細目4の食い違い(s2, _節(細目の全文(), 4)) == []


def test_核2から中身の無いの限りを外すと食い違いとして拒まれる():
    """注入: 核 §2 から「中身の無い」を外した文は、細目 §4 と食い違うと名指しされる。"""
    s2 = _節((PLUGIN / "核.md").read_text(encoding="utf-8"), 2)
    broken = s2.replace("中身の無い番号は出さない", "番号は出さない")
    assert broken != s2
    assert _核2と細目4の食い違い(broken, _節(細目の全文(), 4)) != []
