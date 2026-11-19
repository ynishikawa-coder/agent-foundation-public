"""qa-html の型・検査・答えの形を、使う側が写さずに土台の正本から直に読む口の試験（作り物の入力だけ）。

守る約束: 型は `check.mjs --template` で一字違わず出る／答えの形（qa-html/2）の正本は check.mjs の ANSWER_FORM・ANSWER_KEYS の
1 か所で、型の JS が作る答えと SKILL.md の例がそれに合う／写した古い形・知らない鍵・欠けた鍵の答えは `check.mjs --answer` が赤。
"""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
QA = ROOT / "plugins" / "docs-kit" / "skills" / "qa-html"
CHECK = QA / "check.mjs"
TEMPLATE = QA / "references" / "template.html"
SKILL = QA / "SKILL.md"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="node が無い（qa-html の検査は node で動く）")

GOOD = {
    "form": "qa-html/2", "title": "作り物の確認", "version": "2026-11-19.1", "receipt": "R261119-7KQ4",
    "answered_at": "2026-11-19T17:41:00+09:00",
    "answers": {"q1": ["down"], "q2": ["__unknown__"]},
    "labels": {"q1": ["切り捨てる"], "q2": ["分からない・確かめてから答える"]},
    "supp": {"q2": "係の人に聞けば分かります"}, "free": "",
}


def answer(obj_or_text, *more):
    src = obj_or_text if isinstance(obj_or_text, str) else json.dumps(obj_or_text, ensure_ascii=False)
    p = subprocess.run([NODE, str(CHECK), "--answer", "-", "--json", *more], input=src, capture_output=True, text=True, timeout=60)
    assert p.returncode in (0, 1), p.stderr
    out = json.loads(p.stdout)
    assert out["ok"] == (p.returncode == 0)
    return out


