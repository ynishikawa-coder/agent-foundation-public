"""公開の検査の照合は、全部 1 つの正規化（guard.normalize: NFKC・書式の字を除く）を通る（注入の試験）。

前の形: 置かない語・平文の顧客の語は lower だけで、全角・半角のカナ・互換の字・幅の無い空白ですり抜けた
（束の照合だけ NFKC）。形（電話など）も全角ですり抜けた。
"""
import base64
import hashlib
import hmac

import pytest

from public_guard_box import PHONE, guard, wide


def _bundle(words, key=b"k" * 32):
    digests = {hmac.new(key, w.encode(), hashlib.sha256).digest()[:guard.DIGEST] for w in words}
    return guard.decode_bundle("%s.%s.%s" % (guard.BUNDLE_PREFIX, base64.urlsafe_b64encode(key).decode(),
                                             base64.urlsafe_b64encode(b"".join(sorted(digests))).decode()))


ZW = "​"   # 幅の無い空白


def _all_hit():
    """全部の照合が、互換の字で書いた物に当たるか。"""
    return {
        "置かない語": bool(guard.word_hits("x", "本文 " + wide("FAKEWORD"), ["fakeword"])),
        "置かない語（半角カナ）": bool(guard.word_hits("x", "本文 ｶｷｸｹ", ["カキクケ"])),
        "置かない語（幅の無い空白）": bool(guard.word_hits("x", "fake" + ZW + "word", ["fakeword"])),
        "顧客の語（平文）": bool(guard.customer_hits("x", wide("FakeCust") + " さん", ["fakecust"], None)),
        "顧客の語（束）": bool(guard.customer_hits("x", "ｶｷｸｹ さん", [], _bundle(["カキクケ"]))),
        "個人の情報の形": bool(guard.pattern_hits("x", "電話 " + wide(PHONE))),
        "秘密の形": bool(guard.secret_labels("鍵 " + wide("ghp_" + "c" * 36))),
    }


def test_全部の照合が互換の字にも当たる():
    got = _all_hit()
    assert all(got.values()), got


def test_注入_正規化を外すと全部の照合がすり抜ける(monkeypatch):
    """正規化を 1 つの関数に寄せた事の確かめ: guard.normalize を何もしない物に替えると、全部の照合が当たらなくなる
    （どれかが別の正規化を持っていれば、その照合だけ当たり続ける）。"""
    monkeypatch.setattr(guard, "normalize", lambda text: text or "")
    got = _all_hit()
    assert not any(got.values()), got


@pytest.mark.parametrize("word", ["fakeword", "ＦＡＫＥＷＯＲＤ"])
def test_表の語の側も同じ正規化を通る(word):
    assert guard.word_hits("x", "本文 fakeword", [word])
