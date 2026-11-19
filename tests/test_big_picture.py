"""docs-kit の big-picture（全体の絵）の道具と、土台の絵（docs/全体の絵.json）の自分の試験。

合格の線: わざと合意した絵と違う実物を作ると、照らし（compare）が差ありで止まる（exit 1）。
"""
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "plugins" / "docs-kit" / "skills" / "big-picture"
TOOL = SKILL / "scripts" / "big_picture.py"
DODAI = ROOT / "docs" / "全体の絵.json"

spec = importlib.util.spec_from_file_location("big_picture", TOOL)
bp = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True   # plugins/ の中に __pycache__ を作らない
spec.loader.exec_module(bp)


def agreed():
    return json.loads(DODAI.read_text(encoding="utf-8"))


def actual_from(pic):
    """合意した絵と同じ中身の「実物の絵」（レビューの窓が描いた形）。"""
    x = copy.deepcopy(pic)
    x["meta"]["kind"] = "実物"
    x["meta"].pop("agreed", None)
    x["meta"]["drawn_from"] = "agent-foundation-public@0123456789ab"
    x["meta"]["drawn_by"] = "session_REVIEW01"
    for b in x["boxes"]:
        b["intent"] = None   # 実物の絵は意図を持たない（意図は照らさない）
    return x


def run(*args):
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True)


def write(tmp_path, name, pic):
    p = tmp_path / name
    p.write_text(json.dumps(pic, ensure_ascii=False), encoding="utf-8")
    return p


# ── 土台の絵 ──────────────────────────────────────────────


def test_土台の絵は合意した版で形の誤りが無い():
    pic = agreed()
    errs, reds = bp.check(pic)
    assert errs == []
    assert pic["meta"]["kind"] == "合意" and pic["meta"]["agreed"]["by"] == "owner"
    assert bp.VERSION.match(pic["meta"]["version"])


def test_土台の絵は_4_つの必ず載せる物を持つ():
    pic = agreed()
    assert pic["meta"]["problem"] and pic["meta"]["goal"]          # 解決したい問題と完成像
    assert {b["tab"] for b in pic["boxes"]} == set(bp.TABS)        # 部品と流れ（3 タブ）
    assert {b["side"] for b in pic["boxes"]} >= {"共通", "個別"}    # 共通と個別の境
    assert any(b.get("role") == "決める" for b in pic["boxes"])    # 人が決める所


def test_土台の絵の意図の空きは赤い点で全部出る():
    pic = agreed()
    _, reds = bp.check(pic)
    empty = [b for b in pic["boxes"] if not b.get("intent")]
    assert len(reds) == len(empty) and empty, "意図の空いた箱は赤い点として全部出る"
    r = run("check", DODAI)
    assert r.returncode == 0 and "赤い点" in r.stdout and "CHECK OK" in r.stdout


def test_土台の絵は描き直せて外の物を読まない(tmp_path):
    out = tmp_path / "e.html"
    r = run("render", DODAI, "-o", out)
    assert r.returncode == 0, r.stdout
    html = out.read_text(encoding="utf-8")
    assert "<title>土台の全体の絵</title>" in html
    assert bp.SLOT not in html and '"form": "big-picture/1"' in html
    assert "http://" not in html and "https://" not in html   # file:// で動く
    for word in ("意図", "起きた問題", "説明", "4. 決めた事と意図"):
        assert word in html


# ── 合格の線: わざと違う実物は red ─────────────────────────────


def test_同じ実物は差なしで通る(tmp_path):
    r = run("compare", DODAI, write(tmp_path, "x.json", actual_from(agreed())))
    assert r.returncode == 0, r.stdout
    assert "差: 0 件" in r.stdout


def _drop_box(x):
    x["boxes"] = [b for b in x["boxes"] if b["id"] != "f7"]
    x["arrows"] = [a for a in x["arrows"] if "f7" not in (a["from"], a["to"])]
    x["problems"] = []


def _add_box(x):
    x["boxes"].append(dict(id="zz", tab="arch", t="勝手に足した部品", k="part", side="共通",
                           x=10, y=10, w=80, h=40, what="作り物", why="作り物", intent=None))


def _drop_flow(x):
    x["arrows"] = [a for a in x["arrows"] if (a["from"], a["to"]) != ("f7", "f10")]