def node_const(name):
    js = f"import({json.dumps(CHECK.as_uri())}).then(m => console.log(JSON.stringify(m.{name})))"
    p = subprocess.run([NODE, "--input-type=module", "-e", js], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


@needs_node
def test_型は_template_の口で一字違わず出る():
    p = subprocess.run([NODE, str(CHECK), "--template"], capture_output=True, timeout=60)
    assert p.returncode == 0 and p.stdout == TEMPLATE.read_bytes()


@needs_node
def test_型の_JS_が作る答えの頭は答えの形の正本と同じ():
    """型の payload() の物の鍵と形の名が、check.mjs の ANSWER_KEYS・ANSWER_FORM と同じ（どちらかだけ直すと赤）。"""
    m = re.search(r"var p = \{ (form: '([^']+)'.*?) \};", TEMPLATE.read_text(encoding="utf-8"))
    assert m, "型の JS に答えを作る所（var p = { form: … }）が無い"
    keys = re.findall(r"(?:^|, )([a-z_]+):", m.group(1))
    assert m.group(2) == node_const("ANSWER_FORM")
    assert keys == node_const("ANSWER_KEYS")


@needs_node
def test_SKILL_の答えの例は答えの形の検査で緑():
    text = SKILL.read_text(encoding="utf-8")
    sec = text[text.index("### 答えの形"):]
    block = re.search(r"```json\n(.*?)\n```", sec, re.S).group(1)
    assert answer(block)["red"] == []


@needs_node
def test_作り物の良い答えは緑():
    assert answer(GOOD) == {"form": "qa-html/2", "ok": True, "red": []}


@needs_node
@pytest.mark.parametrize("name, change, expect", [
    ("写した古い形の名", {"form": "qa-html/1"}, "答えの形が qa-html/2 でない"),
    ("形の名が無い", {"form": None}, "答えの形が qa-html/2 でない"),
    ("知らない鍵（写しの側だけ足した）", {"sheet": "x"}, "答えに知らない鍵 sheet"),
    ("受付番号の形が違う", {"receipt": "12345"}, "受付番号（receipt）が R<YYMMDD>-<英数 4 字> でない"),
    ("時刻にタイムゾーンが無い", {"answered_at": "2026-11-19T17:41:00"}, "タイムゾーン付きの時刻でない"),
    ("答えが並びでない（前の形）", {"answers": {"q1": "down", "q2": ["__unknown__"]}}, "answers.q1 が文字の並びでない"),
    ("見出しの数が答えと違う", {"labels": {"q1": [], "q2": ["分からない・確かめてから答える"]}}, "labels.q1 が answers.q1 と同じ数"),
    ("ひとことが答えに無い問いを指す", {"supp": {"q9": "x"}}, "supp に answers に無い問いの鍵 q9"),
])
def test_形の違う答えは赤(name, change, expect):
    bad = {**GOOD}
    for k, v in change.items():
        if v is None:
            bad.pop(k)
        else:
            bad[k] = v
    red = answer(bad)["red"]
    assert any(expect in r for r in red), (name, red)


@needs_node
@pytest.mark.parametrize("key", ["version", "receipt", "labels", "free"])
def test_欠けた鍵は赤(key):
    bad = {k: v for k, v in GOOD.items() if k != key}
    assert f"答えに鍵 {key} が無い" in answer(bad)["red"]


@needs_node
def test_配る口が足す鍵は名指しした物だけ通る():
    mine = {**GOOD, "respondent": "作り物 花子"}
    assert answer(mine)["red"] == ["答えに知らない鍵 respondent（形 qa-html/2 の鍵は form・title・version・receipt・answered_at・answers・labels・supp・free）"]
    assert answer(mine, "--extra", "respondent")["red"] == []
    assert answer({**mine, "sheet": "x"}, "--extra", "respondent")["red"][0].startswith("答えに知らない鍵 sheet")
    assert answer(GOOD, "--extra", "form")["red"] == ["足す鍵 form は答えの形 qa-html/2 の鍵と重なる"]


@needs_node
def test_読めない答えは赤():
    assert answer("{ 壊れた")["red"][0].startswith("答えの JSON が読めない")


def _node_playwright():
    if not NODE:
        return False
    return subprocess.run([NODE, "-e", "require('playwright')"], capture_output=True, timeout=60).returncode == 0


@pytest.mark.skipif(not _node_playwright(), reason="node の playwright が無い（型の JS を実ブラウザで動かす）")
def test_型の_JS_が実際に作る答えは答えの形の検査で緑(tmp_path):
    spec = importlib.util.spec_from_file_location("af_test_docs_kit_for_answer", ROOT / "tests" / "test_docs_kit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    page = tmp_path / "確認.html"
    page.write_text(mod.filled_template("artifact"), encoding="utf-8")
    script = tmp_path / "run.cjs"
    script.write_text("""
const { chromium } = require('playwright');
(async () => {
  let b;
  try { b = await chromium.launch(); } catch (e) { console.log(JSON.stringify({ skip: String(e).split('\\n')[0] })); return; }
  const pg = await b.newPage();
  await pg.goto(process.argv[2]);
  const got = await pg.evaluate(() => new Promise((ok) => {
    document.addEventListener('qa:submit', (e) => ok(e.detail));
    document.querySelectorAll('fieldset.q[data-qkey]').forEach((f) => {
      const u = f.querySelector('input[value="__unknown__"]') || f.querySelector('input[type=radio]');
      if (u) { u.checked = true; u.dispatchEvent(new Event('change', { bubbles: true })); return; }
      const t = f.querySelector('input:not([type=hidden]):not([name^=supp_]), select');
      if (!t) return;
      t.value = t.type === 'date' ? '2026-11-19' : t.type === 'month' ? '2026-11' : t.type === 'number' ? '1' : '作り物';
      t.dispatchEvent(new Event('input', { bubbles: true }));
    });
    document.querySelector('form').requestSubmit(document.getElementById('sendbtn'));
  }));
  console.log(JSON.stringify({ got }));
  await b.close();
})();
""", encoding="utf-8")
    p = subprocess.run([NODE, str(script), page.as_uri()], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout.strip().splitlines()[-1])
    if "skip" in out:
        pytest.skip(f"ブラウザを起こせない: {out['skip']}")
    got = out["got"]
    assert got["form"] == "qa-html/2" and got["answers"], got
    assert answer(got)["red"] == []


@needs_node
def test_答えの形の赤は根治の入口を指し緑なら出さない():
    def run(obj):
        return subprocess.run([NODE, str(CHECK), "--answer", "-"], input=json.dumps(obj, ensure_ascii=False),
                              capture_output=True, text=True, timeout=60)
    bad = run({"form": "qa-html/1"})
    assert bad.returncode == 1 and "細目 §3「まず構造を疑う」" in bad.stdout.strip().splitlines()[-1]
    good = run(GOOD)
    assert good.returncode == 0 and "まず構造を疑う" not in good.stdout


@needs_node
@pytest.mark.parametrize("args", [["--template", "x"], ["--answer", "-", "--jsno"], ["--answer", "a.json", "b.json"], ["--answer", "-", "--extra"]])
def test_口の知らない引数は黙って捨てず止まる(args):
    p = subprocess.run([NODE, str(CHECK), *args], input="{}", capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and "知らない引数" in p.stderr, (args, p.stdout, p.stderr)


def test_隣の_plugin_の正本は同じ版だけを見て別の版へ降りない(tmp_path):
    sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
    try:
        import guard_common as G
    finally:
        sys.path.pop(0)
    rel = "scripts/x.py"
    market = tmp_path / "cache" / "market"
    other = market / "session-watch" / "zzz" / rel                # 別の版（新しい物）だけがある
    other.parent.mkdir(parents=True)
    other.write_text("#", encoding="utf-8")
    guard_root = market / "guard" / "aaa"
    guard_root.mkdir(parents=True)
    assert G.sibling_plugin_file("session-watch", rel, str(guard_root)) == ""
    same = market / "session-watch" / "aaa" / rel
    same.parent.mkdir(parents=True)
    same.write_text("#", encoding="utf-8")
    assert G.sibling_plugin_file("session-watch", rel, str(guard_root)) == str(same)
