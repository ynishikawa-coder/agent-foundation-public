"""plugins/README.md の一覧と、実の dir・配りの器が合っているかを見る。"""
import json
import re
from pathlib import Path

from test_plugins_list_okiba import 一覧の外れ, 一覧の行, 器の名

ROOT = Path(__file__).resolve().parent.parent
LIST = ROOT / "plugins" / "README.md"
MARKET = ROOT / ".claude-plugin" / "marketplace.json"
KINDS = {"plugin"}
STATES = {"未着手", "作業中", "出した"}


def read_rows():
    """一覧の表を列の名で読む（名の集まりと列の並びは写さない＝tests/test_plugins_list_okiba.py）。"""
    rows = 一覧の行(LIST.read_text(encoding="utf-8"))
    assert rows, "一覧の表が無い・列が足りない"
    return rows


def skills_of(row):
    if row["中身"] == "—":
        return []  # skill を持たない plugin（core）
    return [s.strip() for s in row["中身"].split("・") if s.strip()]


def test_一覧の行が全部ある():
    # 行の集まりは配りの器の名と、まだ配らない行（名は器から読む）。
    assert 一覧の外れ(read_rows(), 器の名(MARKET.read_text(encoding="utf-8"))) == []


def test_各行の値が決まりの中():
    for r in read_rows():
        assert r["種類"] in KINDS, r
        assert r["状態"] in STATES, r
        assert re.fullmatch(r"A\d+[a-z]?", r["持つ窓"]), r
        assert r["置き場"].endswith("/") and not r["置き場"].startswith("/"), r
        if r["種類"] == "plugin":
            assert r["置き場"] == f"plugins/{r['名前']}/", r


def test_状態と実の置き場が合う():
    for r in read_rows():
        exists = (ROOT / r["置き場"]).is_dir()
        if r["状態"] == "未着手":
            assert not exists, f"{r['名前']}: 置き場があるのに 未着手"
        else:
            assert exists, f"{r['名前']}: {r['状態']} なのに置き場が無い"


def test_plugins_の下の_dir_は全部一覧にある():
    listed = {r["置き場"].rstrip("/") for r in read_rows()}
    for d in sorted((ROOT / "plugins").iterdir()):
        if d.is_dir():
            rel = d.relative_to(ROOT).as_posix()
            assert rel in listed, f"一覧に無い dir: {rel}"


def test_出した_plugin_は中身と_skills_が一致():
    rows = [r for r in read_rows() if r["種類"] == "plugin" and r["状態"] == "出した"]
    assert rows, "「出した」plugin の行が 0（一覧の読み方か列の名が変わり、何も照らさずに通る形）"
    for r in rows:
        skills_dir = ROOT / r["置き場"] / "skills"
        actual = {p.parent.name for p in skills_dir.glob("*/SKILL.md")}
        assert actual == set(skills_of(r)), f"{r['名前']}: 一覧 {skills_of(r)} / 実 {sorted(actual)}"


def test_配りの器と一覧が合う():
    data = json.loads(MARKET.read_text(encoding="utf-8"))
    entries = data.get("plugins", [])
    assert isinstance(entries, list), "marketplace.json の plugins が配列でない"
    in_market = {e["name"] for e in entries}
    rows = {r["名前"]: r for r in read_rows() if r["種類"] == "plugin"}
    for name in in_market:
        assert name in rows, f"器にあって一覧に無い: {name}"
        assert rows[name]["状態"] != "未着手", f"器にあるのに 未着手: {name}"
    for name, r in rows.items():
        if r["状態"] == "出した":
            assert name in in_market, f"出した のに器に無い: {name}"


def test_plugin_は版の番号を持たない():
    """土台は main の先端を配る。plugin.json に版を書くと、入った物が commit でなく版の名で区別され、
    古い土台で立った窓を見分ける比べ（plugin core の kaku.py fresh・入った commit と main の先端）が効かなくなる。"""
    for f in sorted(ROOT.glob("plugins/*/.claude-plugin/plugin.json")):
        assert "version" not in json.loads(f.read_text(encoding="utf-8")), f
