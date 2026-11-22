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
    meta = 0 if pic["meta"].get("intent") else 1   # 絵の意図（meta.intent）の空きも 1 つの赤い点
    assert len(reds) == len(empty) + meta and empty, "意図の空いた箱は赤い点として全部出る"
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
    # 欄の形と絵の値の結びは tests/test_jimoji_dake_de_terasanai.py が explain で照らす。ここは命令の口が同じ文を出すか
    assert bp.explain(agreed(), "p1") in r.stdout


def test_無い問題は説明しない():
    assert run("explain", DODAI, "無い").returncode == 1


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(meta=[]), lambda p: p.update(boxes={}), lambda p: p["arrows"].append("a2>a3"),
    lambda p: p.update(tabs=[]),
])
def test_形の崩れた_JSON_は落ちずに照らせないで止まる(tmp_path, mutate):
    a = agreed()
    mutate(a)
    errs, _ = bp.check(a)
    assert errs
    r = run("compare", write(tmp_path, "a.json", a), write(tmp_path, "x.json", actual_from(agreed())))
    assert r.returncode == 2 and "照らせない" in r.stdout, r.stdout + r.stderr


def test_土台の絵は配りの器から全部の_plugin_へ流れを描く():
    """代表の 1 本で済ませない（実物の絵と同じ粗さ）。plugin の箱は配りの器から全部繋がる。"""
    pic = agreed()
    # plugin の箱＝題の頭（「（」の前）が plugins/ の下の名の部品。plugin の外の部品（公開の検査）は配りの器から入らない。
    plugins = {p.name for p in (ROOT / "plugins").iterdir() if (p / ".claude-plugin" / "plugin.json").is_file()}
    parts = {b["id"] for b in pic["boxes"] if b["tab"] == "arch" and b["k"] == "part" and b["t"].split("（")[0] in plugins}
    assert len(parts) == len(plugins), (parts, plugins)
    fed = {a["to"] for a in pic["arrows"] if a["from"] == "a2"}
    assert parts <= fed, parts - fed


def test_設計書の型は全体の絵の下に置かれる():
    """全体の絵が上・spec-doc は部品ごとの細部（決定 2026-11-19）。両方の SKILL が互いを指す。"""
    spec_doc = (ROOT / "plugins" / "dev-flow" / "skills" / "spec-doc" / "SKILL.md").read_text(encoding="utf-8")
    assert "big-picture" in spec_doc and "全体の絵の下で部品ごとの細部" in spec_doc
    assert "唯一の正解" not in spec_doc, "設計書を全体の絵より上の正と書かない"
    assert "spec-doc" in (SKILL / "SKILL.md").read_text(encoding="utf-8")


def test_main_へ入れる手を片方の_AI_に限らない():
    """照らす段が green なら、どちらの AI の親窓が入れてもよい（決定 2026-11-19）。"""
    for f in ("CONTRIBUTING.md", ".github/pull_request_template.md"):
        text = (ROOT / f).read_text(encoding="utf-8")
        assert "Javis 側の親窓" not in text, f"{f} に畳んだ決まりの写しが残っている"
    github = next(b for b in agreed()["boxes"] if b["id"] == "github")
    assert github["intent"] and "どちらの AI" in github["what"]


# --- 1 repo に製品が複数ある形（点 13 の pick） ---

def _repo(tmp_path, agreed=None, pics=("docs/全体の絵.json",)):
    for p in pics:
        f = tmp_path / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(DODAI.read_text(encoding="utf-8"), encoding="utf-8")
    if agreed is not None:
        (tmp_path / "config").mkdir(exist_ok=True)
        (tmp_path / "config" / "skill-values.json").write_text(
            json.dumps({"docs-kit": {"big-picture": {"agreed": agreed}}}, ensure_ascii=False), encoding="utf-8")
    return tmp_path


MULTI = [
    {"name": "うみ", "path": "docs/絵/うみ.json", "covers": ["apps/umi", "packages/umi-core"]},
    {"name": "やま", "path": "docs/絵/やま.json", "covers": ["apps/yama"]},
]


def test_製品が複数の_repo_は触った製品の絵だけを選ぶ(tmp_path):
    root = _repo(tmp_path, MULTI, pics=("docs/絵/うみ.json", "docs/絵/やま.json"))
    chosen, errs = bp.pick(root, ["apps/umi/a.py", "packages/umi-core/b.py"])
    assert not errs and [c[0] for c in chosen] == ["うみ"]
    chosen, errs = bp.pick(root, ["apps/umi/a.py", "apps/yama/c.py"])
    assert not errs and [c[0] for c in chosen] == ["うみ", "やま"]
    r = run("pick", root, "apps/yama/c.py")
    assert r.returncode == 0 and "絵 やま docs/絵/やま.json" in r.stdout and "うみ" not in r.stdout


def test_どの絵も覆わない_file_があれば照らせない(tmp_path):
    root = _repo(tmp_path, MULTI, pics=("docs/絵/うみ.json", "docs/絵/やま.json"))
    r = run("pick", root, "apps/umi/a.py", "apps/other/x.py")
    assert r.returncode == 2 and "apps/other/x.py" in r.stdout and "絵 うみ" not in r.stdout


@pytest.mark.parametrize("bad", [
    [{"name": "うみ", "path": "docs/絵/うみ.json"}],                                  # covers が無い
    [{"name": "うみ", "path": "docs/絵/うみ.json", "covers": []}],                    # covers が空
    [{"name": "うみ", "path": "docs/絵/うみ.json", "covers": ["/"]},
     {"name": "うみ", "path": "docs/絵/うみ.json", "covers": ["/"]}],                 # name が重なる
    [{"name": "", "path": "docs/絵/うみ.json", "covers": ["/"]}],                     # name が空
    [{"name": "やま", "path": "docs/絵/無い.json", "covers": ["/"]}],                 # 絵が無い
    {"name": "うみ"},                                                                  # 並びでない
    [],                                                                                # 空の並び
])
def test_値の形の誤りは照らせない(tmp_path, bad):
    root = _repo(tmp_path, bad, pics=("docs/絵/うみ.json",))
    assert run("pick", root, "apps/umi/a.py").returncode == 2


def test_値が無ければ土台の絵_1_枚_無ければ照らせない(tmp_path):
    root = _repo(tmp_path)
    r = run("pick", root, "any/file.py")
    assert r.returncode == 0 and "絵 全体 docs/全体の絵.json" in r.stdout
    empty = tmp_path / "empty"
    empty.mkdir()
    assert run("pick", empty, "any/file.py").returncode == 2
    assert run("pick", root).returncode == 2, "触った file が渡されなければ照らせない"
