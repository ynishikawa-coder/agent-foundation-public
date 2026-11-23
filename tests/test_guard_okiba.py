"""守りの hook（guard）が止めた文の中の細目の指し先を、字の写しでなく細目の欄（動く物）から読んだ名で照らす。

意図: 止めた文が指す細目の節「名」が細目に欄として在り、根治の入口は止めた文の最後の行に在る事を守り、
  止めた文の言い回しは縛らない。
課題: 試験が「細目 §3「まず構造を疑う」」「細目 §4「推奨の印」」の字を写して `in` で探していたので、細目の欄の名を
  直すと hook の文が古いまま緑、指し先が細目に無くても緑だった。
原因: 試験が指し先の名を細目（tests/md_yomi.py の 欄）から読まずに写していた。
"""
from __future__ import annotations

import re
from pathlib import Path

from md_yomi import 太字の欄, 欄

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "plugins" / "core" / "細目"
_REF = re.compile(r"細目 §(\d+)「(.+?)」")


def 細目の節(n: int) -> str:
    """細目の §n の file（名が `0n-` で始まる 1 つ）の本文。"""
    hits = sorted(DIR.glob(f"{n:02d}-*.md"))
    assert len(hits) == 1, hits
    return hits[0].read_text(encoding="utf-8")


def _欄の名(text: str, mark: str) -> str:
    names = [name for name, body in 太字の欄(text) if mark in body]
    assert len(names) == 1, (mark, names)
    return names[0]


def 根治の入口(saimoku3: str | None = None) -> str:
    """細目 §3 の、本文が「根治に入る口」と言う欄の名（今は「まず構造を疑う」）。"""
    return _欄の名(saimoku3 if saimoku3 is not None else 細目の節(3), "根治に入る口")


def 推奨の名(saimoku4: str | None = None) -> str:
    """細目 §4 の、本文が `(推奨)` の付け方を言う欄の名（今は「推奨の印」）。"""
    return _欄の名(saimoku4 if saimoku4 is not None else 細目の節(4), "`(推奨)`")


def 細目の指し先の外れ(text: str, saimoku: dict[int, str] | None = None) -> list[str]:
    """text の中の「細目 §n「名」」が全部、細目 §n に欄として 1 つずつ在るか。指し先が 1 つも無い時も外れ。"""
    refs = _REF.findall(text)
    if not refs:
        return ["細目の指し先が無い"]
    out = []
    for n, name in refs:
        body = (saimoku or {}).get(int(n)) or 細目の節(int(n))
        if 欄(body, name) is None:
            out.append(f"細目 §{n} に「{name}」の欄が 1 つでない")
    return out


def 根治の行の外れ(why: str, saimoku: dict[int, str] | None = None) -> list[str]:
    """止めた文の最後の行が細目 §3 の根治の入口を指し、指し先が全部細目に在るか。"""
    s3 = (saimoku or {}).get(3)
    want = f"細目 §3「{根治の入口(s3)}」"
    lines = why.strip().splitlines()
    out = [] if lines and want in lines[-1] else [f"止めた文の最後の行に {want} が無い"]
    return out + 細目の指し先の外れ(why, saimoku)


def 根治の指し先の外れ(why: str, saimoku: dict[int, str] | None = None) -> list[str]:
    """止めた文のどこかが細目 §3 の根治の入口を指し、指し先が全部細目に在るか（最後の行と限らない文）。"""
    want = f"細目 §3「{根治の入口((saimoku or {}).get(3))}」"
    return ([] if want in why else [f"止めた文に {want} が無い"]) + 細目の指し先の外れ(why, saimoku)


def 推奨の指し先の外れ(why: str, saimoku: dict[int, str] | None = None) -> list[str]:
    want = f"細目 §4「{推奨の名((saimoku or {}).get(4))}」"
    return ([] if want in why else [f"止めた文に {want} が無い"]) + 細目の指し先の外れ(why, saimoku)


# --- 注入の試験 ---------------------------------------------------------------------------------------------

WHY = "作り物の止めた訳。\n直し: 細目 §4「推奨の印」を読む。\n直し: 意図とのずれから入り、細目 §3「まず構造を疑う」で探して直す"


def test_注入_細目の欄の名を変えると古い指し先は赤_止めた文の言い回しは縛らない():
    s3, s4 = 細目の節(3), 細目の節(4)
    assert 根治の行の外れ(WHY) == [] and 推奨の指し先の外れ(WHY) == []
    # 細目の欄の名を変えたら（hook の文はそのまま）指し先が古いので赤
    s3r = s3.replace("**まず構造を疑う**", "**構造から疑う**", 1)
    assert 根治の入口(s3r) == "構造から疑う" and 根治の行の外れ(WHY, {3: s3r}) != []
    s4r = s4.replace("**推奨の印**", "**推奨の付け方**", 1)
    assert 推奨の指し先の外れ(WHY, {4: s4r}) != []
    # 細目の欄を注記へ入れると欄が無い
    line = next(l for l in s3.splitlines() if l.startswith("- **まず構造を疑う**"))
    assert any("1 つでない" in x for x in 細目の指し先の外れ(WHY, {3: s3.replace(line, f"<!-- {line} -->", 1)}))
    # 細目に無い名を指すと赤・指し先が 1 つも無いと赤
    assert 細目の指し先の外れ("細目 §3「無い欄」") == ["細目 §3 に「無い欄」の欄が 1 つでない"]
    assert 細目の指し先の外れ("直して出し直す。") == ["細目の指し先が無い"]
    # 根治の入口が最後の行から外れると赤
    lines = WHY.splitlines()
    assert 根治の行の外れ("\n".join([lines[2], lines[0]])) != []
    # 止めた文の言い回しを変えても指し先が在れば緑
    assert 根治の行の外れ(WHY.replace("意図とのずれから入り、", "", 1)) == []
