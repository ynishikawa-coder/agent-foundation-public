"""細目を節の名で引いて読む道を照らす。

意図: 窓が細目の file を丸ごと読まず、要る 1 節だけ読む。
課題: 差し込みの案内が「番号で始まる file を Read」＝ 1 file を丸ごと読ませていた。
原因: 案内を実の節と照らす物が無かった（片方だけ変えても緑）。
"""
import re
from pathlib import Path

from saimoku import DIR, kaku

ROOT = Path(__file__).resolve().parent.parent


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
