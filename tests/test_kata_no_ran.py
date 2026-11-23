"""振り返り・直しの型が、意図・課題・原因などの欄を別々の欄として決まった順で持ち続けるかを、欄の形で照らす。

意図: 各型が意図・課題・原因の欄を持ち続けることを試験が守る。
課題: 型の欄の試験が雛形の 1 行を丸ごと字で照らしていたので、言い回しを変えると欄が残っていても赤になり、
  欄を消して字だけ残すと緑だった。
原因: 型の欄の試験が欄の形でなく決まった字の有無を見ていた（型ごとの欄の定義を持つ所が無かった）。
"""
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


# ── 型の欄 ────────────────────────────────────────────────────
# 型ごとの欄の定義は tests/data/型の欄.json 1 つ。根治の段の名と順は細目 §3 の「根治の 5 段」から引く。
# 照らすのは決まった字の有無でなく欄の形: 欄の始まりの印（行の頭・見出し・箇条・太字・`|`・`｜`・`／`・`/`・`—`・丸数字・`）の後に
# 名が在り、すぐ欄の終わりの印（`:`・`：`・`（`・太字の閉じ・`|`・`｜`・`／`・`/`・`・行の終わり）が続く所を欄と見る。

型の欄 = json.loads(_read("tests/data/型の欄.json"))["型"]
_始まりの印 = r"(?:^[ \t]*(?:#+[ \t]*|[-*][ \t]*|\d+\.[ \t]*)?(?:\*\*|`)?|[|｜／/—`①②③④⑤⑥⑦⑧⑨⑩][ \t]*|\*\*)"
_終わりの印 = r"(?=[:：（(／/`]|\*\*|[ \t]*[|｜]|[ \t]*$)"


def 根治の段():
    """細目 §3「根治の 5 段」の段の名を順に返す（型の欄の名と順の正本）。"""
    s = _read("plugins/core/細目/03-直すは根治.md")
    head = s.index("- **根治の 5 段**")
    names = []
    for line in s[head:].splitlines()[1:]:
        m = re.match(r"^  - \*\*(.+?)\*\* — ", line)
        if not m:
            break
        names.append(m.group(1))
    return names


def 型の所(text, kata):
    """file の中の型の所（始まりの行から、幅の終わりまで）を返す。無ければ None。"""
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if re.search(kata["始まり"], line):
            out = [line]
            if kata["幅"] != "行":
                for nxt in lines[n + 1:]:
                    if nxt.startswith("```") or (kata["幅"] == "塊" and not nxt.strip()) or \
                       (kata["幅"] == "節" and re.match(r"^#+\s", nxt)):
                        break
                    out.append(nxt)
            return "\n".join(out)
    return None


def 欄の位置(unit, name):
    """name が欄として在る最初の位置（字だけ在って欄でない物は数えない）。無ければ -1。"""
    m = re.search(_始まりの印 + "(" + re.escape(name) + ")" + _終わりの印, unit, re.M)
    return m.start(1) if m else -1


def 欄の外れ(unit, names):
    """欄が別々に・この順で在るかを照らし、外れを返す（空なら合う）。"""
    if unit is None:
        return ["型の所が見つからない"]
    pos = {n: 欄の位置(unit, n) for n in names}
    bad = [f"欄が無い: {n}" for n, p in pos.items() if p < 0]
    seen = [pos[n] for n in names if pos[n] >= 0]
    if not bad and seen != sorted(seen):
        bad.append("欄の順が違う: " + " → ".join(sorted(names, key=pos.get)))
    return bad


def _ids(k):
    return k["名"]


def test_型の欄の段の名と順は細目の根治の段に沿う():
    dan = 根治の段()
    assert dan[:3] == ["意図", "課題", "原因"], dan
    for k in 型の欄:
        steps = [n for n in k["欄"] if n in dan]
        assert steps, k["名"]
        assert steps == sorted(steps, key=dan.index), k["名"]


