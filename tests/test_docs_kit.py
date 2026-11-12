"""docs-kit プラグインが「プラグインとして入る形」か、と qa-html の検査（check.mjs）の自分の試験。"""
import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "docs-kit"
SKILLS = PLUGIN / "skills"
DATA = Path(__file__).resolve().parent / "docs_kit"
QA = SKILLS / "qa-html"
CHECK = QA / "check.mjs"
NAMES = {"blueprint", "compose-message", "make-deck", "mindmap", "pdf-read", "qa-html", "theory-mock"}
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node が無い（qa-html の検査は node で動く）")


# ── プラグインとして入る形 ──────────────────────────────────────────


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{path}: 頭の --- の欄が無い"
    out = {}
    for line in m.group(1).splitlines():
        k, sep, v = line.partition(":")
        if sep and not line.startswith(" "):
            out[k.strip()] = v.strip()
    return out


def test_plugin_json_が読めて名前が合う():
    data = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["name"] == "docs-kit"
    assert data.get("description")


def test_skills_は_7_本で余りが無い():
    dirs = {p.name for p in SKILLS.iterdir() if p.is_dir()}
    assert dirs == NAMES


@pytest.mark.parametrize("name", sorted(NAMES))
def test_skill_の頭の欄(name):
    fm = frontmatter(SKILLS / name / "SKILL.md")
    assert fm.get("name") == name
    assert len(fm.get("description", "")) >= 20


@pytest.mark.parametrize("name", sorted(NAMES))
def test_skill_が指す付属の物がある(name):
    """SKILL.md が名指しする references/・scripts/・prompts/・check.mjs が skill の dir にある。"""
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    refs = set(re.findall(r"(?<![\w/$])((?:references|scripts|prompts)/[\w.\-]+\.\w+|check\.mjs)", text))
    for ref in refs:
        assert (SKILLS / name / ref).is_file(), f"{name}: {ref} が無い"


def test_付属の_python_が読める():
    for py in sorted(SKILLS.glob("*/scripts/*.py")):
        ast.parse(py.read_text(encoding="utf-8"), filename=str(py))  # 読むだけ（プラグインの中に __pycache__ を作らない）


