"""全体の絵の流れのタブは手順の正本を読んで描く（要約で描かない）約束の試験。

合格の線: 流れの箱の引用を、正本に無い文（要約・古い版の文）にわざと替えると sources が止める（exit 1）。
引用の無い箱・正本の外の引用・形 2 の外の form は check が止める。作り物の手順だけを使う。
"""
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "docs-kit" / "skills" / "big-picture" / "scripts" / "big_picture.py"
spec = importlib.util.spec_from_file_location("big_picture", TOOL)
bp = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(bp)

PROC = """# 手順（作り物）

## 1 段
届いた紙を全部読み、
台帳へ書く。

## 2 段
差が 0 でなくても、差の訳が分かれば次の段へ進む。
"""


OLD = """# 前の設計（作り物）
差が 0 になるまで次の段へ進まない。
"""


def box(i, t, x, src=None, tab="flow"):
    b = {"id": i, "tab": tab, "t": t, "k": "ai", "side": "個別", "x": x, "y": 10, "w": 100, "h": 40,
         "what": t, "why": "手順.md", "intent": None}
    if src is not None:
        b["src"] = src
    return b


def pic():
    return {
        "form": "big-picture/2",
        "meta": {"title": "作り物", "kind": "実物", "version": "2026-01-01.1", "problem": "p", "goal": "g",
                 "drawn_from": "repo@0123456789ab", "drawn_by": "session_X", "sources": {"flow": ["docs/手順.md"]}},
        "tabs": {"flow": {"w": 400, "h": 100}},
        "boxes": [
            box("s1", "読んで書く", 10, [{"path": "docs/手順.md", "quote": "届いた紙を全部読み、台帳へ書く。"}]),
            box("s2", "訳が分かれば進む", 200, [{"path": "docs/手順.md", "quote": "差の訳が分かれば次の段へ進む"}]),
            box("c1", "文脈の箱は引用が要らない", 10, tab="ctx"),
        ],
        "arrows": [{"from": "s1", "to": "s2"}],
        "problems": [],
    }


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "手順.md").write_text(PROC, encoding="utf-8")
    (tmp_path / "docs" / "古い設計.md").write_text(OLD, encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "skill-values.json").write_text(
        json.dumps({"docs-kit": {"big-picture": {"procedure": ["docs/手順.md"]}}}, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def run(*a):
    return subprocess.run([sys.executable, str(TOOL), *map(str, a)], capture_output=True, text=True)


def save(tmp_path, p):
    f = tmp_path / "絵.json"
    f.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    return f


def test_正本の文から描いた流れは通る(repo):
    p = pic()
    p["tabs"]["ctx"] = {"w": 200, "h": 100}
    assert bp.check(p)[0] == []
    r = run("sources", save(repo, p), repo)
    assert r.returncode == 0, r.stdout
    assert "SOURCES OK" in r.stdout


@pytest.mark.parametrize("quote", [
    "差が 0 になるまで次の段へ進まない",          # 古い設計の文
    "差の訳が分かったら次へ",                     # 要約
    "届いた紙を全部読む。台帳へ書く。",            # 書き換え
])
def test_正本に無い引用は止める(repo, tmp_path, quote):
    p = pic()
    p["tabs"]["ctx"] = {"w": 200, "h": 100}
    p["boxes"][1]["src"][0]["quote"] = quote
    r = run("sources", save(repo, p), repo)
    assert r.returncode == 1, r.stdout
    assert "s2" in r.stdout and "直し:" in r.stdout


def test_正本が変われば前に描いた絵は止まる(repo):
    p = pic()
    p["tabs"]["ctx"] = {"w": 200, "h": 100}
    (repo / "docs" / "手順.md").write_text(PROC.replace("差の訳が分かれば次の段へ進む", "差が 0 の時だけ次の段へ進む"), encoding="utf-8")
    assert run("sources", save(repo, p), repo).returncode == 1


@pytest.mark.parametrize("mutate, word", [
    (lambda p: p["boxes"][0].pop("src"), "src"),
    (lambda p: p["boxes"][0].__setitem__("src", []), "src"),
    (lambda p: p["boxes"][0]["src"][0].pop("quote"), "{path, quote}"),
    (lambda p: p["boxes"][0]["src"][0].__setitem__("path", "docs/別の紙.md"), "meta.sources.flow"),
    (lambda p: p["meta"].pop("sources"), "meta.sources.flow"),
    (lambda p: p.__setitem__("form", "big-picture/9"), "form"),
])
def test_引用の無い流れの箱と正本の外の引用は形の誤り(mutate, word):
    p = pic()
    p["tabs"]["ctx"] = {"w": 200, "h": 100}
    mutate(p)
    errs, _ = bp.check(p)
    assert any(word in e for e in errs), errs


def test_正本が読めない時と根が無い時は照らせない(repo, tmp_path):
    p = pic()
    p["tabs"]["ctx"] = {"w": 200, "h": 100}
    f = save(repo, p)
    assert run("sources", f, tmp_path / "無い").returncode == 2
    q = copy.deepcopy(p)
    q["meta"]["sources"]["flow"] = ["他:docs/手順.md"]
    for b in q["boxes"]:
        for s in b.get("src", []):
            s["path"] = "他:docs/手順.md"
    assert run("sources", save(repo, q), repo).returncode == 2          # 「他」の根を渡していない
    assert run("sources", save(repo, q), "他=%s" % repo).returncode == 0


def test_古い形の絵は引用を照らせないと言い_check_は止めずに知らせる(repo):
    p = pic()
    p["tabs"]["ctx"] = {"w": 200, "h": 100}
    p["form"] = "big-picture/1"
    for b in p["boxes"]:
        b.pop("src", None)
    p["meta"].pop("sources")
    f = save(repo, p)
    r = run("check", f)
    assert r.returncode == 0 and "古い形" in r.stdout
    assert run("sources", f, repo).returncode == 2


def _base():
    p = pic()
    p["tabs"]["ctx"] = {"w": 200, "h": 100}
    return p


def _point_all(p, path):
    p["meta"]["sources"]["flow"] = [path]
    for b in p["boxes"]:
        for s in b.get("src", []):
            s["path"] = path


def test_宣言されていない古い設計の文書を正本と名乗る絵は止める(repo):
    p = _base()
    _point_all(p, "docs/古い設計.md")
    p["boxes"][1]["src"][0]["quote"] = "差が 0 になるまで次の段へ進まない。"
    p["boxes"][0]["src"][0]["quote"] = "差が 0 になるまで次の段へ進まない。"
    r = run("sources", save(repo, p), repo)
    assert r.returncode == 1 and "宣言された手順の正本でない" in r.stdout, r.stdout


def test_絵そのものを正本として引く絵は止める(repo):
    p = _base()
    f = repo / "docs" / "絵.json"
    _point_all(p, "docs/絵.json")
    p["boxes"][0]["src"][0]["quote"] = "読んで書く読んで書く読んで書く"
    p["boxes"][1]["src"][0]["quote"] = "訳が分かれば進む訳が分かれば進む"
    f.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    vals = repo / "config" / "skill-values.json"
    vals.write_text(json.dumps({"docs-kit": {"big-picture": {"procedure": ["docs/手順.md", "docs/絵.json"]}}}), encoding="utf-8")
    r = run("sources", f, repo)
    assert r.returncode == 1 and "自分自身" in r.stdout, r.stdout


def test_短すぎる引用は止める(repo):
    p = _base()
    p["boxes"][1]["src"][0]["quote"] = "段"
    r = run("sources", save(repo, p), repo)
    assert r.returncode == 1 and "短すぎる" in r.stdout, r.stdout


@pytest.mark.parametrize("bad", ["../外/手順.md", "/etc/hostname"])
def test_根の外を指す正本は止める(repo, bad):
    p = _base()
    _point_all(p, bad)
    r = run("sources", save(repo, p), repo)
    assert r.returncode == 1 and "根の外" in r.stdout, r.stdout


def test_手順の正本を宣言していない_repo_は照らせない(repo):
    (repo / "config" / "skill-values.json").unlink()
    r = run("sources", save(repo, _base()), repo)
    assert r.returncode == 2 and "宣言していない" in r.stdout, r.stdout


def test_skill_は流れを手順の正本の引用で描くと書く():
    text = (ROOT / "plugins" / "docs-kit" / "skills" / "big-picture" / "SKILL.md").read_text(encoding="utf-8")
    assert "big_picture.py sources" in text
    assert "要約で描かない" in text
    assert "docs-kit.big-picture.procedure" in text