def _add_flow(x):
    x["arrows"].append({"from": "f6", "to": "f8"})   # 照らす段を飛ばして入れる流れ


def _side(x):
    next(b for b in x["boxes"] if b["id"] == "a9")["side"] = "共通"


def _role(x):
    b = next(b for b in x["boxes"] if b["id"] == "f10")
    b["k"], b["role"] = "ai", ""


@pytest.mark.parametrize("mutate,欄", [
    (_drop_box, "欄 2"), (_add_box, "欄 2"), (_drop_flow, "欄 2"), (_add_flow, "欄 2"),
    (_side, "欄 3"), (_role, "欄 4"),
])
def test_わざと絵と違う実物を作ると_red(tmp_path, mutate, 欄):
    x = actual_from(agreed())
    mutate(x)
    r = run("compare", DODAI, write(tmp_path, "x.json", x))
    assert r.returncode == 1, r.stdout
    assert "差あり" in r.stdout and "止め" in r.stdout
    head = r.stdout.index("## " + 欄)
    body = r.stdout[head:].split("\n## ")[0]
    assert "差なし" not in body, body


def test_合意の印の無い絵とは照らさない(tmp_path):
    a = agreed()
    del a["meta"]["agreed"]
    r = run("compare", write(tmp_path, "a.json", a), write(tmp_path, "x.json", actual_from(agreed())))
    assert r.returncode == 2 and "照らせない" in r.stdout


def test_合意した絵どうし_取り違えは照らさない(tmp_path):
    r = run("compare", DODAI, DODAI)
    assert r.returncode == 2 and "取り違え" in r.stdout


def test_描いた元と描いた窓の無い実物は照らさない(tmp_path):
    x = actual_from(agreed())
    del x["meta"]["drawn_by"]
    r = run("compare", DODAI, write(tmp_path, "x.json", x))
    assert r.returncode == 2


def test_意図の違いは差に数えない(tmp_path):
    x = actual_from(agreed())
    x["boxes"][0]["intent"] = "実物の側で書いた別の文"
    assert run("compare", DODAI, write(tmp_path, "x.json", x)).returncode == 0


# ── 形の誤りは既定で止める ───────────────────────────────────


@pytest.mark.parametrize("mutate,word", [
    (lambda p: p["boxes"][0].pop("intent"), "intent の欄が無い"),
    (lambda p: p["boxes"][0].update(side="たぶん共通"), "side"),
    (lambda p: p["boxes"][0].update(k="謎"), " k "),
    (lambda p: p["boxes"].append(dict(p["boxes"][0])), "重なる"),
    (lambda p: p["arrows"].append({"from": "owner", "to": "無い箱"}), "端の箱が無い"),
    (lambda p: p["arrows"].append({"from": "owner", "to": "f1"}), "タブをまたぐ"),
    (lambda p: p["meta"].update(version="v1"), "YYYY-MM-DD.n"),
    (lambda p: p["meta"].pop("goal"), "完成像"),
    (lambda p: next(b for b in p["boxes"] if b["k"] == "owner").pop("role"), "role"),
    (lambda p: p["problems"][0].update(origin="たぶん"), "origin"),
    (lambda p: p["problems"][0].update(cause="無い箱"), "原因の箱"),
    (lambda p: p["problems"][0].update(why_here=""), "why_here"),
])
def test_形の誤りは止める(mutate, word):
    pic = agreed()
    mutate(pic)
    errs, _ = bp.check(pic)
    assert any(word in e for e in errs), errs
    with pytest.raises(ValueError):
        bp.render(pic)


# ── 説明（チャットの文） ─────────────────────────────────────


def test_説明は箱の名と原因と意図を挙げる():
    r = run("explain", DODAI, "p1")
    assert r.returncode == 0, r.stdout
    for word in ("起きた所", "原因の箱", "構造から来る", "流れ", "この箱の意図", "なぜここから起きたか", "【実物が絵どおりか】"):
        assert word in r.stdout, word


def test_無い問題は説明しない():
    assert run("explain", DODAI, "無い").returncode == 1


def test_review_pr_の点_13_が道具を指す():
    skill = (ROOT / "plugins" / "checker" / "skills" / "review-pr" / "SKILL.md").read_text(encoding="utf-8")
    assert "| 13 全体の絵 |" in skill
    assert "big_picture.py compare" in skill and "docs/全体の絵.json" in skill
    assert "書いた窓の申告" in skill
