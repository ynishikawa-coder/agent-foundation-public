"""細目の決まりは、どの文も名の在る節（`- **名** — …`）の中に在る事を照らす。

意図: 窓は細目を丸ごと読まず、節の名で Grep してその節だけ Read する。それで決まりを 1 つも読み落とさない。
課題: 細目の file に、節の名の無い地の文（見出しの下の素の行・名の無い `- ` の行）が在った。
節だけ読む案内に従う窓は、その文を引けずに読み落としていた。
原因: 細目の形（節の名で引く）を決めた時、名の無い行を拒む口が無く、書き足す度に名の無い文が混ざれた。
解決: 細目の 01〜09 は、見出しの後の空でない行を `- **名**` で始めるか、上の節に属す字下げ（2 字）にする。
名の無い行をわざと入れた写しを拒む試験も持つ（00-はじめ は細目の読み方の案内で節を持たないので外す）。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SAIMOKU = ROOT / "plugins" / "core" / "細目"


def unnamed_lines(text):
    """見出しの後で、名の在る節にも、その節の字下げにも属さない行を (行番号, 行) で返す。"""
    out, seen_head, in_section = [], False, False
    for no, ln in enumerate(text.splitlines(), 1):
        if ln.startswith("## "):
            seen_head, in_section = True, False
            continue
        if not seen_head or not ln.strip():
            continue
        if ln.startswith("- **"):
            in_section = True
        elif ln.startswith("  ") and in_section:
            pass
        else:
            out.append((no, ln))
    return out


def _files():
    fs = sorted(p for p in SAIMOKU.glob("*.md") if not p.name.startswith("00-"))
    assert len(fs) >= 9, fs
    return fs


def test_細目の文はどれも名の在る節の中に在る():
    bad = {p.name: unnamed_lines(p.read_text(encoding="utf-8")) for p in _files()}
    bad = {k: v for k, v in bad.items() if v}
    assert not bad, "名の無い地の文: %r" % bad


def test_名の無い行をわざと入れると拒む():
    p = SAIMOKU / "05-返事の形.md"
    text = p.read_text(encoding="utf-8")
    assert not unnamed_lines(text)
    for planted in ("作り物の決まりを地の文で書く。", "- 作り物の決まりを名の無い行で書く。"):
        got = unnamed_lines(text.rstrip("\n") + "\n\n" + planted + "\n")
        assert [ln for _, ln in got] == [planted], got


def test_見出しの前に節が無い字下げも拒む():
    got = unnamed_lines("## 9. 例\n\n  - 上に節の無い字下げ\n- **名** — 文。\n  - 節に属す字下げ\n")
    assert [ln for _, ln in got] == ["  - 上に節の無い字下げ"], got
