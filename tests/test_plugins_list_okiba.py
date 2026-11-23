"""plugins/README.md の一覧の照らし（tests/test_plugins_list.py）を、手で写した名の集まりと列の並びでなく、
配りの器（.claude-plugin/marketplace.json）の名と、表の頭の行から読んだ列で照らす。

意図: 一覧の表が配りの器と実の dir に揃う事を守り、名の集まりと列の並びを試験に写さない。
課題: 試験が plugin の名の集まり（EXPECTED）と列の並び（HEADER）を写していたので、plugin を足す・消すたびに試験の写しも直し、
  表を注記の中へ入れても file の頭から最初の表を読んでいた。
原因: 試験が構造を読む口（tests/md_yomi.py）を使わず、名を動く物（配りの器）から読まずに写していた。
"""
import json
from pathlib import Path

from md_yomi import 地の行, 表の行

ROOT = Path(__file__).resolve().parent.parent
LIST = ROOT / "plugins" / "README.md"
MARKET = ROOT / ".claude-plugin" / "marketplace.json"
FIRST = "名前"
# 試験が読む列（並びは縛らない）。
USED = ["名前", "種類", "持つ窓", "状態", "置き場", "中身"]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def 一覧の行(text: str) -> list[dict] | None:
    """頭の行の 1 つ目の升が「名前」の表を、頭の行の列の名で dict にして返す（注記・囲いの中の表は読まない）。
    表が無い・2 つ在る・読む列が無い・列の数が違う時は None。"""
    heads = [_cells(l) for l in 地の行(text) if l.strip().startswith("|") and _cells(l)[0] == FIRST]
    if len(heads) != 1 or not set(USED) <= set(heads[0]):
        return None
    rows = 表の行(text, FIRST)
    if not rows or any(len(r) != len(heads[0]) for r in rows):
        return None
    return [dict(zip(heads[0], r)) for r in rows]


def 器の名(market: str) -> set[str]:
    entries = json.loads(market).get("plugins", [])
    assert isinstance(entries, list), "marketplace.json の plugins が配列でない"
    return {e["name"] for e in entries}


def 一覧の外れ(rows: list[dict] | None, in_market: set[str]) -> list[str]:
    """名が重ならず、器の名が全部在り、器に無い行は 出した でない（＝行の集まりは器と、まだ配らない行）。"""
    if rows is None:
        return ["一覧の表（頭の 1 つ目の升が「名前」）が 1 つでない・列が足りない"]
    names = [r["名前"] for r in rows]
    out = [f"名前が重なる: {n}" for n in sorted({n for n in names if names.count(n) > 1})]
    out += [f"器にあって一覧に無い: {n}" for n in sorted(in_market - set(names))]
    out += [f"器に無いのに 出した: {r['名前']}" for r in rows if r["名前"] not in in_market and r["状態"] == "出した"]
    return out


def _read(p):
    return p.read_text(encoding="utf-8")


def test_今は揃う():
    assert 一覧の外れ(一覧の行(_read(LIST)), 器の名(_read(MARKET))) == []


def test_注入_表を注記へ入れると読めない_列の並びを変えても読める():
    t = _read(LIST)
    table = "\n".join(l for l in t.splitlines() if l.startswith("|"))
    assert 一覧の行(t.replace(table, f"<!--\n{table}\n-->", 1)) is None
    assert 一覧の行(t.replace(table, f"```\n{table}\n```", 1)) is None
    swapped = "\n".join("|" + "|".join([c[0], c[2], c[1]] + c[3:]) + "|" for c in map(_cells, table.splitlines()))
    rows = 一覧の行(t.replace(table, swapped, 1))
    assert rows == 一覧の行(t)   # 2 つ目と 3 つ目の列を入れ替えても、列の名で読むので同じ
    assert 一覧の行(t.replace("| 名前 | 種類 |", "| 名前 | 型 |", 1)) is None   # 読む列の名を変えると読めない


def test_注入_器に足すと赤_器から消すと赤():
    rows, m = 一覧の行(_read(LIST)), 器の名(_read(MARKET))
    assert 一覧の外れ(rows, m | {"nai-plugin"}) == ["器にあって一覧に無い: nai-plugin"]
    gone = sorted(m)[0]
    assert 一覧の外れ(rows, m - {gone}) == [f"器に無いのに 出した: {gone}"]
    assert 一覧の外れ(rows + [dict(rows[0])], m) == [f"名前が重なる: {rows[0]['名前']}"]
