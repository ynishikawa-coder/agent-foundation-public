"""オーナーの決定から main の直しの持ち主が生まれる道を、細目 §8 の 1 か所で照らす。

意図: オーナーが「畳む」「変える」と決めた事が、main の物まで届いて片付く。
課題: 決定が決定の記録に入るだけで、畳む PR が閉じられると誰も持たず、main に畳むはずの物が残って直され続けた。
原因: 決定を書く段（細目 §8「決めた事」）にも台帳の行の出どころにも、決定から原因の台帳の行（持ち主と行き先）を作る道が無かった。
ここでは、§8 の「決めた事」が、main の物を変える・畳む決定を書く時に台帳の行にもすると言い切っている事を照らす。
文を消す・弱める（「できれば」・別の時に回す・後ろに打ち消しの句を足す）と赤。§8 から畳んだ「決まりの文の書き方」が
細目のどの節・核・振る舞いの既定に戻っても赤（正本は skill register-rule）。
"""
from pathlib import Path

from saimoku import 全文

ROOT = Path(__file__).resolve().parent.parent
決定から台帳へ = "main の物を変える・畳む決定は、書く時に原因の台帳の行にもする。"
畳んだ写し = "決まりの文には今の結論だけを書き"
CORE = ROOT / "plugins" / "core"


def _毎回読む物(saimoku: str) -> str:
    """細目の全文と、毎回差し込む核・振る舞いの既定。畳んだ写しはこのどこにも戻さない。"""
    rest = "".join((CORE / n).read_text(encoding="utf-8") for n in ("核.md", "振る舞い.md"))
    return saimoku + rest


def _節8(text: str) -> str:
    head = "## 8. 記録"
    assert text.count(head) == 1, "細目 §8 の見出しが 1 つでない"
    body = text.split(head, 1)[1]
    return body.split("\n## ", 1)[0]


def _照らす(text: str) -> None:
    s8 = _節8(text)
    lines = [ln for ln in s8.splitlines() if ln.startswith("- **決めた事**")]
    assert len(lines) == 1, "細目 §8 の「決めた事」がちょうど 1 行でない"
    assert 決定から台帳へ in lines[0], "決定を書く段に、main の物を変える・畳む決定を台帳の行にする道が無い"
    assert lines[0].rstrip().endswith(決定から台帳へ), "「決めた事」の道の文の後ろに、道を打ち消す・外す句が足された"
    assert 畳んだ写し not in _毎回読む物(text), "細目・核・振る舞いの既定に、skill register-rule が正本の「決まりの文の書き方」の写しが戻った"


def test_決定を書く時に_main_を変える決定は台帳の行にもする():
    _照らす(全文())


def test_決まりの文の書き方の正本は_register_rule():
    s = (ROOT / "plugins" / "dev-flow" / "skills" / "register-rule" / "SKILL.md").read_text(encoding="utf-8")
    assert "規律の文は今の結論（振る舞い）だけ。オーナーの原文・日付・出所・経緯" in s


def test_注入_道を消す_弱める_写しを戻すと赤():
    good = 全文()
    bads = {
        "消す": good.replace(決定から台帳へ, ""),
        "弱める": good.replace(決定から台帳へ, "main の物を変える・畳む決定は、できれば後で原因の台帳の行にする。"),
        "打ち消しの句を足す": good.replace(決定から台帳へ, 決定から台帳へ + "ただし急ぐ時は載せなくてよい。"),
        "写しを戻す": good.replace(決定から台帳へ, 決定から台帳へ + 畳んだ写し + "、日付・原文・経緯を書かない。"),
        "写しを別の節に戻す": good.replace("## 5. 返事の形", "## 5. 返事の形\n\n- " + 畳んだ写し + "、日付・原文・経緯を書かない。\n", 1),
    }
    for name, bad in bads.items():
        assert bad != good, name
        try:
            _照らす(bad)
        except AssertionError:
            continue
        raise AssertionError(f"{name} を入れても赤にならない")
