"""docs-kit プラグインが「プラグインとして入る形」か、と qa-html の検査（check.mjs）の自分の試験。"""
import ast
import json
import os
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
    "読んだ資料": ["見積り書（10 月分）・10 月 1 日に受け取り", "注文書の控え・10 月 1 日に受け取り", "貸し出しの決まり・9 月 10 日に受け取り"],
    "答えるまでの扱い": ["答えが届くまで、この点は確定せずにお待ちします。"],
    "期限": ["11 月 20 日"],
    "差出人": ["サンプル事務所 担当 見本"],
    "連絡先": ["このメールに返信してください"],
    "版": ["2026-11-13.1"],
    "一言の見出し": ["送料の端数", "届く日", "返す期限"],
    "まとまりの 1 行": ["決まりと合わない所です", "届いた物の確かめです", "今回の催しの分だけの事です"],
    "何について: 誰": ["全員", "見本さん", "全員"],
    "何について: いつ": ["10 月分", "10 月分", "10 月分"],
    "何について: 何": ["送料", "棚が届く日"],
    "問い 1 行": ["送料の端数は、どちらで計算しますか", "新しい棚が届く日は、どちらですか", "返す期限は、どう決めますか"],
    "見つけた事": ["見積り書の 2 枚目は、送料 1 箱 125.5 円です。", "見積り書と注文書の控えに、届く日の書きがありません。", "今は期限が決まっていません。"],
    "表の見出し": ["10 月の請求"],
    "今の計算": ["切り捨てる"],
    "直した場合": ["切り上げる"],
    "行の名": ["合計"],
    "数": ["1,200 円", "1,300 円"],
    "切り抜きの画像": ["data:image/png;base64,iVBORw0KGgo="],
    "切り抜きに写っている事": ["見積り書の送料の行"],
    "切り抜きの資料名と場所": ["見積り書 2 枚目"],
    "判断に要る細かい事": ["見積りの写しを付けています。", "注文は 10 月 1 日に出ています。", "大きい物は 7 日では足りない事があります。"],
    "原文": ["送料 1 箱 125.5 円（税別）"],
    "選択肢の鍵": ["down", "up", "d1020", "d1027", "d7", "d14"],
    "中身の見出し": ["切り捨てる", "切り上げる", "10 月 20 日", "10 月 27 日", "借りた日から 7 日", "借りた日から 14 日"],
    "この答えで変わる事": ["10 月の請求が合計 1,200 円", "10 月の請求が合計 1,300 円", "棚の入れ替えが 10 月 21 日", "棚の入れ替えが 10 月 28 日",
                       "返す日の知らせが借りた日から 7 日目", "返す日の知らせが借りた日から 14 日目"],
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
    expect = ["答えるまでの扱いが無い", "問い q1: なぜ聞くか", "問い q1: 1 問に 2 つ以上", "問い q1: 選択肢が 1 つだけ", "問い q2: 並びが逆",
              "問い q2: 切り抜き 1 の画像が無い", "問い q2: 選択肢「まだ分からない」にこの答えで変わる事", "問い q2: 資料の外の事実の問いに「当てはまらない」",
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


@needs_node
def test_前提が書けない問いのデータは赤(tmp_path):
    """何について・見つけた事・資料・なぜ聞くか・くわしく・変わる事が空なら出さない（前提が書けない問いは出さない）。"""
    data = json.loads((DATA / "good.json").read_text(encoding="utf-8"))
    q = data["questions"][0]
    for k in ["about", "known", "docs", "why", "more"]:
        q.pop(k)
    q["options"][0].pop("change")
    data["questions"][1]["clips"][1]["shows"] = ["見本さん", "ほかの人"]
    page = tmp_path / "q.json"
    page.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    red = run_check(page)["red"]
    expect = ["問い q1: 何について", "問い q1: なぜ聞くか", "問い q1: 見つけた事（資料名・場所・値）が無い", "問い q1: 見つけた事が読んだ資料を指していない",
              "問い q1: くわしく", "問い q1: 選択肢「借りた日から 7 日」にこの答えで変わる事", "問い q2: 切り抜き 2 に問いの人の外の名「ほかの人」"]
    assert len(red) == len(expect), red
    for e in expect:
        assert any(r.startswith(e) for r in red), (e, red)


@needs_node
def test_食い違いの切り抜きは_2_枚(tmp_path):
    data = json.loads((DATA / "good.json").read_text(encoding="utf-8"))
    data["questions"][1]["clips"].pop()
    page = tmp_path / "q.json"
    page.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    red = run_check(page)["red"]
    assert len(red) == 1 and red[0].startswith("問い q2: 食い違いの切り抜きは 2 枚"), red


@needs_node
def test_なぜ聞くかの文は会社の表で替えられる(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template().replace(">今回だけの事を確かめます<", ">この月だけの事を確かめます<", 1), encoding="utf-8")
    assert run_check(page)["red"][0].startswith("問い q3: なぜ聞くかの文は決まった文")
    values = tmp_path / "config" / "skill-values.json"
    values.parent.mkdir()
    values.write_text(json.dumps({"docs-kit": {"qa-html": {"why": {"once": "この月だけの事を確かめます"}}}}, ensure_ascii=False), encoding="utf-8")
    assert run_check(page)["red"] == []


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
    ("<b>当てはまらない</b>", '<b>ほかの日</b><small class="chg">届く日を表に入れます</small>', "問い q2: 資料の外の事実の問いに「当てはまらない」"),
    ('name="q2" value="__unknown__"', 'name="q2" value="later"', "問い q2: 「分からない・社内で確かめてから答える」"),
    ('value="d1020" required', 'value="d1020"', "問い q2: 答えずに送れる"),
    ("<b>切り捨てる", "<b>A 切り捨てる", "問い q1: 選択肢に記号"),
    ('value="d7"', 'value="7days!"', "問い q3: 選択肢の鍵（value）"),
    ('name="supp_q1"', 'name="note_q1"', "問い q1: ひとことの欄"),
    # 前提の 3 段（はじめの画面・まとまり・1 問の 4 欄・切り抜き・変わる事）
    ('<p class="hold">', '<p class="note">', "答えるまでの扱いが無い"),
    ('<li data-doc="d3">', '<li data-doc="d-4">増えた資料</li><li data-doc="d3">', "読んだ資料の鍵（data-doc）"),
    ('data-docs="d2 d3"', 'data-docs="d2 d9"', "問い q2: 見つけた事の資料「d9」が読んだ資料の一覧に無い"),
    ('data-docs="d2 d3"', 'data-docs=""', "問い q2: 見つけた事が読んだ資料を指していない"),
    ("見積り書と注文書の控えに、届く日の書きがありません。", "", "問い q2: 見つけた事（資料名・場所・値）が無い"),
    ("今は期限が決まっていません。", "今は期限が決まっていません。" + "借りた物を返す日の決まりは、どの資料にも書かれていませんでした。" * 2, "問い q3: 見つけた事の 1 行が"),
    ("資料に書いてありません</p>", "資料が足りません</p>", "問い q2: なぜ聞くかの文は決まった文"),
    ('data-why="once"', 'data-why="month"', "問い q3: なぜ聞くか"),
    ('data-kind="choose"', 'data-kind="mismatch"', "問い q1: 食い違いの問い（mismatch）"),
    ('<p class="about"><span>全員</span><span>10 月分</span></p>', "", "問い q3: 何について"),
    ("<span>送料</span>", "<span>送料</span><span>請求</span>", "問い q1: 何についての札が 4 つ"),
    ('<p class="glead">届いた物の確かめです</p>', "", "問い q2: まとまりの最初の問いに"),
    ("届いた物の確かめです", "届いた物の<br>確かめです", "問い q2: まとまりの 1 行が 2 行"),
    ('data-group="person"', 'data-group="rule"', "問い q2: まとまりの 1 行はまとまりの最初の問いだけ"),
    ('<details class="more"><summary>くわしく</summary>注文は 10 月 1 日に出ています。</details>', "", "問い q2: くわしく"),
    ("注文は 10 月 1 日に出ています。", "注文は 10 月 1 日です。<br>届く日は未定です。<br>棚は 2 台です。<br>置き場は 1 階です。", "問い q2: くわしくが 4 行"),
    ('<small class="chg">棚の入れ替えが 10 月 28 日</small>', "", "問い q2: 選択肢「10 月 27 日」にこの答えで変わる事"),
    ('data-shows=""', 'data-shows="見本さん"', "問い q1: 切り抜き 1 に問いの人の外の名「見本さん」"),
    ('alt="見積り書の送料の行"', 'alt="見本さんの送料の行"', "問い q1: 切り抜き 1 の説明に問いの人の外の名「見本さん」"),
    ('data-doc="d1" data-shows', 'data-doc="d7" data-shows', "問い q1: 切り抜き 1 の資料「d7」"),
    ("</figure></div>", "</figure>" + '<figure class="clip" data-doc="d2" data-shows=""><img src="data:image/png;base64,AAAA" alt="注文書の控え"></figure>' * 2 + "</div>", "問い q1: 切り抜きが 3 枚"),
    ("</figure></div>", "</figure>" + '<figure class="clip" data-doc="d2" data-shows=""><img src="data:image/png;base64,AAAA" alt="注文書の控え"><figcaption>注文書の控え</figcaption></figure></div>', None),
    ('data-doc="d1" data-shows=""', 'data-doc="d1"', "問い q1: 切り抜き 1 に写っている人の名"),
    ('<span class="who">見本さん</span>', "<span>見本さん</span>", "問い q2: 人ごとの事実の問いに問いの人"),
    ('<fieldset class="q" data-qkey="q2"', '<p class="glead">問いの間の説明</p><fieldset class="q" data-qkey="q2"', "まとまりの 1 行（.glead）が問いの箱の外に 1 つ"),
    ('<p class="why" data-why="missing">資料に書いてありません</p>', '<p class="why" data-why="missing">資料に書いてありません</p><p class="why" data-why="law">好きに書いた理由</p>', "問い q2: .why が 2 つ"),
    ('<div class="known" data-docs="d2 d3">', '<div class="known" data-docs="d2">短い</div><div class="known" data-docs="d2 d3">', "問い q2: .known が 2 つ"),
    ("<span>送料</span></p>", "<span>送料</span></p><p class=\"about\"><span>a</span><span>b</span><span>c</span><span>d</span></p>", "問い q1: .about が 2 つ"),
    ("</details>\n<div class=\"opts\">\n<label class=\"opt\"><input type=\"radio\" name=\"q3\"", "</details><details class=\"more\"><summary>x</summary>1<br>2<br>3<br>4</details>\n<div class=\"opts\">\n<label class=\"opt\"><input type=\"radio\" name=\"q3\"", "問い q3: .more が 2 つ"),
    ('name="q2" value="d1027"><span><b>10 月 27 日</b><small class="chg">棚の入れ替えが 10 月 28 日</small>', 'name="q2" value="other"><span><b>10 月 27 日</b>', "問い q2: 選択肢「10 月 27 日」にこの答えで変わる事"),
    ("今は期限が決まっていません。", "照合して決まっていません。", "内部の言葉「照合」"),
    ("今は期限が決まっていません。", "Q2026.11-37 の続きです。", "番号「Q2026.11-37」"),
    ('<details class="more">', '<details class="more" ontoggle="fetch(\'/x\')">', "型の外に許していない属性"),
    ("送料 1 箱 125.5 円（税別）", '<a href="javascript:alert(1)">見積りの写し</a>', "許していない URL"),
    ("送料 1 箱 125.5 円（税別）", '<img src="https://example.com/a.png" alt="見積り">', "外のリソース・許していない src"),
    ('<meta name="color-scheme" content="light">', '<meta content="light dark" name="color-scheme">', "暗い色の設定"),
    ('<section class="done" id="qa-done" hidden>', '<section class="done" id="qa-done">', "qa:foot の中身が型と違う"),
    ("<h2>答えを確かめてください</h2>", "<h2>これで送ります</h2>", "qa:foot の中身が型と違う"),
    ('id="sendbtn">', 'id="sendbtn" onclick="fetch(\'/x\')">', "qa:foot の中身が型と違う"),
    ("決まりの写しをお送りします。", "決まりの写しをお送りします。<a href=\"#\">x</a>", "「この後のこと」（.next）に書けるのは"),
    ("決まりの写しをお送りします。", '決まりの写しをお送りします。<img src="x" onerror="fetch(\'/x\')">', "「この後のこと」（.next）に書けるのは"),
    ("決まりの写しをお送りします。", "決まりの写しをお送りします。<b>x</b>", "「この後のこと」（.next）に書けるのは", '<p class="lead">', '<p class="lead"><span class="next">ok</span>'),
    ("</body>", "<!--qa:css--><p>x</p><!--/qa:css--></body>", "型の qa:css の印が 2 回ある"),
    ("</body>", "<!--qa:js--><p>x</p><!--/qa:js--></body>", "型の qa:js の印が 2 回ある"),
    ("</body>", "<!--qa:foot--><p>x</p><!--/qa:foot--></body>", "型の qa:foot の印が 2 回ある"),
    ("送料 1 箱 125.5 円（税別）", '<iframe srcdoc="&lt;script&gt;fetch(1)&lt;/script&gt;"></iframe>', "型の外に許していない要素 <iframe>"),
    ("送料 1 箱 125.5 円（税別）", '<iframe src="data:text/html,x"></iframe>', "型の外に許していない要素 <iframe>"),
    ("送料 1 箱 125.5 円（税別）", '<embed src="data:text/html,x">', "型の外に許していない要素 <embed>"),
    ('<meta name="color-scheme" content="light">', '<meta name="color-scheme" content="light"><meta http-equiv="refresh" content="0;url=https://example.com/">', "型の外に許していない属性「http-equiv」"),
    ("送料 1 箱 125.5 円（税別）", '<img src="data:image/png;base64,iVBORw0KGgo=" alt="見積り" srcset="https://example.com/a.png 2x">', "型の外に許していない属性「srcset」"),
    ("送料 1 箱 125.5 円（税別）", '<a href="https://example.com/mitsumori">見積りの写し</a>', None),
    ("送料 1 箱 125.5 円（税別）", '<img src="data:image/png;base64,AAAA" SRC="data:image/png;base64,BBBB" alt="x">', "同じ属性「src」が 2 回ある"),
    ("送料 1 箱 125.5 円（税別）", '<a href="#a" href="#b">見積り</a>', "同じ属性「href」が 2 回ある"),
    ("送料 1 箱 125.5 円（税別）", '<a href="http://example.com/">見積り</a>', "許していない URL"),
    ('<meta name="color-scheme" content="light">', '<meta name="color-scheme" content="light"><meta name="referrer" content="none">', "許していない meta"),
    ("<p class=\"lead\">", "<!-- a --!> x --><p class=\"lead\">", "崩れたコメント"),
    ("<p class=\"lead\">", "<!--> x --><p class=\"lead\">", "崩れたコメント"),
    ('<details class="more">', '<details class="more"/onclick="fetch(\'/x\')">', "型の外に許していない属性"),
    ('type="radio" name="q2" value="none"', 'type="checkbox" name="q2" value="none" required', "問い q2: checkbox に required"),
]


