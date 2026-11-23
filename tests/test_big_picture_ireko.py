"""全体の絵の箱どうしの関わり（入れ子 in・別のタブの参照 see）を欄で持てるか（注入の試験）。

合格の線: 指す先の誤った in／see を入れると check が誤り（exit 1）で拒む。照らしは入れ子の差を欄 2 の差に数える。
土台の絵は、箱の関わりを what の文に id で写さない。
"""
import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "docs-kit" / "skills" / "big-picture" / "scripts" / "big_picture.py"
DODAI = ROOT / "docs" / "全体の絵.json"

spec = importlib.util.spec_from_file_location("big_picture", TOOL)
bp = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(bp)


def pic():
    return json.loads(DODAI.read_text(encoding="utf-8"))


def box(p, i):
    return next(b for b in p["boxes"] if b["id"] == i)


def test_土台の絵は入れ子と参照を欄で持ち形が通る():
    p = pic()
    assert box(p, "a9")["in"] == "a13" and box(p, "a10")["in"] == "a13"
    assert box(p, "github")["see"]
    errs, _ = bp.check(p)
    assert errs == []


def test_土台の絵は箱の関わりを_what_に_id_で写さない():
    p = pic()
    ids = {b["id"] for b in p["boxes"]}
    for b in p["boxes"]:
        hits = [i for i in re.findall(r"（([A-Za-z][A-Za-z0-9_-]*)）", b["what"]) if i in ids and i != b["id"]]
        assert not hits, "%s の what が箱 %s を文で指す（in／see の欄で持つ）" % (b["id"], hits)


@pytest.mark.parametrize("bad, want", [
    (lambda p: box(p, "a9").__setitem__("in", "nai"), "in（中に入る箱）"),
    (lambda p: box(p, "a9").__setitem__("in", "a9"), "自分を指す"),
    (lambda p: box(p, "a9").__setitem__("in", "github"), "別のタブ"),
    (lambda p: (box(p, "a13").__setitem__("in", "a9")), "輪になる"),
    (lambda p: box(p, "github").__setitem__("see", "f8"), "id の並びでない"),
    (lambda p: box(p, "github").__setitem__("see", []), "id の並びでない"),
    (lambda p: box(p, "github").__setitem__("see", ["nai"]), "see の箱"),
    (lambda p: box(p, "github").__setitem__("see", ["github"]), "自分を指す"),
    (lambda p: box(p, "github").__setitem__("see", ["dodai"]), "同じタブ"),
    (lambda p: box(p, "github").__setitem__("see", ["f8", "f8"]), "重なる"),
])
def test_指す先の誤った_in_see_を拒む(bad, want, tmp_path):
    p = pic()
    bad(p)
    errs, _ = bp.check(p)
    assert any(want in e for e in errs), errs
    f = tmp_path / "e.json"
    f.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    res = subprocess.run([sys.executable, str(TOOL), "check", str(f)], capture_output=True, text=True)
    assert res.returncode == 1


def test_照らしは入れ子の差を差に数える():
    a = pic()
    x = copy.deepcopy(a)
    x["meta"]["kind"] = "実物"
    x["meta"].pop("agreed", None)
    x["meta"]["drawn_from"] = "agent-foundation-public@0123456789ab"
    x["meta"]["drawn_by"] = "session_REVIEW01"
    _, same = bp.compare(a, x)
    del box(x, "a9")["in"]
    md, diffs = bp.compare(a, x)
    assert diffs == same + 1 and "入っている箱が違う" in md



def test_照らしは別のタブの参照の差を差に数える():
    a = pic()
    x = copy.deepcopy(a)
    x["meta"]["kind"] = "実物"
    x["meta"].pop("agreed", None)
    x["meta"]["drawn_from"] = "agent-foundation-public@0123456789ab"
    x["meta"]["drawn_by"] = "session_REVIEW01"
    _, same = bp.compare(a, x)
    box(x, "github")["see"] = ["f5", "f6"]
    md, diffs = bp.compare(a, x)
    assert diffs == same + 1 and "別のタブで関わる箱が違う" in md
