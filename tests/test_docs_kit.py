"""docs-kit プラグインが「プラグインとして入る形」か、と qa-html の検査（check.mjs）の自分の試験。"""
import ast
import json
import os
import re
import shlex
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
    assert "細目 §3「まず構造を疑う」" in ng.stderr.strip().splitlines()[-1], "欠けを埋めて出し直させるだけの古い形に戻った"


# ── qa-html の検査 ──────────────────────────────────────────────────

# 型の差し込み（{{…}}）の頭 → 出てくる順に使う値（作り物）
FILL = {
    "件名": ["備品の貸し出しの決め方", "備品の貸し出しの決め方"],
    "send か copy か artifact": ["copy"],
    "宛名": ["サンプル株式会社 ご担当者様"],
    "前書き": ["答えていただいた内容で、貸し出しの決まりを確定します。"],
    "リンク": ["https://example.com/docs/mitsumori", "https://example.com/docs/mitsumori", "https://example.com/docs/chumon", "https://example.com/docs/chumon"],
    "リンクが無い訳": ["紙で受け取った"],
    "読んだ資料": ["見積り書（10 月分）・10 月 1 日に受け取り", "注文書の控え・10 月 1 日に受け取り", "貸し出しの決まり・9 月 10 日に受け取り"],
    "答えるまでの扱い": ["答えが届くまで、この点は確定せずにお待ちします。"],
    "期限": ["11 月 20 日"],
    "版": ["2026-11-13.1"],
    "一言の見出し": ["送料の端数", "届く日", "返す期限", "壊れた時"],
    "まとまりの 1 行": ["決まりと合わない所です", "届いた物の確かめです", "今回の催しの分だけの事です"],
    "何について: 誰": ["全員", "見本さん", "全員", "全員"],
    "何について: いつ": ["10 月分", "10 月分", "10 月分"],
    "何について: 何": ["送料", "棚が届く日", "壊れた時"],
    "問い 1 行": ["送料の端数は、どちらで計算しますか", "新しい棚が届く日は、どちらですか", "返す期限は、どう決めますか",
               "借りた物が壊れた時は、どう決めますか"],
    "AI の読み": ["1 箱 125.5 円の送料と読みました → 円未満の端数の扱いがどこにも書かれていません。",
                "注文は 10 月 1 日と読みました → 届く日はどの資料にも無く、決まりません。",
                "催しの間だけ貸すと読みました → 何日目までに返すかが決まりません。",
                "壊れた時の扱いは決まりに無いと読みました → 起きた時に誰が直すかが決まりません。"],
    "見つけた事": ["見積り書の 2 枚目は、送料 1 箱 125.5 円です。", "見積り書と注文書の控えに、届く日の書きがありません。", "今は期限が決まっていません。",
              "貸し出しの決まりに、壊れた時の書きがありません。"],
    "根拠の場所": ["2 枚目・送料の行", "2 枚目・送料の行", "1 枚目・届け日の欄", "1 枚目・届け日の欄", "1 枚目・貸し出しの期間の行",
              "1 枚目・貸し出しの期間の行", "第 3 条（返す時）", "第 3 条（返す時）"],
    "根拠の資料名": ["見積り書", "注文書の控え", "見積り書", "貸し出しの決まり"],
    "原文の引用": ["届け日: （空欄）", "貸し出しの期間: 催しの間", "借りた物は、使い終わったら元の棚へ返す。"],
    "表の見出し": ["10 月の請求"],
    "今の計算": ["切り捨てる"],
    "直した場合": ["切り上げる"],
    "行の名": ["合計"],
    "数": ["1,200 円", "1,300 円"],
    "切り抜きの画像": ["data:image/png;base64,iVBORw0KGgo="],
    "切り抜きに写っている事": ["見積り書の送料の行"],
    "切り抜きの資料名と場所": ["見積り書 2 枚目"],
    "判断に要る細かい事": ["見積りの写しを付けています。", "注文は 10 月 1 日に出ています。", "大きい物は 7 日では足りない事があります。",
                     "10 月までに壊れた事はありません。"],
    "原文": ["送料 1 箱 125.5 円（税別）"],
    "選択肢の鍵": ["down", "up", "d1020", "d1027", "d7", "d14", "lender", "borrower"],
    "中身の見出し": ["切り捨てる", "切り上げる", "10 月 20 日", "10 月 27 日", "借りた日から 7 日", "借りた日から 14 日", "貸した側が直す", "借りた側が直す"],
    "この答えで変わる事": ["10 月の請求が合計 1,200 円", "10 月の請求が合計 1,300 円", "棚の入れ替えが 10 月 21 日", "棚の入れ替えが 10 月 28 日",
                       "返す日の知らせが借りた日から 7 日目", "返す日の知らせが借りた日から 14 日目",
                       "直す費用を貸した側の請求に入れます", "直す費用を借りた側への請求に入れます"],
    "見込みの根拠": ["9 月までの見積り書の送料は、どれも切り捨てで書かれている"],
    "AI の今の見込み": ["切り捨てる"],
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
    assert out["dest"] == dest and out["questions"] == ["q1", "q2", "q3", "q4"]


@needs_node
def test_問いのデータの良い例は緑():
    out = run_check(DATA / "good.json")
    assert out["red"] == [], out["red"]
    assert out["dest"] == "artifact" and out["questions"] == ["q1", "q2", "q3"]


@needs_node
def test_問いのデータの悪い例は決まった赤だけ():
    out = run_check(DATA / "bad.json")
    assert not out["ok"]
    expect = ["答えるまでの扱いが無い", "問い q1: なぜ聞くか", "問い q1: 1 問に 2 つ以上", "問い q1: 選択肢が 1 つだけ", "問い q2: 並びが逆",
              "問い q2: 切り抜き 1 の画像が無い", "問い q2: 選択肢「まだ分からない」にこの答えで変わる事", "問い q2: 資料の外の事実の問いに「当てはまらない」",
              "問い q2: ひとことの欄",
              # 根拠・読み・見込み・リンク・ほかの問いに頼る言い方
              "「前の問」は書かない", "読んだ資料 d1 にリンク", "問い q1: 根拠（どの資料のどこを見たか", "問い q1: 実物が無い", "問い q1: AI の読み",
              "問い q1: AI の今の見込みの根拠", "問い q1: 選択肢「決まったら連絡」の推奨の印", "問い q2: 根拠（どの資料のどこを見たか", "問い q2: AI の読み"]
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
    for k in ["about", "known", "docs", "why", "more", "reading", "evidence"]:
        q.pop(k)
    q["options"][0].pop("change")
    data["questions"][1]["clips"][1]["shows"] = ["見本さん", "ほかの人"]
    page = tmp_path / "q.json"
    page.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    red = run_check(page)["red"]
    expect = ["問い q1: 何について", "問い q1: なぜ聞くか", "問い q1: 見つけた事（資料名・場所・値）が無い", "問い q1: 見つけた事が読んだ資料を指していない",
              "問い q1: くわしく", "問い q1: 根拠（どの資料のどこを見たか", "問い q1: 実物が無い", "問い q1: AI の読み", "問い q1: 選択肢「借りた日から 7 日」にこの答えで変わる事", "問い q2: 切り抜き 2 に問いの人の外の名「ほかの人」"]
    assert len(red) == len(expect), red
    for e in expect:
        assert any(r.startswith(e) for r in red), (e, red)


@needs_node
def test_問いのデータに外した欄があれば赤(tmp_path):
    """差出人・連絡先の欄は外した（宛先で変えるのは宛名と会社の色だけ）＝鍵が残っていれば赤。"""
    for k, name in [("from", "差出人"), ("contact", "連絡先")]:
        data = json.loads((DATA / "good.json").read_text(encoding="utf-8"))
        data[k] = "サンプル事務所"
        page = tmp_path / f"q_{k}.json"
        page.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        red = run_check(page)["red"]
        assert len(red) == 1 and red[0].startswith(f'{name}（"{k}"）は外した'), red


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


# ── 前の答えを照らす口（値の表の docs-kit.qa-html.prior_check_cmd・check.mjs の --prior / --run-prior）


def write_values(tmp_path, qa_values):
    values = tmp_path / "config" / "skill-values.json"
    values.parent.mkdir(exist_ok=True)
    values.write_text(json.dumps({"docs-kit": {"qa-html": qa_values}}, ensure_ascii=False), encoding="utf-8")
    return values


def run_check_args(path, *args):
    res = subprocess.run([NODE, str(CHECK), str(path), "--json", *args], capture_output=True, text=True, cwd=path.parent)
    assert res.returncode in (0, 1), res.stderr
    return json.loads(res.stdout)


def prior_cmd(tmp_path, answered=None, skip=()):
    """作り物の「前の答えを照らす道具」: 標準入力の問いを読み、answered に無い問いは引いた結果を返す。"""
    script = tmp_path / "prior_tool.py"
    script.write_text(
        "import json, sys\n"
        "data = json.load(sys.stdin)\n"
        f"answered = {json.dumps(answered or {})}\n"
        f"skip = {json.dumps(list(skip))}\n"
        "assert data['format'] == 'qa-prior/1'\n"
        "checked = {q['key']: '引いた言葉: ' + q['label'] for q in data['questions'] if q['key'] not in answered and q['key'] not in skip}\n"
        "print(json.dumps({'answered': answered, 'checked': checked}, ensure_ascii=False))\n",
        encoding="utf-8",
    )
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"


@needs_node
def test_値の表に_prior_check_cmd_が無ければ前と同じ(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template(), encoding="utf-8")
    before = run_check(page)
    write_values(tmp_path, {"limits": {}})
    after = run_check(page)
    assert before["red"] == after["red"] == [] and before["questions"] == after["questions"]


@needs_node
def test_引いた結果に答え済みの鍵があれば赤(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template(), encoding="utf-8")
    prior = tmp_path / "引いた結果.json"
    prior.write_text(json.dumps({"answered": {"q2": "https://example.com/answers/12"}, "checked": {}}), encoding="utf-8")
    red = run_check_args(page, "--prior", str(prior))["red"]
    assert red == ["問い q2: 前の答えで答え済み（https://example.com/answers/12）＝問いから外す（作り方 0）"], red
    # ページの隣の <名>.prior.json は --prior を渡さなくても読む（guard の qa_page はページの path だけで呼ぶ）
    (tmp_path / "確認.prior.json").write_text(prior.read_text(encoding="utf-8"), encoding="utf-8")
    assert run_check(page)["red"] == red


@needs_node
def test_値の表に命令があれば引いた結果の無い問いは赤(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template(), encoding="utf-8")
    write_values(tmp_path, {"prior_check_cmd": prior_cmd(tmp_path)})
    assert run_check(page)["red"] == ["前の答えを照らした結果が無い（値の表に prior_check_cmd がある）: node check.mjs <file> --run-prior で引いてから検査する"]
    prior = tmp_path / "確認.prior.json"
    prior.write_text(json.dumps({"checked": {"q1": "x", "q2": "y", "q4": "z"}}), encoding="utf-8")
    assert run_check(page)["red"] == ["問い q3: 前の答えを照らした結果が無い（--run-prior で引き直す）"]
    prior.write_text(json.dumps({"checked": ["q1"]}), encoding="utf-8")
    red = run_check(page)["red"]
    assert len(red) == 1 and red[0].startswith("前の答えを照らした結果が読めない") and '"checked" は' in red[0], red


@needs_node
def test_run_prior_で値の表の命令を走らせて照らす(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template(), encoding="utf-8")
    write_values(tmp_path, {"prior_check_cmd": prior_cmd(tmp_path)})
    assert run_check_args(page, "--run-prior")["red"] == []
    saved = json.loads((tmp_path / "確認.prior.json").read_text(encoding="utf-8"))
    assert saved["checked"]["q1"] == "引いた言葉: 送料の端数"
    assert run_check(page)["red"] == []  # 書いた結果を次の検査（guard も）が読む
    write_values(tmp_path, {"prior_check_cmd": prior_cmd(tmp_path, answered={"q4": "決定の記録 7"})})
    assert run_check_args(page, "--run-prior")["red"] == ["問い q4: 前の答えで答え済み（決定の記録 7）＝問いから外す（作り方 0）"]
    write_values(tmp_path, {"prior_check_cmd": f"{shlex.quote(sys.executable)} -c 'print(1/0)'"})
    red = run_check_args(page, "--run-prior")["red"]
    assert len(red) == 1 and red[0].startswith("前の答えを照らした結果が読めない（prior_check_cmd"), red


@needs_node
def test_問いのデータにも同じ口(tmp_path):
    data = json.loads((DATA / "good.json").read_text(encoding="utf-8"))
    page = tmp_path / "q.json"
    page.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    res = subprocess.run([NODE, str(CHECK), str(page), "--prior-input"], capture_output=True, text=True, check=True)
    sent = json.loads(res.stdout)
    assert sent["format"] == "qa-prior/1" and [q["key"] for q in sent["questions"]] == [q["key"] for q in data["questions"] if q["key"] != "__自由記入__"]
    key = sent["questions"][0]["key"]
    write_values(tmp_path, {"prior_check_cmd": prior_cmd(tmp_path, answered={key: "前の答え 3"})})
    assert run_check_args(page, "--run-prior")["red"] == [f"問い {key}: 前の答えで答え済み（前の答え 3）＝問いから外す（作り方 0）"]
    assert (tmp_path / "q.prior.json").exists()


@needs_node
def test_prior_に渡した_file_が無ければ赤(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template(), encoding="utf-8")
    red = run_check_args(page, "--prior", str(tmp_path / "無い.json"))["red"]
    assert len(red) == 1 and red[0].startswith("前の答えを照らした結果が読めない") and "file が無い" in red[0], red
    res = subprocess.run([NODE, str(CHECK), str(page), "--prior"], capture_output=True, text=True)
    assert res.returncode == 2 and "--prior の後に file を書く" in res.stderr


@needs_node
def test_命令が落ちたら前の回の結果を残さない(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template(), encoding="utf-8")
    write_values(tmp_path, {"prior_check_cmd": prior_cmd(tmp_path)})
    assert run_check_args(page, "--run-prior")["red"] == []
    for broken in ["false", f"{shlex.quote(sys.executable)} -c 'print(\"x\")'"]:  # 落ちる／JSON を返さない
        write_values(tmp_path, {"prior_check_cmd": broken})
        assert run_check_args(page, "--run-prior")["red"][0].startswith("前の答えを照らした結果が読めない")
        write_values(tmp_path, {})  # 値の表から命令を外しても、ページの path だけの検査（guard）は古い結果で緑にならない
        red = run_check(page)["red"]
        assert len(red) == 1 and "命令が落ちた回の結果" in red[0], red


@needs_node
def test_別の版のページで引いた結果は赤(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template(), encoding="utf-8")
    write_values(tmp_path, {"prior_check_cmd": prior_cmd(tmp_path)})
    assert run_check_args(page, "--run-prior")["red"] == []
    page.write_text(filled_template().replace('value="2026-11-13.1"', 'value="2026-11-13.2"', 1), encoding="utf-8")
    red = run_check(page)["red"]
    assert red == ["前の答えを照らした結果が別の版（2026-11-13.1）のページで引いた物: 今の版（2026-11-13.2）で --run-prior を引き直す"], red


@needs_node
def test_guard_と同じ呼び方でも値の表を見つける(tmp_path):
    """guard の qa_page は cwd をページの dir にして呼ぶ。ページが repo の外（窓の scratchpad）でも、窓の repo の値の表の命令が効く。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    write_values(repo, {"prior_check_cmd": prior_cmd(tmp_path)})
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    page = scratch / "確認.html"
    page.write_text(filled_template(), encoding="utf-8")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    res = subprocess.run([NODE, str(CHECK), str(page), "--json"], capture_output=True, text=True, cwd=scratch, env=env)
    assert json.loads(res.stdout)["red"][0].startswith("前の答えを照らした結果が無い（値の表に prior_check_cmd がある）")
    res = subprocess.run([NODE, str(CHECK), str(page), "--json", "--run-prior"], capture_output=True, text=True, cwd=scratch, env=env)
    assert res.returncode == 0, res.stdout
    res = subprocess.run([NODE, str(CHECK), str(page), "--json"], capture_output=True, text=True, cwd=scratch, env=env)
    assert res.returncode == 0 and json.loads(res.stdout)["red"] == []


# 1 か所だけ壊すと、その 1 つの赤だけが出る（壊した所以外の結果が変わらない見張り）
MUTATIONS = [
    ('<body data-dest="copy"', '<body data-dest="mail"', "宛先の印が無い"),
    ('id="copybtn"', 'id="copy-button"', "qa:foot の中身が型と違う"),
    ('<p class="to">サンプル株式会社 ご担当者様</p>', '<p class="to"></p>', "宛名（header の .to）が無い"),
    # 外した欄（差出人・連絡先）が残っていれば赤
    ('<p class="hold">', '<p class="from">サンプル事務所 担当 見本</p><p class="hold">', "差出人の欄（.from）は外した"),
    ('<p class="hold">', '<p class="contact">このメールに返信してください</p><p class="hold">', "連絡先の欄（.contact）は外した"),
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
    ('name="q2" value="__unknown__"', 'name="q2" value="later"', "問い q2: 「分からない・確かめてから答える」"),
    ('value="d1020" required', 'value="d1020"', "問い q2: 答えずに送れる"),
    ("<b>切り捨てる", "<b>A 切り捨てる", "問い q1: 選択肢に記号"),
    ('value="d7"', 'value="7days!"', "問い q3: 選択肢の鍵（value）"),
    ('name="supp_q1"', 'name="note_q1"', "問い q1: ひとことの欄"),
    # 前提の 3 段（はじめの画面・まとまり・1 問の 4 欄・切り抜き・変わる事）
    ('<p class="hold">', '<p class="note">', "答えるまでの扱いが無い"),
    ('<li data-doc="d3" ', '<li data-doc="d-4" data-url="" data-no-url="紙で受け取った">増えた資料</li><li data-doc="d3" ', "読んだ資料の鍵（data-doc）"),
    # 根拠（資料のどこ）・実物・AI の読み・AI の今の見込み・資料のリンク・先に決めておきたい事
    ('data-url="" data-no-url="紙で受け取った"', 'data-url=""', "読んだ資料 d3 にリンク"),
    ('data-url="https://example.com/docs/chumon"', 'data-url="https://example.com/docs/other"', "読んだ資料 d2 のリンクが見えない"),
    ('data-url="https://example.com/docs/chumon"><a href="https://example.com/docs/chumon">', 'data-url="http://example.com/x"><a href="https://example.com/docs/chumon">', "読んだ資料 d2 のリンクは https://"),
    ('<ul class="evidence"><li data-doc="d1" data-where="2 枚目・送料の行"><b>見積り書</b>・2 枚目・送料の行</li></ul>', "", "問い q1: 根拠（どの資料のどこを見たか"),
    ('data-where="1 枚目・届け日の欄"', 'data-where=""', "問い q2: 根拠 1 の場所"),
    ('<li data-doc="d2" data-where', '<li data-doc="d9" data-where', "問い q2: 根拠 1 の資料「d9」"),
    ('<span class="quote">届け日: （空欄）</span>', "", "問い q2: 実物が無い"),
    ('<p class="reading">注文は 10 月 1 日と読みました → 届く日はどの資料にも無く、決まりません。</p>', "", "問い q2: AI の読み"),
    ("注文は 10 月 1 日と読みました → ", "注文は 10 月 1 日と読みました<br>1<br>2<br>", "問い q2: AI の読みが 4 行"),
    ("決まりません。</p>\n<div class=\"known\" data-docs=\"d2 d3\">", "決まりません。</p><p class=\"reading\">2 つ目</p>\n<div class=\"known\" data-docs=\"d2 d3\">", "問い q2: .reading が 2 つ"),
    ('data-basis="9 月までの見積り書の送料は、どれも切り捨てで書かれている"', 'data-basis=""', "問い q1: AI の今の見込みの根拠"),
    ('<p class="estimate"', '<p class="estimate-x"', None),
    ("答えが届くまで、この点は確定せずにお待ちします。", "今の見込みで計算し、答えが届いたら直します。", "「見込み」は AI の今の見込みの枠"),
    ("今は期限が決まっていません。", "前の問いの答えで決まります。", "「前の問」は書かない"),
    ("今は期限が決まっていません。", "この先の答えは、返す日の知らせに使います。", None),
    # 並び: AI の読みはなぜ聞くかの下・見込みは選択肢の後
    ('<p class="why" data-why="missing">資料に書いてありません</p>\n<p class="reading">注文は 10 月 1 日と読みました → 届く日はどの資料にも無く、決まりません。</p>',
     '<p class="reading">注文は 10 月 1 日と読みました → 届く日はどの資料にも無く、決まりません。</p>\n<p class="why" data-why="missing">資料に書いてありません</p>',
     "問い q2: AI の読み（.reading）はなぜ聞くか（.why）の下に置く"),
    ('\n<p class="estimate" data-basis="9 月までの見積り書の送料は、どれも切り捨てで書かれている">切り捨てる</p>', "",
     "問い q1: AI の今の見込み（.estimate）は選択肢（.opts）の後に置く",
     '<div class="opts">\n<label class="opt"><input type="radio" name="q1"',
     '<p class="estimate" data-basis="9 月までの見積り書の送料は、どれも切り捨てで書かれている">切り捨てる</p><div class="opts">\n<label class="opt"><input type="radio" name="q1"'),
    # 上限
    ('data-where="2 枚目・送料の行"', 'data-where="' + "2 枚目・送料の行" * 8 + '"', "問い q1: 根拠 1 の場所が"),
    ("<span class=\"quote\">届け日: （空欄）</span>", "<span class=\"quote\">" + "届け日: （空欄）" * 12 + "</span>", "問い q2: 根拠 1 の原文の引用が"),
    (">切り捨てる</p>", ">" + "切り捨てる" * 9 + "</p>", "問い q1: AI の今の見込みが"),
    ('data-basis="9 月までの見積り書の送料は、どれも切り捨てで書かれている"', 'data-basis="' + "9 月までの見積り書の送料は、どれも切り捨て" * 3 + '"', "問い q1: AI の今の見込みの根拠が"),
    ("<b>借りた日から 7 日</b>", "<b>借りた日から 7 日（推奨）</b>", "「推奨」は書かない"),
    ("今月の計算には関係しません。起きた時の決め方を先に伺います。", "壊れた時の事です", "問い q4: 先に決めておきたい事のまとまりの 1 行"),
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
        try:
            b = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        except Exception as e:   # 入った playwright の版のブラウザが無い窓（QA_CHROMIUM で別の版を指せる）
            pytest.skip(f"ブラウザを起こせない: {str(e).splitlines()[0]}")
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


@needs_node
def test_添え書きの無いほかの答えにも印が要る(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template("send").replace(
        'value="other" data-supp="need"><span><b>ほかの答え</b><small>下のひとことに書いてください</small>',
        'value="other"><span><b>ほかの答え</b>', 1), encoding="utf-8")
    red = run_check(page)["red"]
    assert len(red) == 1 and "ほかの答え" in red[0] and 'data-supp="need" が無い' in red[0], red


@needs_node
def test_印の値は_need_だけ(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template("send").replace('value="other" data-supp="need"', 'value="other" data-supp="yes"', 1), encoding="utf-8")
    red = run_check(page)["red"]
    assert len(red) == 1 and 'data-supp は "need" だけ（今 yes）' in red[0], red
    data = json.loads((DATA / "good.json").read_text(encoding="utf-8"))
    for q in data["questions"]:
        for o in q.get("options", []):
            if o.get("supp") == "need":
                o["supp"] = True
    p = tmp_path / "q.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    red = run_check(p)["red"]
    assert red and all('"supp" は "need" だけ（今 true）' in x for x in red), red


# 問いのデータ（JSON）を 1 か所だけ壊すと、その 1 つの赤だけが出る（根拠・読み・見込み・リンク・先に決めておきたい事）
def _drop_quotes(d):
    for e in d["questions"][2]["evidence"]:
        e.pop("quote", None)


JSON_MUTATIONS = [
    ("evidence が無い", lambda d: d["questions"][1].pop("evidence"), "問い q2: 根拠（どの資料のどこを見たか"),
    ("where が空", lambda d: d["questions"][1]["evidence"][0].update(where=" "), "問い q2: 根拠 1 の場所"),
    ("実物が無い", _drop_quotes, "問い q3: 実物が無い"),
    ("reading が無い", lambda d: d["questions"][2].pop("reading"), "問い q3: AI の読み"),
    ("estimate の basis が空", lambda d: d["questions"][0]["estimate"].update(basis=""), "問い q1: AI の今の見込みの根拠"),
    ("estimate の中身が空", lambda d: d["questions"][0]["estimate"].update(value=""), "問い q1: AI の今の見込みの中身が空"),
    ("estimate が無くても緑", lambda d: d["questions"][0].pop("estimate"), None),
    ("前の問いに頼る", lambda d: d["questions"][2].update(more="上の問いと同じ決め方です。"), "「上の問」は書かない"),
    ("前の質問に頼る", lambda d: d["questions"][1].update(question="前の質問と同じ日ですか"), "「前の質問」は書かない"),
    ("見込みを前提に見せる", lambda d: d.update(lead="今の見込みで計算しています。"), "「見込み」は AI の今の見込みの枠"),
    ("url も no_url も無い", lambda d: d["docs"][2].pop("url"), "読んだ資料 d3 にリンク"),
    ("no_url の訳が空", lambda d: d["docs"][1].update(no_url=""), "読んだ資料 d2 にリンク"),
    ("url が https でない", lambda d: d["docs"][0].update(url="file:///x.pdf"), "読んだ資料 d1 のリンクは https://"),
    ("先に決めておきたい事が最後でない", lambda d: d["questions"].insert(1, d["questions"].pop(2)), "問い q2: 並びが逆"),
    ("根拠が 4 つ", lambda d: d["questions"][0]["evidence"].extend([{"doc": "d1", "where": f"{i} 枚目"} for i in (2, 3)]), "問い q1: 根拠が 4 つ"),
    ("先に決めておきたい事の 1 行を替えた", lambda d: d["questions"][2].update(glead="壊れた時の事です"), "問い q3: 先に決めておきたい事のまとまりの 1 行"),
]


@needs_node
@pytest.mark.parametrize("name, mutate, expect", JSON_MUTATIONS, ids=[m[0] for m in JSON_MUTATIONS])
def test_問いのデータの根拠と見込みの赤(tmp_path, name, mutate, expect):
    data = json.loads((DATA / "good.json").read_text(encoding="utf-8"))
    mutate(data)
    q = tmp_path / "q.json"
    q.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    red = run_check(q)["red"]
    if expect is None:
        assert red == [], red
        return
    assert len(red) == 1 and red[0].startswith(expect), (name, red)


@needs_node
def test_緑の_1_問は根拠と読みと見込みが全部そろう():
    """緑の例: 根拠（資料と場所と引用）・実物・AI の読み・根拠つきの見込み・選択肢に印なし・資料のリンクがそろった 1 問。"""
    data = json.loads((DATA / "good.json").read_text(encoding="utf-8"))
    q1 = data["questions"][0]
    assert q1["evidence"] and all(e["where"] for e in q1["evidence"]) and any(e.get("quote") for e in q1["evidence"])
    assert q1["reading"] and q1["estimate"]["basis"] and not any("recommended" in o for o in q1["options"])
    assert all(d.get("url") or d.get("no_url") for d in data["docs"])
    assert run_check(DATA / "good.json")["red"] == []


# ── 決まりの無理を外した所（1 つの形に押し込めない）。古い形を戻すと赤になる注入の試験


def _json_page(tmp_path, mutate, name="q.json"):
    data = json.loads((DATA / "good.json").read_text(encoding="utf-8"))
    mutate(data["questions"][-1])
    page = tmp_path / name
    page.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return run_check(page)["red"]


def test_分からないの文は誰にでも合う_1_文で_社内の言い方は残らない():
    from_check = re.search(r'"unknown":\s*\{[^}]*"label":\s*"([^"]+)"', CHECK.read_text(encoding="utf-8")).group(1)
    assert from_check == "分からない・確かめてから答える"
    for p in [QA / "SKILL.md", QA / "references" / "template.html", CHECK]:
        assert "社内で確かめて" not in p.read_text(encoding="utf-8"), p


@needs_node
def test_分からないの文に社内の言い方を戻すと赤(tmp_path):
    page = tmp_path / "確認.html"
    page.write_text(filled_template().replace("<b>分からない・確かめてから答える</b>", "<b>分からない・社内で確かめてから答える</b>", 1), encoding="utf-8")
    red = run_check(page)["red"]
    assert len(red) == 1 and red[0].startswith("問い q1: 「分からない」の文は「分からない・確かめてから答える」のまま"), red


@needs_node
def test_2_通りに読める資料は_5_つ目のなぜ聞くかで聞ける(tmp_path):
    assert _json_page(tmp_path, lambda q: q.update(why="ambiguous")) == []
    page = tmp_path / "確認.html"
    page.write_text(filled_template().replace('data-why="once">今回だけの事を確かめます<', 'data-why="ambiguous">資料の書き方が 2 通りに読めます<', 1), encoding="utf-8")
    assert run_check(page)["red"] == []
    # 知らない理由は今までどおり止まる・決まった文の外の文も止まる
    red = _json_page(tmp_path, lambda q: q.update(why="two_readings"), "q2.json")
    assert len(red) == 1 and red[0].startswith("問い q3: なぜ聞くか"), red
    page.write_text(filled_template().replace('data-why="once">今回だけの事を確かめます<', 'data-why="ambiguous">規程が 2 通りに読めます<', 1), encoding="utf-8")
    red = run_check(page)["red"]
    assert len(red) == 1 and red[0].startswith("問い q3: なぜ聞くかの文は決まった文「資料の書き方が 2 通りに読めます」"), red


COMPLETE_OPTS = [{"value": "all", "label": "これで全部", "change": "この資料だけで計算します"},
                 {"value": "more", "label": "ほかにもある", "change": "届いた資料で計算し直します", "detail": "下のひとことに資料の名を書いてください", "supp": "need"}]


@needs_node
def test_資料がそろっているかは当てはまらない無しで聞ける(tmp_path):
    def ok(q):
        q.update(kind="complete", why="once", question="読んだ資料はこれで全部ですか", options=COMPLETE_OPTS)
        q.pop("estimate", None)
    assert _json_page(tmp_path, ok) == []
    # 足りない資料を書かせる選択肢が無ければ赤（「ほかにもある」と答えても、何が足りないかが分からない）
    def no_supp(q):
        ok(q)
        q["options"] = [COMPLETE_OPTS[0], {k: v for k, v in COMPLETE_OPTS[1].items() if k not in ("supp", "detail")}]
    red = _json_page(tmp_path, no_supp, "q2.json")
    assert len(red) == 1 and red[0].startswith("問い q3: 資料がそろっているかの問いに、足りない資料の名をひとことに書かせる選択肢"), red
    # 古い形（資料の外の事実として聞く）に戻すと「当てはまらない」を求められる
    def as_fact(q):
        ok(q)
        q["kind"] = "fact"
    red = _json_page(tmp_path, as_fact, "q3.json")
    assert len(red) == 1 and red[0].startswith("問い q3: 資料の外の事実の問いに「当てはまらない」"), red


NONE_OPT = {"value": "none", "label": "当てはまらない", "detail": "10 月は残業がありません"}


def _overtime(kind, input_):
    def m(q):
        q.update(kind=kind, why="missing", question="10 月の実際の残業時間を教えてください", options=[NONE_OPT],
                 known=["作業の記録と月の報告を探しました。残業の時間はどちらにもありません。"])
        q.pop("estimate", None)
        if input_:
            q["input"] = input_
    return m


@needs_node
def test_資料の外にしか無い数は事実の問いの数の欄でだけ聞ける(tmp_path):
    assert _json_page(tmp_path, _overtime("fact", "number")) == []
    # 数の欄でない・資料の外の事実でない（計算できる数を書かせる古い形）は今までどおり赤
    for i, (kind, input_) in enumerate([("fact", "text"), ("fact", None), ("judge", "number")]):
        red = _json_page(tmp_path, _overtime(kind, input_), f"q{i}.json")
        assert any(r.startswith("問い q3: 数を書かせる問い「時間を教えて」") for r in red), (kind, input_, red)


@needs_node
def test_選択肢_1_つは資料の外の数の欄の時だけ(tmp_path):
    """数の欄を足した問いの選択肢 1 つを、ほかの形・ほかの欄へ広げない（レビューで見つけた穴の注入）。"""
    def one(kind, input_):
        def m(q):
            q.update(kind=kind, why="missing", options=[NONE_OPT] if kind == "fact" else [q["options"][0]])
            q.pop("estimate", None)
            if input_:
                q["input"] = input_
        return m
    assert _json_page(tmp_path, _overtime("fact", "number")) == []
    for i, (kind, input_) in enumerate([("choose", "text"), ("judge", "text"), ("judge", "number"), ("fact", "text"), ("fact", "date")]):
        red = _json_page(tmp_path, one(kind, input_), f"o{i}.json")
        assert any(r.startswith("問い q3: 選択肢が 1 つだけ") for r in red), (kind, input_, red)


@needs_node
def test_file_を2つ渡すと2つ目の赤も出る(tmp_path):
    good = tmp_path / "確認.html"
    good.write_text(filled_template("copy"), encoding="utf-8")
    bad = DATA / "bad.json"
    one = subprocess.run([NODE, str(CHECK), str(good)], capture_output=True, text=True, cwd=tmp_path)
    assert one.returncode == 0, one.stdout
    res = subprocess.run([NODE, str(CHECK), str(good), str(bad), "--json"], capture_output=True, text=True, cwd=tmp_path)
    assert res.returncode == 1, res.stderr
    out = json.loads(res.stdout)
    assert [r["ok"] for r in out] == [True, False] and out[1]["file"] == str(bad.resolve())


@needs_node
def test_1枚ずつの印は_file_が2つなら止まる(tmp_path):
    good = tmp_path / "確認.html"
    good.write_text(filled_template("copy"), encoding="utf-8")
    res = subprocess.run([NODE, str(CHECK), str(good), str(DATA / "good.json"), "--run-prior"],
                         capture_output=True, text=True, cwd=tmp_path)
    assert res.returncode == 2 and "1 枚ずつ" in res.stderr


@needs_node
@pytest.mark.parametrize("flags,word", [(["--jsno"], "知らない印"), (["--values", "a.json", "--values", "b.json"], "2 度")])
def test_知らない印と同じ印の2度書きは止まる(flags, word):
    res = subprocess.run([NODE, str(CHECK), str(DATA / "good.json"), *flags], capture_output=True, text=True)
    assert res.returncode == 2 and word in res.stderr and res.stdout == ""


@needs_node
def test_file_を2つ渡して1つでも赤なら根治の入口を指す(tmp_path):
    good = tmp_path / "確認.html"
    good.write_text(filled_template("copy"), encoding="utf-8")
    res = subprocess.run([NODE, str(CHECK), str(good), str(DATA / "bad.json")], capture_output=True, text=True, cwd=tmp_path)
    assert res.returncode == 1 and "まず構造を疑う" in res.stdout and "赤 1" in res.stdout


@needs_node
def test_検査が赤なら根治の入口を指し緑なら出さない():
    """赤の行だけを返す古い形（原因から直させない）に戻すと赤。"""
    bad = subprocess.run([NODE, str(CHECK), str(DATA / "bad.json")], capture_output=True, text=True)
    assert bad.returncode == 1 and "細目 §3「まず構造を疑う」" in bad.stdout.strip().splitlines()[-1]
    good = subprocess.run([NODE, str(CHECK), str(DATA / "good.json")], capture_output=True, text=True)
    assert good.returncode == 0 and "まず構造を疑う" not in good.stdout


def _load(path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dom(text):
    return '<pre id="selftest">%s</pre>' % text if text is not None else "<html></html>"


@pytest.mark.parametrize("selftest", ["SELFTEST NG\nscr1: 例外", None])
def test_理論モックの検査は_NG_なら最後に根治の入口を指し_OK_なら指さない(tmp_path, monkeypatch, capsys, selftest):
    """NG の行だけを返す古い形（1 つずつ潰させる）に戻すと赤。Chrome は使わず DOM を作り物にする。"""
    tm = _load(SKILLS / "theory-mock" / "scripts" / "check_theory_mock.py", "check_theory_mock")
    page = tmp_path / "m.html"
    page.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(tm, "find_chrome", lambda: "chrome")
    monkeypatch.setattr(tm, "dump_dom", lambda cmd: (_dom(selftest), ""))
    assert tm.main(["x", str(page)]) == 1
    assert "細目 §3「まず構造を疑う」" in capsys.readouterr().out.strip().splitlines()[-1]
    monkeypatch.setattr(tm, "dump_dom", lambda cmd: (_dom("SELFTEST OK 3 screens"), ""))
    assert tm.main(["x", str(page)]) == 0
    assert "まず構造を疑う" not in capsys.readouterr().out


@pytest.mark.parametrize("selftest", ["SELFTEST NG\ntab1/s1: 根拠が空", None])
def test_Blueprint_の検査は_NG_なら最後に根治の入口を指し_OK_なら指さない(tmp_path, monkeypatch, capsys, selftest):
    bp = _load(SKILLS / "blueprint" / "scripts" / "check_blueprint.py", "check_blueprint")
    page = tmp_path / "b.html"
    page.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(bp, "open_dom", lambda target, mode: _dom(selftest))
    assert bp.check(str(page)) == 1
    assert "細目 §3「まず構造を疑う」" in capsys.readouterr().out.strip().splitlines()[-1]
    monkeypatch.setattr(bp, "open_dom", lambda target, mode: _dom("SELFTEST OK 1 tabs 2 steps"))
    assert bp.check(str(page)) == 0
    assert "まず構造を疑う" not in capsys.readouterr().out


def test_Blueprint_の比較で材料が読めなければ最後に根治の入口を指す(tmp_path, monkeypatch, capsys):
    bp = _load(SKILLS / "blueprint" / "scripts" / "check_blueprint.py", "check_blueprint")
    a, b = tmp_path / "a.html", tmp_path / "b.html"
    for f in (a, b):
        f.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(bp, "open_dom", lambda target, mode: "<html></html>")
    assert bp.compare(str(a), str(b)) == 1
    assert "細目 §3「まず構造を疑う」" in capsys.readouterr().out.strip().splitlines()[-1]