@needs_node
@pytest.mark.parametrize("old, new, expect, more", [(*m[:3], m[3:]) for m in MUTATIONS], ids=[m[2] or f"緑: {m[1][:20]}" for m in MUTATIONS])
def test_壊した所の赤だけが出る(tmp_path, old, new, expect, more):
    """more＝同時に入れる 2 つ目の書き換え（old2, new2）。囮を置いて照らしをすり抜けられないかを見る。"""
    base = filled_template()
    for o, n in [(old, new), *zip(more[::2], more[1::2])]:
        assert o in base, o
        base = base.replace(o, n, 1)
    page = tmp_path / "確認.html"
    page.write_text(base, encoding="utf-8")
    out = run_check(page)
    if expect is None:  # 許す物の表で通る書き換え（例: 根拠の資料へのリンク）
        assert out["red"] == [], out["red"]
        return
    assert len(out["red"]) == 1 and out["red"][0].startswith(expect), out["red"]


# 2 つ目の印の間に書いた物は、印の重なりと中身の両方で赤になる（中身を照らしから外さない）
SECOND_MARKS = [
    ("qa:css", "<style>body{background:#000}</style>", "型の外に許していない要素 <style>"),
    ("qa:js", "<script>fetch('/x')</script>", "型の外に許していない要素 <script>"),
    ("qa:foot", '<img src="x" onerror="fetch(\'/x\')">', "型の外に許していない属性"),
]