def test_型は意図などの欄を別々にこの順で持つ():
    bad = {k["名"]: b for k in 型の欄 if (b := 欄の外れ(型の所(_read(k["file"]), k), k["欄"]))}
    assert not bad, bad


def 型が並べる欄(unit):
    """型が欄を並べて書く所（`a｜b｜c` の並び・表の頭の行）から欄の名を全部返す。"""
    names = []
    for grp in re.findall(r"`([^`\n]*｜[^`\n]*)`", unit):
        names += [x.strip() for x in grp.split("｜")]
    head = next((l for l in unit.splitlines() if l.strip().startswith("|") and not set(l.strip()) <= set("|-: ")), None)
    if head:
        names += [re.split(r"[（(]", c)[0].strip() for c in head.strip().strip("|").split("|")]
    return [n for n in names if n]


def test_型が並べる欄は全部_欄の定義に載る():
    # 欄の定義を手で選んで一部だけ載せると、載せない欄は消しても緑になる（PR #137 のレビューの red）
    bad = {k["名"]: m for k in 型の欄
           if (m := [n for n in 型が並べる欄(型の所(_read(k["file"]), k)) if n not in k["欄"]])}
    assert not bad, bad


def test_注入_並べた欄を定義から外すと赤():
    unit = "欄 `意図｜決めた中身｜原文｜時刻` で書く。"
    assert [n for n in 型が並べる欄(unit) if n not in ["意図", "決めた中身"]] == ["原文", "時刻"]
    table = "| 論点 | 意図（何のために） | 持つ窓 |\n|---|---|---|"
    assert 型が並べる欄(table) == ["論点", "意図", "持つ窓"]


def _字だけ残す(unit, name):
    """name の欄を壊し、字は残す（「意図:」→「意図も込みの文:」）。"""
    return re.sub(_始まりの印 + "(" + re.escape(name) + ")" + _終わりの印,
                  lambda m: m.group(0) + "も込みの文", unit, flags=re.M)


def _言い回しを変える(unit, names):
    """欄の名を除く言葉を全部言い換える（欄の名と区切りの印は残す）。"""
    keep = []

    def _守る(m):
        keep.append(m.group(0))
        return f"\0{len(keep) - 1}\0"

    pat = _始まりの印 + "(?:" + "|".join(map(re.escape, names)) + ")" + _終わりの印
    out = re.sub(r"[ぁ-んァ-ヶ一-龠ー]+", "言い換え", re.sub(pat, _守る, unit, flags=re.M))
    return re.sub(r"\0(\d+)\0", lambda m: keep[int(m.group(1))], out)


@pytest.mark.parametrize("kata", 型の欄, ids=_ids)
def test_注入_欄を消して字だけ残すと赤_言い回しを変えても欄が残れば緑(kata):
    unit = 型の所(_read(kata["file"]), kata)
    for name in kata["欄"]:
        broken = _字だけ残す(unit, name)
        assert name in broken
        assert f"欄が無い: {name}" in 欄の外れ(broken, kata["欄"]), (kata["名"], name)
    reworded = _言い回しを変える(unit, kata["欄"])
    assert reworded != unit, kata["名"]
    assert 欄の外れ(reworded, kata["欄"]) == [], kata["名"]


@pytest.mark.parametrize("kata", 型の欄, ids=_ids)
def test_注入_欄の順を入れ替えると赤(kata):
    unit = 型の所(_read(kata["file"]), kata)
    a, b = kata["欄"][0], kata["欄"][-1]
    pa, pb = 欄の位置(unit, a), 欄の位置(unit, b)
    swapped = unit[:pa] + b + unit[pa + len(a):pb] + a + unit[pb + len(b):]
    assert any(x.startswith("欄の順が違う") for x in 欄の外れ(swapped, kata["欄"])), kata["名"]


def test_注入_型の所が無いと赤():
    assert 欄の外れ(None, ["意図"]) == ["型の所が見つからない"]
    assert 欄の外れ("意図と課題と原因を 1 つの欄に書く:", ["意図", "課題", "原因"])