def test_土台の外の置き場を指さない():
    """プラグインは入れた先で動く＝作った所の repo の中の path や、他の repo の内部の path を書かない。"""
    bad = re.compile(r"git rev-parse --show-toplevel\)/plugins/|\.claude/skills/|core/rules/|agents/javis")
    files = [p for p in PLUGIN.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    hits = [f"{p.relative_to(ROOT)}" for p in files if bad.search(p.read_text(encoding="utf-8"))]
    assert not hits, hits


def test_make_deck_の差し込みが埋まる_欠ければ止まる(tmp_path):
    render = SKILLS / "make-deck" / "scripts" / "render_prompt.py"
    out = tmp_path / "p.txt"
    ok = subprocess.run([sys.executable, "-B", str(render), "render", "--values",
                         str(SKILLS / "make-deck" / "prompts" / "case.example.json"), "--out", str(out)],
                        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    assert "<<" not in out.read_text(encoding="utf-8")
    thin = tmp_path / "case.json"
    thin.write_text('{"対象": "x"}', encoding="utf-8")
    ng = subprocess.run([sys.executable, "-B", str(render), "render", "--values", str(thin), "--out", str(tmp_path / "q.txt")],
                        capture_output=True, text=True)
    assert ng.returncode != 0


# ── qa-html の検査 ──────────────────────────────────────────────────

FILL = {
    "宛名": ["オーナーへの確認"],
    "題": ["備品の貸し出しの決め方", "備品の貸し出しの決め方"],
    "前書き": ["貸し出しの決まりで確かめたい事が 3 件あります。"],
    "send か copy": ["copy"],
    "一言の見出し": ["送料の端数", "納品日", "返す期限"],
    "問い 1 行": ["送料の端数は、どちらが正しいですか", "新しい棚の納品日はいつですか", "返す期限は、どう決めますか"],
    "分かっている事": ["A なら 合計 1,200 円・B なら 合計 1,300 円です。", "注文は 10 月 1 日に出ています。", "今は期限が決まっていません。"],
    "候補 A": ["切り捨て", "借りた日から 7 日"],
    "候補 B": ["切り上げ", "借りた日から 14 日"],
    "A ならどうなるか": ["合計 1,200 円"],
    "B ならどうなるか": ["合計 1,300 円"],
    "中身 1 行": ["多くの備品はこれで足ります", "大きい物も足ります"],
    "分かる": ["分かる（補足に書く）"],
    "分かったら次の": ["分かったら次の確認でまた伺います"],
    "判断に要る細かい事": ["見積りの写しを付けています。"],
    "この答えで決まる事": ["請求の額", "棚の入れ替えの日", "返す期限の知らせを出す日"],
    "…": [""],
}


def filled_template():
    """型（references/template.html）を作り物の中身で埋めた 1 枚。型の決まりが変わらない見張りを兼ねる。"""
    text = (QA / "references" / "template.html").read_text(encoding="utf-8")
    used = {k: 0 for k in FILL}

    def fill(m):
        hole = m.group(1)
        for k in sorted(FILL, key=len, reverse=True):
            if hole.startswith(k):
                vals = FILL[k]
                v = vals[min(used[k], len(vals) - 1)]
                used[k] += 1
                return v
        raise AssertionError(f"埋め方の無い差し込み: {hole}")

    return re.sub(r"\{\{([^}]*)\}\}", fill, text)


def run_check(path):
    res = subprocess.run([NODE, str(CHECK), str(path), "--json"], capture_output=True, text=True, cwd=path.parent)
    assert res.returncode in (0, 1), res.stderr
    out = json.loads(res.stdout)
    assert out["ok"] == (res.returncode == 0)
    return out


@needs_node
def test_型を埋めた_1_枚は緑(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template(), encoding="utf-8")
    out = run_check(page)
    assert out["red"] == [], out["red"]
    assert out["dest"] == "copy" and out["questions"] == ["q1", "q2", "q3"]


@needs_node
@pytest.mark.parametrize("name, dest, n", [("good_artifact.html", "artifact", 1), ("good.json", "artifact", 2)])
def test_確認のページの良い例は緑(name, dest, n):
    out = run_check(DATA / name)
    assert out["red"] == [], out["red"]
    assert out["dest"] == dest and len(out["questions"]) == n


@needs_node
def test_問いのデータの悪い例は決まった赤だけ():
    out = run_check(DATA / "bad.json")
    assert not out["ok"]
    expect = ["問い q1: 1 問に 2 つ以上", "問い q1: 選択肢が 1 つだけ", "問い q2: 資料の外の事実の問いに「該当しない」",
              "問い q2: 自由記述の補足"]
    assert len(out["red"]) == len(expect), out["red"]
    for e in expect:
        assert any(r.startswith(e) for r in out["red"]), (e, out["red"])


# 1 か所だけ壊すと、その 1 つの赤だけが出る（壊した所以外の結果が変わらない見張り）
MUTATIONS = [
    ('<body data-dest="copy"', '<body data-dest="mail"', "宛先の印が無い"),
    ('id="copybtn"', 'id="copy-button"', "写す宛先なのに写すボタン"),
    ('data-kind="judge"', 'data-kind="ask"', "問い q3: 問いの形"),
    ("返す期限は、どう決めますか", "返す期限と置き場所を教えてください", "問い q3: 1 問に 2 つ以上"),
    ("新しい棚の納品日はいつですか", "新しい棚の納品日は合っていますか", "問い q2: 「合っていますか」"),
    ("新しい棚の納品日はいつですか", "新しい棚の数を教えてください", "問い q2: 数を書かせる問い"),
    ("<b>該当しない</b>", "<b>ほかの日</b>", "問い q2: 資料の外の事実の問いに「該当しない」"),
    ('name="supp_q1"', 'name="note_q1"', "問い q1: 自由記述の補足"),
    ("<p class=\"decides\">請求の額</p>", "", "問い q1: 「この答えで決まる事」"),
    ("今は期限が決まっていません。", "照合して決まっていません。", "内部の言葉「照合」"),
    ("今は期限が決まっていません。", "Q2026.11-37 の続きです。", "番号「Q2026.11-37」"),
]


@needs_node
@pytest.mark.parametrize("old, new, expect", MUTATIONS, ids=[m[2] for m in MUTATIONS])
def test_壊した所の赤だけが出る(tmp_path, old, new, expect):
    base = filled_template()
    assert old in base, old
    page = tmp_path / "確認.html"
    page.write_text(base.replace(old, new, 1), encoding="utf-8")
    out = run_check(page)
    assert len(out["red"]) == 1 and out["red"][0].startswith(expect), out["red"]


@needs_node
def test_body_の印が根の要素の印に勝つ(tmp_path):
    text = (DATA / "good_artifact.html").read_text(encoding="utf-8")
    page = tmp_path / "p.html"
    page.write_text('<body data-dest="artifact">' + text.replace('data-dest="artifact"', 'data-dest="mail"') + "</body>", encoding="utf-8")
    assert run_check(page)["red"] == []