@needs_node
@pytest.mark.parametrize("name, inner, expect", SECOND_MARKS, ids=[m[0] for m in SECOND_MARKS])
def test_2_つ目の印の間の中身も照らす(tmp_path, name, inner, expect):
    page = tmp_path / "確認.html"
    page.write_text(filled_template().replace("</body>", f"<!--{name}-->{inner}<!--/{name}--></body>", 1), encoding="utf-8")
    red = run_check(page)["red"]
    assert red[0].startswith(f"型の {name} の印が 2 回ある") and any(r.startswith(expect) for r in red), red


@needs_node
def test_この後のことは差し替えても緑(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template().replace("11 月 22 日までに、決まりの写しをお送りします。", "来週中に<br>お電話します。", 1), encoding="utf-8")
    assert run_check(page)["red"] == []


# ブラウザはコメントを --!> や <!--> でも閉じる＝検査がコメントと読んでも、中の script は動く
BROKEN_COMMENTS = ["<!-- a --!><script>fetch('/x')</script><!-- b -->", "<!--><script>fetch('/x')</script><!-- b -->"]


@needs_node
@pytest.mark.parametrize("inject", BROKEN_COMMENTS, ids=["--!>", "<!-->"])
def test_崩れたコメントに隠した_script_も赤(tmp_path, inject):
    page = tmp_path / "確認.html"
    page.write_text(filled_template().replace("</form>", "</form>" + inject, 1), encoding="utf-8")
    red = run_check(page)["red"]
    for e in ["型の外に許していない要素 <script>", "<script> はページ全体でちょうど 1 つ", "崩れたコメント"]:
        assert any(r.startswith(e) for r in red), (e, red)


