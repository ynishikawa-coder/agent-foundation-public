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

# 型の差し込み（{{…}}）の頭 → 出てくる順に使う値（作り物）
FILL = {
    "件名": ["備品の貸し出しの決め方", "備品の貸し出しの決め方"],
    "send か copy か artifact": ["copy"],
    "宛名": ["サンプル株式会社 ご担当者様"],
    "前書き": ["答えていただいた内容で、貸し出しの決まりを確定します。"],
    "期限": ["11 月 20 日"],
    "差出人": ["サンプル事務所 担当 見本"],
    "連絡先": ["このメールに返信してください"],
    "版": ["2026-11-13.1"],
    "一言の見出し": ["送料の端数", "届く日", "返す期限"],
    "この答えで決まる事": ["請求の額", "棚の入れ替えの日", "返す期限の知らせを出す日"],
    "問い 1 行": ["送料の端数は、どちらで計算しますか", "新しい棚が届く日は、どちらですか", "返す期限は、どう決めますか"],
    "分かっている事": ["見積りの送料は 1 箱 125.5 円です。", "注文は 10 月 1 日に出ています。", "今は期限が決まっていません。"],
    "表の見出し": ["10 月の請求"],
    "今の計算": ["切り捨てる"],
    "直した場合": ["切り上げる"],
    "行の名": ["合計"],
    "数": ["1,200 円", "1,300 円"],
    "判断に要る細かい事": ["見積りの写しを付けています。"],
    "選択肢の鍵": ["down", "up", "d1020", "d1027", "d7", "d14"],
    "中身の見出し": ["切り捨てる", "切り上げる", "10 月 20 日", "10 月 27 日", "借りた日から 7 日", "借りた日から 14 日"],
    "その結果 1 行": ["合計 1,200 円", "合計 1,300 円", "多くの備品はこれで足ります", "大きい物も足ります"],
    "この後のこと": ["11 月 22 日までに、決まりの写しをお送りします。"],
}


def filled_template(dest="copy"):
    """型（references/template.html）を作り物の中身で埋めた 1 枚。型の決まりが変わらない見張りを兼ねる。"""
    raw = (QA / "references" / "template.html").read_text(encoding="utf-8")
    # 頭の説明（コメント）の中の {{…}} は差し込みでない＝埋めない
    head_end = raw.index("-->") + 3
    text = raw[head_end:]
    used = {k: 0 for k in FILL}

    def fill(m):
        hole = m.group(1)
        for k in sorted(FILL, key=len, reverse=True):
            if hole.startswith(k):
                vals = FILL[k]
                assert used[k] < len(vals), f"差し込み「{k}」の値が足りない"
                used[k] += 1
                return dest if k == "send か copy か artifact" else vals[used[k] - 1]
        raise AssertionError(f"埋め方の無い差し込み: {hole}")

    out = raw[:head_end] + re.sub(r"\{\{([^}]*)\}\}", fill, text)
    left = {k: len(v) - used[k] for k, v in FILL.items() if used[k] != len(v)}
    assert not left, f"使われない値がある（型の差し込みが減った？）: {left}"
    return out


def run_check(path):
    res = subprocess.run([NODE, str(CHECK), str(path), "--json"], capture_output=True, text=True, cwd=path.parent)
    assert res.returncode in (0, 1), res.stderr
    out = json.loads(res.stdout)
    assert out["ok"] == (res.returncode == 0)
    return out


@needs_node
@pytest.mark.parametrize("dest", ["copy", "send", "artifact"])
def test_型を埋めた_1_枚は緑(tmp_path, dest):
    page = tmp_path / "確認.html"
    page.write_text(filled_template(dest), encoding="utf-8")
    out = run_check(page)
    assert out["red"] == [], out["red"]
    assert out["dest"] == dest and out["questions"] == ["q1", "q2", "q3"]


@needs_node
def test_問いのデータの良い例は緑():
    out = run_check(DATA / "good.json")
    assert out["red"] == [], out["red"]
    assert out["dest"] == "artifact" and out["questions"] == ["q1", "q2"]


@needs_node
def test_問いのデータの悪い例は決まった赤だけ():
    out = run_check(DATA / "bad.json")
    assert not out["ok"]
    expect = ["問い q1: 1 問に 2 つ以上", "問い q1: 選択肢が 1 つだけ", "問い q2: 並びが逆", "問い q2: 資料の外の事実の問いに「当てはまらない」",
              "問い q2: ひとことの欄"]
    assert len(out["red"]) == len(expect), out["red"]
    for e in expect:
        assert any(r.startswith(e) for r in out["red"]), (e, out["red"])


@needs_node
def test_問いのデータの選択肢が文字だけなら赤(tmp_path):
    data = json.loads((DATA / "good.json").read_text(encoding="utf-8"))
    data["questions"][0]["options"] = ["借りた日から 7 日", "借りた日から 14 日"]
    page = tmp_path / "q.json"
    page.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    red = run_check(page)["red"]
    assert any("{\"value\",\"label\"}" in r for r in red), red


