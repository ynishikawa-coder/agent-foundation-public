"""細目を節の名で引いて読む道と、細目の聞く線が守りの上限と合う事を照らす。

意図: 窓が細目の file を丸ごと読まず、要る 1 節だけ読む。細目の問いの形は守り（guard）の上限と食い違わない。
課題: 差し込みの案内が「番号で始まる file を Read」＝ 1 file を丸ごと読ませていた。細目「聞き方」が画面の問いの前提を
「1〜2 文」とし、guard の ask_question_max_sentences（1 文）とずれていた。
原因: 案内も細目の数も、実の節・守りの値と照らす物が無かった（片方だけ変えても緑）。
"""
import importlib.util
import re
import sys
from pathlib import Path

from saimoku import DIR, kaku

ROOT = Path(__file__).resolve().parent.parent


def _guard_defaults():
    sys.path.insert(0, str(ROOT / "plugins/guard/scripts"))
    try:
        spec = importlib.util.spec_from_file_location("gc_for_setsu", ROOT / "plugins/guard/scripts/guard_common.py")
        gc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gc)
        return gc.DEFAULTS
    finally:
        sys.path.pop(0)


def 節の名(text: str) -> set[str]:
    """細目の節の名（`- **名** —` の行の `**名**`）。"""
    return set(re.findall(r"^- (\*\*[^*\n]+\*\*) —", text, re.M))


def 案内の名(ctx: str) -> list[str]:
    """差し込みの終わりの案内に例として出す節の名。"""
    tail = ctx[ctx.rindex("形の細目は"):]
    return re.findall(r"`(\*\*[^*`]+\*\*)`", tail)


def 死んだ名(ctx: str, text: str) -> list[str]:
    names = 案内の名(ctx)
    return ["（案内に節の名が無い）"] if not names else [n for n in names if n not in 節の名(text)]


def 画面の問いの文の数(text: str) -> list[str]:
    """細目 §4「見せてから聞く」の ② の中の「N 文」「N〜M 文」の数の並び。"""
    line = next(ln for ln in text.splitlines() if ln.startswith("- **見せてから聞く**"))
    seg = line[line.index("②"):line.index("③")]
    return re.findall(r"(\d+(?:〜\d+)?) 文", seg)


def test_差し込みの案内は節の名で引いてその節だけ読ませる():
    ctx = kaku.inject_text()
    tail = ctx[ctx.rindex("形の細目は"):]
    assert "で Grep し、" in tail and "その節だけ Read する" in tail
    assert not re.search(r"Read する）", tail.replace("その節だけ Read する）", "")), "file を丸ごと読ませる案内が残る"
    assert 死んだ名(ctx, kaku.saimoku_text(DIR)) == []


def test_案内の節の名が細目に無いと赤(monkeypatch):
    """注入の試験: 案内の例を死んだ節の名にすると拒む。"""
    monkeypatch.setattr(kaku, "SAIMOKU_EXAMPLE", "**無い節の名**")
    assert 死んだ名(kaku.inject_text(), kaku.saimoku_text(DIR)) == ["**無い節の名**"]


def test_細目から節を消すと案内の名が死んで赤():
    """注入の試験: 細目の側で節の名を変えると拒む。"""
    text = kaku.saimoku_text(DIR).replace("- **見せてから聞く** —", "- **見せて聞く** —")
    assert 死んだ名(kaku.inject_text(), text) == ["**見せてから聞く**"]


def test_細目の画面の問いの文の数は_guard_の上限と同じ():
    want = str(_guard_defaults()["ask_question_max_sentences"])
    nums = 画面の問いの文の数((DIR / "04-聞き方.md").read_text(encoding="utf-8"))
    assert nums and all(n == want for n in nums), nums


def test_細目の聞く線を旧い幅に戻すと赤():
    """注入の試験: 作り物で旧い「1〜2 文」に戻すと guard の上限とずれて拒む。"""
    want = str(_guard_defaults()["ask_question_max_sentences"])
    text = (DIR / "04-聞き方.md").read_text(encoding="utf-8").replace("1 文（前提も①へ）", "1 文（要る前提は 1〜2 文まで）")
    assert any(n != want for n in 画面の問いの文の数(text))