# 同じ属性が 2 回ある時、ブラウザは前の値を使う＝前の値も照らし、重なりも赤
DOUBLE_ATTRS = [
    ('<img src="https://example.com/a.png" SRC="data:image/png;base64,AAAA" alt="x">', "外のリソース・許していない src"),
    ('<a href="javascript:alert(1)" href="#">見積り</a>', "許していない URL"),
]


@needs_node
@pytest.mark.parametrize("inject, expect", DOUBLE_ATTRS, ids=["src", "href"])
def test_同じ属性の_2_つ目で隠せない(tmp_path, inject, expect):
    page = tmp_path / "確認.html"
    page.write_text(filled_template().replace("送料 1 箱 125.5 円（税別）", inject, 1), encoding="utf-8")
    red = run_check(page)["red"]
    assert any(r.startswith("同じ属性") for r in red) and any(r.startswith(expect) for r in red), red


@needs_node
def test_型の外の_script_は赤(tmp_path):
    base = filled_template()
    page = tmp_path / "確認.html"
    page.write_text(base.replace("</form>", "</form><script>fetch('/x')</script>", 1), encoding="utf-8")
    red = run_check(page)["red"]
    assert len(red) == 2 and red[0].startswith("<script> はページ全体でちょうど 1 つ") and red[1].startswith("型の外に許していない要素 <script>"), red