# 1 か所だけ壊すと、その 1 つの赤だけが出る（壊した所以外の結果が変わらない見張り）
MUTATIONS = [
    ('<body data-dest="copy"', '<body data-dest="mail"', "宛先の印が無い"),
    ('id="copybtn"', 'id="copy-button"', "qa:foot の中身が型と違う"),
    ('<span class="contact">', "<span>", "連絡先"),
    ('name="__版__"', 'name="__ver__"', "版"),
    ("font-size:18px;line-height:1.6", "font-size:15px;line-height:1.6", "qa:css の中身が型と違う"),
    ('<meta name="color-scheme" content="light">', '<meta name="color-scheme" content="light dark">', "暗い色の設定"),
    ('style="--brand:#0f6e66"', 'style="--brand:#ffd43b"', "会社の色 #ffd43b は白地で読みにくい"),
    ("<legend>", '<legend style="color:#c00">', "<legend> に style"),
    ('data-kind="judge"', 'data-kind="ask"', "問い q3: 問いの形"),
    ('data-group="once"', 'data-group="rule"', "問い q3: 並びが逆"),
    ("返す期限は、どう決めますか", "返す期限と置き場所を教えてください", "問い q3: 1 問に 2 つ以上"),
    ("新しい棚が届く日は、どちらですか", "新しい棚が届く日は合っていますか", "問い q2: 「合っていますか」"),
    ("新しい棚が届く日は、どちらですか", "新しい棚の数を教えてください", "問い q2: 数を書かせる問い"),
    ("<b>当てはまらない</b>", "<b>ほかの日</b>", "問い q2: 資料の外の事実の問いに「当てはまらない」"),
    ('name="q2" value="__unknown__"', 'name="q2" value="later"', "問い q2: 「分からない・社内で確かめてから答える」"),
    ('value="d1020" required', 'value="d1020"', "問い q2: 答えずに送れる"),
    ("<b>切り捨てる", "<b>A 切り捨てる", "問い q1: 選択肢に記号"),
    ('value="d7"', 'value="7days!"', "問い q3: 選択肢の鍵（value）"),
    ('name="supp_q1"', 'name="note_q1"', "問い q1: ひとことの欄"),
    (' data-decides="請求の額"', "", "問い q1: この答えで決まる事"),
    ("今は期限が決まっていません。", "照合して決まっていません。", "内部の言葉「照合」"),
    ("今は期限が決まっていません。", "Q2026.11-37 の続きです。", "番号「Q2026.11-37」"),
    ('<details class="more">', '<details class="more" ontoggle="fetch(\'/x\')">', "型の外に動き（on… の属性）"),
    ("見積りの写しを付けています。", '<a href="javascript:alert(1)">見積りの写し</a>', "javascript: の URL"),
    ("見積りの写しを付けています。", '<img src="https://example.com/a.png" alt="見積り">', "外のリソースを読んでいる"),
    ('<meta name="color-scheme" content="light">', '<meta content="light dark" name="color-scheme">', "暗い色の設定"),
    ('<section class="done" id="qa-done" hidden>', '<section class="done" id="qa-done">', "qa:foot の中身が型と違う"),
    ("<h2>答えを確かめてください</h2>", "<h2>これで送ります</h2>", "qa:foot の中身が型と違う"),
    ('id="sendbtn">', 'id="sendbtn" onclick="fetch(\'/x\')">', "qa:foot の中身が型と違う"),
    ("決まりの写しをお送りします。", "決まりの写しをお送りします。<script>fetch('/x')</script>", "「この後のこと」（.next）に書けるのは"),
    ("決まりの写しをお送りします。", '決まりの写しをお送りします。<img src="x" onerror="fetch(\'/x\')">', "「この後のこと」（.next）に書けるのは"),
    ("決まりの写しをお送りします。", "決まりの写しをお送りします。<script>fetch('/x')</script>", "「この後のこと」（.next）に書けるのは", '<p class="lead">', '<p class="lead"><span class="next">ok</span>'),
    ('<details class="more">', '<details class="more"/onclick="fetch(\'/x\')">', "型の外に動き（on… の属性）"),
    ('type="radio" name="q2" value="none"', 'type="checkbox" name="q2" value="none" required', "問い q2: checkbox に required"),
]


@needs_node
@pytest.mark.parametrize("old, new, expect, more", [(*m[:3], m[3:]) for m in MUTATIONS], ids=[m[2] for m in MUTATIONS])
def test_壊した所の赤だけが出る(tmp_path, old, new, expect, more):
    """more＝同時に入れる 2 つ目の書き換え（old2, new2）。囮を置いて照らしをすり抜けられないかを見る。"""
    base = filled_template()
    for o, n in [(old, new), *zip(more[::2], more[1::2])]:
        assert o in base, o
        base = base.replace(o, n, 1)
    page = tmp_path / "確認.html"
    page.write_text(base, encoding="utf-8")
    out = run_check(page)
    assert len(out["red"]) == 1 and out["red"][0].startswith(expect), out["red"]


@needs_node
def test_この後のことは差し替えても緑(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template().replace("11 月 22 日までに、決まりの写しをお送りします。", "来週中に<br>お電話します。", 1), encoding="utf-8")
    assert run_check(page)["red"] == []


@needs_node
def test_型の外の_script_は赤(tmp_path):
    base = filled_template()
    page = tmp_path / "確認.html"
    page.write_text(base.replace("</form>", "</form><script>fetch('/x')</script>", 1), encoding="utf-8")
    red = run_check(page)["red"]
    assert len(red) == 1 and red[0].startswith("型の外に <script>"), red
