"""plugins/README.md の一覧と、実の dir・配りの器が合っているかを見る。"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIST = ROOT / "plugins" / "README.md"
MARKET = ROOT / ".claude-plugin" / "marketplace.json"
HEADER = ["名前", "種類", "持つ窓", "状態", "置き場", "中身"]
KINDS = {"plugin"}
STATES = {"未着手", "作業中", "出した"}
# 波 0 で先に置いた行。消す時はこの集合も同じ PR で替える。
EXPECTED = {"docs-kit", "dev-flow", "session-watch", "checker", "guard", "core"}


def read_rows():
    lines = LIST.read_text(encoding="utf-8").splitlines()
    rows, in_table = [], False
    for line in lines:
        if not line.startswith("|"):
            if in_table:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not in_table:
            assert cells == HEADER, f"一覧の見出しが違う: {cells}"
            in_table = True
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        assert len(cells) == len(HEADER), f"列の数が違う: {line}"
        rows.append(dict(zip(HEADER, cells)))
    assert rows, "一覧の表が無い"
    return rows


def skills_of(row):
    if row["中身"] == "—":
        return []  # skill を持たない plugin（core）
    return [s.strip() for s in row["中身"].split("・") if s.strip()]


def test_一覧の行が全部ある():
    names = [r["名前"] for r in read_rows()]
    assert len(names) == len(set(names)), f"名前が重なる: {names}"
    assert set(names) == EXPECTED


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
    for r in read_rows():
        if r["種類"] != "plugin" or r["状態"] != "出した":
            continue
        skills_dir = ROOT / r["置き場"] / "skills"
        actual = {p.parent.name for p in skills_dir.glob("*/SKILL.md")}
        assert actual == set(skills_of(r)), f"{r['名前']}: 一覧 {skills_of(r)} / 実 {sorted(actual)}"


def test_配りの器と一覧が合う():
    if not MARKET.exists():
        pytest.skip("配りの器 .claude-plugin/marketplace.json がまだ無い（A0 の合流待ち）")
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
