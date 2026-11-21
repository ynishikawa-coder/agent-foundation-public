"""値の表の全体に当てる鍵と codex の glob の「前の読み方」の受けを畳んだ（2 段目）約束の注入の試験。

どれも前の誤りを入れると赤になる形で書く:
- 全体に当てる鍵の、全体の形でない行（錨なし・一番外に | の在る ^a|b$）を前の読み方（一部に当てる）で効かせ直すと赤
- ^a|b$ を全体の形と読む（^ と $ の字だけで見る）へ戻すと赤
- 止める側の鍵（irreversible_tools_extra）で、効かない行を黙って捨てる（止めない）へ倒すと赤
- 通す側の鍵（qa_page_exempt など）で、効かない行を照らせない時にも通す側へ倒すと赤
- codex の self_allow・clients.<名>.paths で * が / をまたぐ読み方へ戻す（前の読み方でだけ当たる path を通す）と赤
- 古い形.json に、畳んだ形（values-pattern-partial・codex-glob-star-crosses）が戻ると赤
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
sys.path.insert(0, str(ROOT / "skill-values"))
sys.path.insert(0, str(ROOT / "plugins" / "dev-flow" / "skills" / "codex"))

import skill_values as SV  # noqa: E402
import guard_common as G  # noqa: E402
import irreversible  # noqa: E402
import codex_pack  # noqa: E402

TOOLS = SV.key_spec("guard", None, "irreversible_tools_extra")
TODAY = dt.date(2026, 11, 20)


@pytest.mark.parametrize("row, whole", [
    ("^mcp__s__delete_item$", True),
    ("^(?:mcp__s__delete_item|mcp__s__purge)$", True),
    ("^mcp__s__a\\|b$", True),                 # エスケープした | は選択でない
    ("^mcp__s__[|]x$", True),                  # 字の組の中の | は選択でない
    ("^mcp__s__[]|]x$", True),                 # ] で始まる字の組の中の |
    ("^mcp__s__delete_item|mcp__s__purge$", False),   # 一番外の | ＝読み方が割れる
    ("^a$|^b$", True),                       # 分かれの全部の道が錨で挟まれる
    ("delete", False),
    ("^delete", False),
    ("delete$", False),
])
def test_全体の形は全部の道が錨で挟まれる行だけ(row, whole):
    assert SV._whole_regex(row) is whole
    assert (SV.not_whole_rows(TOOLS, [row]) == []) is whole


def test_全体の形でない行は前の読み方で効かない():
    rows = SV.compile_patterns(TOOLS, ["delete", "^mcp__s__delete_item|mcp__s__purge$"])
    for name in ("mcp__s__undelete_item", "mcp__s__delete_item", "mcp__s__purge", "delete"):
        assert SV.hit(rows, name) is None, name


def test_選択の行は一部の読み方にも全体の読み方にも割れず_名指される():
    probs = SV.check({"guard": {"irreversible_tools_extra": ["^mcp__s__a|mcp__s__b$"]}})
    assert any("全体の形でない" in p and "^(?:a|b)$" in p for p in probs), probs


def test_止める側の鍵は効かない行で黙って通さず_照らせないと止める():
    vals = {"irreversible_tools_extra": ["delete", "^mcp__s__x|mcp__s__purge$"]}
    for name in ("mcp__s__undelete_item", "mcp__s__x_more", "mcp__t__mcp__s__purge"):
        why = irreversible.match(name, {}, "", vals)
        assert "照らせない" in why and "irreversible_tools_extra" in why, (name, why)
    assert irreversible.match("mcp__s__read_item", {}, "", vals) == ""


def test_止める側の鍵の全体の形の行は道具の名の全体だけを止める():
    vals = {"irreversible_tools_extra": [{"pattern": "^(?:mcp__s__delete_item|mcp__s__purge)$", "why": "作り物"}]}
    assert irreversible.match("mcp__s__purge", {}, "", vals) == "作り物"
    assert irreversible.match("mcp__s__purge_all", {}, "", vals) == ""


def test_通す側の鍵の効かない行は通さない側に倒れる():
    pats = G.patterns({"qa_page_exempt": ["quiz/", "^quiz/a\\.html|docs/.*$"]}, "qa_page_exempt")
    for rel in ("quiz/a.html", "docs/b.html", "x/quiz/c.html"):
        assert SV.hit(pats, rel) is None, rel


def test_hit_は前の当てる相手を受けない():
    import inspect
    assert list(inspect.signature(SV.hit).parameters) == ["compiled", "text"]


@pytest.mark.parametrize("key, vals, dest", [
    ("self_allow", {"self_allow": ["tools/*"]}, "self"),
    ("paths", {"clients": {"c1": {"opt_in": True, "no_training_tier": True, "expires": "2099-01-01",
                                  "paths": ["work/c1/*"]}}}, "client:c1"),
])
def test_codex_の_glob_は星が斜線をまたぐ読み方で通さない(key, vals, dest):
    deep = "tools/sub/deep/x.py" if key == "self_allow" else "work/c1/sub/x.py"
    direct = "tools/x.py" if key == "self_allow" else "work/c1/x.py"
    assert codex_pack.resolve_dest(dest, [direct], vals, TODAY) == dest
    with pytest.raises(codex_pack.Abort) as e:
        codex_pack.resolve_dest(dest, [deep], vals, TODAY)
    assert "dir/**" in str(e.value)


def test_codex_の前の読み方の受けの名が残らない():
    src = (ROOT / "plugins" / "dev-flow" / "skills" / "codex" / "codex_pack.py").read_text(encoding="utf-8")
    assert not hasattr(codex_pack, "old_only") and not hasattr(codex_pack, "_note_old")
    assert "前の読み方" not in src


def test_古い形の一覧に畳んだ形が戻らない():
    olds = json.loads((ROOT / "plugins" / "core" / "古い形.json").read_text(encoding="utf-8"))["olds"]
    ids = {o["id"] for o in olds}
    assert not ids & {"values-pattern-partial", "codex-glob-star-crosses"}, ids