@needs_node
def test_ひとことに書かせる選択肢に印が無いと赤(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template("send").replace('value="other" data-supp="need">', 'value="other">', 1), encoding="utf-8")
    red = run_check(page)["red"]
    assert len(red) == 1 and red[0].startswith("問い q1: ひとことに書かせる選択肢「ほかの答え」に data-supp=\"need\" が無い"), red


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


@pytest.mark.skipif(_playwright() is None, reason="playwright が無い（型の JS を実ブラウザで動かす）")
def test_ひとことに書かせる選択肢を選ぶと欄の名が変わり空では進めない(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template("copy"), encoding="utf-8")
    with _playwright()() as p:
        exe = os.environ.get("QA_CHROMIUM")   # 入った playwright と別の版のブラウザを使う時だけ
        b = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = b.new_page()
        pg.goto(page.as_uri())
        js = """([sel, ev, val]) => { const f = document.querySelector('fieldset.q[data-qkey="q1"]'); const el = f.querySelector(sel);
            if (val === null) el.checked = true; else el.value = val; el.dispatchEvent(new Event(ev, { bubbles: true })); }"""
        lab = lambda: pg.evaluate("""() => document.querySelector('fieldset.q[data-qkey="q1"] .supp label').textContent""")
        nxt = lambda: pg.evaluate("""() => { const f = document.querySelector('fieldset.q[data-qkey="q1"]');
            [...f.querySelectorAll('button')].pop().click(); return [f.classList.contains('miss'), f.querySelector('.err').textContent]; }""")
        assert lab() == "ひとこと（なくても大丈夫です）"
        pg.evaluate(js, ['input[value="other"]', "change", None])
        assert lab() == "ひとこと（この答えでは書いてください）"
        miss, err = nxt()
        assert miss and "下のひとことに書いてください" in err
        pg.evaluate(js, ['textarea[name="supp_q1"]', "input", "月の合計で丸める"])
        assert nxt()[0] is False
        pg.evaluate(js, ['input[value="__unknown__"]', "change", None])
        assert lab() == "誰に聞けば分かりますか（なくても大丈夫です）"
        b.close()
