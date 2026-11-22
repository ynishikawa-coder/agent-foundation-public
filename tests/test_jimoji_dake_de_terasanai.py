"""決まった字の有無でなく形で照らす約束の注入の試験（2026-11-22 原因の台帳・束A）。

意図: 型・表・欄・締めの行・値を守る試験が、守る物が崩れたら赤になり、言い回しだけ変えても緑のままでいる。
課題: 試験が決まった字（文・欄の名・表の 1 行）の有無だけを見ていたので、字を残して形（欄・順・表の行・値の結び）を
  崩しても緑で、言い回しを変えると形が残っていても赤だった。値（窓の大きさ）は試験が手で写していた。
原因: 照らす物ごとに「形の正本（読む道具・型・表の頭・正規表現）」を引かず、文を写して照らしていた。
解決: 照らしは形の正本を直に読む＝締めの 2 行は session_watch の CLOSE_AI／CLOSE_OWNER・整地の欄は guard の
  pr_text.template_parts と細目 §3 の根治の段・全体の絵の説明は big_picture の explain と絵の JSON・PR の型の頭は
  CONTRIBUTING の「冒頭の欄」の文と型の頭の塊を突き合わせる。各照らしは崩した作り物で赤・言い換えで緑を確かめる。
"""
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

from test_kata_no_ran import 根治の段
from test_session_watch import sw

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "plugins" / "core" / "核.md"
SAIMOKU5 = ROOT / "plugins" / "core" / "細目" / "05-返事の形.md"
REVIEW = ROOT / "plugins" / "checker" / "skills" / "review-pr" / "SKILL.md"
SEICHI = ROOT / "plugins" / "dev-flow" / "skills" / "preimpl-cleanup" / "整地受領証.template.md"
REGISTER = ROOT / "plugins" / "dev-flow" / "skills" / "register-rule" / "SKILL.md"
BP_DIR = ROOT / "plugins" / "docs-kit" / "skills" / "big-picture"
BP_TOOL = BP_DIR / "scripts" / "big_picture.py"
BP_HTML = BP_DIR / "references" / "template.html"
DODAI = ROOT / "docs" / "全体の絵.json"
PR_TPL = ROOT / ".github" / "pull_request_template.md"
CONTRIB = ROOT / "CONTRIBUTING.md"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True   # plugins/ の中に __pycache__ を作らない
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))   # pr_text が同じ dir の guard_common を読む
import pr_text  # noqa: E402
bp = _load("big_picture_jimoji", BP_TOOL)


def _r(p):
    return p.read_text(encoding="utf-8")


def _swap(text, a, b):
    return text.replace(a, "\0").replace(b, a).replace("\0", b)


# ── 締めの 2 行（核 §5・細目 §5）: 文でなく、返事を読む道具の形で照らす ──────────────


def 締めの名(core):
    """核 §5 の締めの 2 行の名（`…:` の形の字）を順に返す。"""
    sec = core[core.index("\n## 5."):core.index("\n## 6.")]
    return re.findall(r"`([^`\n]+[:：])`", sec)


def _項目(text):
    """箇条の上の段ごとに、下の段の行の並びを返す。"""
    out = []
    for line in text.splitlines():
        if line.startswith("- "):
            out.append([])
        elif out and re.match(r"^  - ", line):
            out[-1].append(line)
    return out


def 締めの外れ(core, saimoku):
    bad = []
    names = 締めの名(core)
    if len(names) != 2:
        return ["核 §5 の締めの名が 2 つでない: %r" % names]
    ai, owner = names
    if not sw.CLOSE_AI.match(ai + " x"):
        bad.append("1 つ目が道具の AI の締めの形でない: " + ai)
    if not sw.CLOSE_OWNER.match(owner + " x"):
        bad.append("2 つ目が道具のあなたの締めの形でない: " + owner)
    if sw.split_close("本文\n%s なし\n%s なし" % (ai, owner))[1] is None:
        bad.append("この順の 2 行を道具が締めと読まない")
    sub = next((s for s in _項目(saimoku) if s and ("`" + ai) in s[0]), None)
    if sub is None or len(sub) != 2:
        return bad + ["細目 §5 に締めの 2 行の例の 2 段が無い"]
    for line, pat in zip(sub, (sw.CLOSE_AI, sw.CLOSE_OWNER)):
        ex = re.findall(r"`([^`\n]+)`", line)
        if not ex or not all(pat.match(e) for e in ex):
            bad.append("細目 §5 の例が道具の形でない: " + line.strip())
    return bad


def test_締めの_2_行は返事を読む道具の形で決まりに在る():
    core, s5 = _r(CORE), _r(SAIMOKU5)
    assert 締めの外れ(core, s5) == []
    ai, owner = 締めの名(core)
    # 注入: 順を入れ替える・名を変える・1 つ消すと赤
    assert 締めの外れ(_swap(core, ai, owner), s5)
    assert 締めの外れ(core.replace(ai, "AI の次の手:"), s5)
    assert 締めの外れ(core.replace("`" + owner + "`", owner), s5)
    assert 締めの外れ(core, s5.replace("`" + ai + " なし`", "`AI の次: なし`"))
    assert 締めの外れ(core, s5.replace("`" + owner + " なし`", "`" + ai + " なし`"))
    # 言い回しを変えても形が残れば緑
    sec_start = core.index("\n## 5.")
    reworded = core[:sec_start] + core[sec_start:].replace("最後の 2 行は", "返事の終わりの 2 行は", 1)
    assert reworded != core and 締めの外れ(reworded, s5) == []


# ── review-pr の点 1 が指す整地の欄: 整地の型の見出しから引く ──────────────────────


def 表(text, first):
    """頭の行の最初の欄が first の表の (頭の欄, 行の欄の並び)。無ければ (None, [])。"""
    lines = text.splitlines()
    for n, ln in enumerate(lines):
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if ln.startswith("|") and cells[0] == first:
            rows = []
            for x in lines[n + 2:]:
                if not x.startswith("|"):
                    break
                rows.append([c.strip() for c in x.strip().strip("|").split("|")])
            return cells, rows
    return None, []


def 点の行(text, no):
    head, rows = 表(text, "点")
    return head, next((r for r in rows if r[0].split(" ")[0] == str(no)), None)


def 点1の整地の欄(review, template_path):
    head, row = 点の行(review, 1)
    if row is None:
        return ["点 1 の行が無い"]
    refs = re.findall(r"`(\d+)\. ([^`]+)`", row[1])
    heads, _ = pr_text.template_parts(template_path)
    want = [(no, name) for no, name in heads if name in 根治の段()[:2]]
    return [] if refs == want and len(want) == 2 else ["点 1 の整地の欄 %r が型の見出し %r と違う" % (refs, want)]


def test_review_pr_の点1は整地の型の見出しの意図と課題を指す():
    review = _r(REVIEW)
    assert 点1の整地の欄(review, SEICHI) == []
    with tempfile.TemporaryDirectory() as d:
        fake = Path(d) / "t.md"
        # 注入: 型の見出しの名を変える・番号を変えると赤
        fake.write_text(_r(SEICHI).replace("## 1. 意図", "## 1. ねらい"), encoding="utf-8")
        assert 点1の整地の欄(review, fake)
        fake.write_text(_r(SEICHI).replace("## 2. 課題", "## 3. 課題"), encoding="utf-8")
        assert 点1の整地の欄(review, fake)
    # 注入: 点 1 が欄を 1 つ落とすと赤
    assert 点1の整地の欄(review.replace("`2. 課題`", "課題", 1), SEICHI)


# ── review-pr の点 13 が全体の絵の道具を指す: 表の行・節・道具の口で照らす ──────────────


def 点13の外れ(review, tool_src):
    head, row = 点の行(review, 13)
    if row is None or len(row) != len(head):
        return ["点 13 が表の行として無い"]
    m = re.search(r"下の「([^」]+)」", row[1])
    if not m:
        return ["点 13 が下の節を指さない"]
    h = re.search(r"^## %s（点 13）\n(.*?)(?=^## |\Z)" % re.escape(m.group(1)), review, re.M | re.S)
    if not h:
        return ["点 13 の指す節が無い: " + m.group(1)]
    sec = h.group(1)
    tup = re.search(r"argv\[1\] not in \(([^)]*)\)", tool_src)
    subs = re.findall(r'"(\w+)"', tup.group(1)) if tup else []
    cmds = re.findall(r"`[^`\n]*big_picture\.py (\w+) [^`\n]*`", sec)
    bad = []
    if "compare" not in cmds or "compare" not in subs:
        bad.append("節に道具の照らし（compare）の命令が無い・道具が受けない")
    if "docs/全体の絵.json" not in sec or not DODAI.exists():
        bad.append("節が土台の絵を指さない")
    if "申告" not in row[2]:
        bad.append("red の欄に書いた窓の申告で照らした時が無い")
    return bad


def test_review_pr_の点13は表の行と節で全体の絵の道具を指す():
    review, src = _r(REVIEW), _r(BP_TOOL)
    assert 点13の外れ(review, src) == []
    _, row = 点の行(review, 13)
    line = next(ln for ln in review.splitlines() if ln.startswith("| " + row[0] + " |"))
    # 注入: 表の行を崩す（欄を 1 つ落とす）・節の見出しを変える・道具が compare を受けなくなると赤
    assert 点13の外れ(review.replace(line, line.rsplit("|", 2)[0] + "|"), src)
    assert 点13の外れ(review.replace("（点 13）", "（点 14）"), src)
    assert 点13の外れ(review, src.replace('"compare", "explain")', '"explain")'))


# ── 全体の絵の説明（explain）: 欄の並びと値を絵の JSON と結ぶ ──────────────────────

説明の欄 = re.compile(r"^- ([^:（\n]+)(?:（[^）\n]*）)?: (.*)$")


def 説明の外れ(text, pic, pid):
    B = {b["id"]: b for b in pic["boxes"]}
    p = next(x for x in pic["problems"] if x["id"] == pid)
    c = B[p["cause"]]
    fields = [(m.group(1), m.group(2)) for m in map(説明の欄.match, text.splitlines()) if m]
    names = [n for n, _ in fields]
    f = dict(fields)
    bad = []
    if len(set(names)) != len(names):
        bad.append("欄が重なる")
    if names[:2] != 根治の段()[:2]:
        bad.append("頭の 2 欄が根治の段の意図・課題でない: %r" % names[:2])
    want = {
        "課題": lambda v: v == p["title"],
        "意図": lambda v: all("【%s】" % B[i]["t"] in v for i in p["at"]),
        "起きた所": lambda v: all("【%s】" % B[i]["t"] in v for i in p["at"]),
        "原因の箱": lambda v: v.startswith("【%s】" % c["t"]) and (("構造から来る" in v) == (p["origin"] == "構造")),
        "流れ": lambda v: v.startswith("【%s】" % c["t"]),
        "原因の箱の意図": lambda v: v == (c.get("intent") or v),
        "なぜここから起きたか": lambda v: v == p["why_here"],
        "この箱で起きた問題": lambda v: v.startswith("%d " % sum(x["cause"] == p["cause"] for x in pic["problems"])),
    }
    for k, ok in want.items():
        if k not in f:
            bad.append("欄が無い: " + k)
        elif not ok(f[k]):
            bad.append("値が絵と違う: %s = %s" % (k, f[k]))
    return bad


def test_全体の絵の説明は欄の形で絵の値を並べる():
    pic = json.loads(_r(DODAI))
    pid = pic["problems"][0]["id"]
    text = bp.explain(pic, pid)
    assert 説明の外れ(text, pic, pid) == []
    lines = text.splitlines()
    first, second = lines[1], lines[2]
    why = next(ln for ln in lines if ln.startswith("- なぜここから"))
    # 注入: 欄を落とす・意図と課題の順を入れ替える・欄の頭を崩す・値を絵と違えると赤
    assert 説明の外れ(text.replace(why + "\n", ""), pic, pid)
    assert 説明の外れ(text.replace(first, "\0").replace(second, first).replace("\0", second), pic, pid)
    assert 説明の外れ(text.replace("- 原因の箱:", "原因の箱:"), pic, pid)
    assert 説明の外れ(text.replace(why, why + "（違う）"), pic, pid)
    # 言い回し（括弧の添え書き）を変えても欄が残れば緑
    assert 説明の外れ(re.sub(r"（[^）\n]*）:", "（言い換え）:", text), pic, pid) == []


# ── 全体の絵の型（template.html）: 意図と課題は別の欄で、各欄を script が埋める ──────────

ラベル = re.compile(r'<div class="lab">([^<（]+)(?:（[^<]*）)?</div><p id="(\w+)"></p>')
説明の層 = re.compile(r'<div class="lab">([^<（]+)（[^<]*）</div><p>\$\{esc\(p\.(\w+)\)\}</p>')


def 絵の型の外れ(html):
    pairs = ラベル.findall(html)
    names = [n for n, _ in pairs]
    dan = 根治の段()[:2]
    bad = []
    if [n for n in names if n in dan] != dan:
        bad.append("頭の欄に意図と課題が別々にこの順で無い: %r" % names)
    for n, i in pairs:
        if not re.search(r"\$\('%s'\)\.textContent=m\.\w+" % re.escape(i), html):
            bad.append("欄を script が埋めない: %s（%s）" % (n, i))
    if ("課題", "title") not in 説明の層.findall(html):
        bad.append("説明の層に課題（起きた事＝問題の題）の欄が無い")
    return bad


def test_全体の絵の型は意図と課題を別の欄に出す():
    html = _r(BP_HTML)
    assert 絵の型の外れ(html) == []
    # 注入: 課題の欄を意図の中へ混ぜる・欄の順を入れ替える・埋める口を消す・説明の層の課題を消すと赤
    assert 絵の型の外れ(html.replace('<div class="lab">課題（意図と今のずれ）</div><p id="problem"></p>', ""))
    a = '<div class="lab">意図（何のために在るか）</div><p id="intent"></p>'
    b = '<div class="lab">課題（意図と今のずれ）</div><p id="problem"></p>'
    assert a in html and b in html
    assert 絵の型の外れ(_swap(html, a, b))
    assert 絵の型の外れ(html.replace("$('problem').textContent=", "void "))
    assert 絵の型の外れ(html.replace('<div class="lab">課題（この意図とのずれ＝起きた事）</div>', '<div class="lab">起きた事（ずれ）</div>'))
    # 言い回し（括弧の添え書き）を変えても欄が残れば緑
    assert 絵の型の外れ(html.replace("（意図と今のずれ）", "（言い換え）")) == []


# ── register-rule の Step 1 は核 §3 の分け方を表で写さない ─────────────────────────


def step1(text):
    return text[text.index("## Step 1"):text.index("## Step 2")]


def 表の写し(sec):
    return [ln for ln in sec.splitlines() if re.match(r"^\s*\|.*\|\s*$", ln)]


def test_register_rule_の_Step1_は表を持たない():
    s = step1(_r(REGISTER))
    assert 表の写し(s) == [], "Step 1 に表がある（核 §3 の分け方を写さず指す）"
    # 注入: 欄の名を言い換えた表でも赤
    assert 表の写し(s + "\n| 入れる物 | 決める人 |\n|---|---|\n| 止める物 | オーナー |\n")


# ── PR の型: 頭の欄は CONTRIBUTING の決まりと同じ・残りの行は台帳の行の id だけ ──────────


def 頭の欄(tpl):
    """型の頭の塊（最初の空行まで）の欄の名。欄の形でない行は None を入れる。"""
    head = tpl.split("\n\n", 1)[0]
    return [(m.group(1) if (m := re.match(r"^([^\s:：<]+)\s*[:：]\s*\S", ln)) else None) for ln in head.splitlines()]


def 頭の外れ(tpl, contributing):
    m = re.search(r"冒頭の欄は (\S+?) の (\d+) 行", contributing)
    if not m:
        return ["CONTRIBUTING に冒頭の欄の決まりが無い"]
    names, n = m.group(1).split("・"), int(m.group(2))
    got = 頭の欄(tpl)
    return [] if got == names and len(got) == n else ["型の頭 %r が決まり %r（%d 行）と違う" % (got, names, n)]


def test_PR_の型の頭は決まりの欄だけ():
    tpl, c = _r(PR_TPL), _r(CONTRIB)
    assert 頭の外れ(tpl, c) == []
    # 注入: 頭に写しの欄を足す・頭を欄の形でなくす・決まりの行の数を変えると赤
    assert 頭の外れ("書いた窓: <id>\n" + tpl, c)
    assert 頭の外れ(tpl.replace("job: ", "job ", 1), c)
    assert 頭の外れ(tpl, c.replace("冒頭の欄は job の 1 行", "冒頭の欄は job の 2 行"))


def 残りの形(tpl):
    """「残り」の節が書かせる行の形を、正規表現にして返す。形が崩れていれば外れの文。"""
    m = re.search(r"^## 残り[^\n]*\n(.*?)(?=^## |\Z)", tpl, re.M | re.S)
    if not m:
        return "残りの節が無い"
    forms = re.findall(r"`(- [^`\n]+)`", m.group(1))
    if len(forms) != 1:
        return "残りの行の形が 1 つでない: %r" % forms
    holders = re.findall(r"<([^>]+)>", forms[0])
    if len(holders) != 1 or re.search(r"[:：]", re.sub(r"<[^>]+>", "", forms[0])):
        return "残りの行に id の外の欄がある: " + forms[0]
    width = re.search(r"(\d+) 字", holders[0])
    hole = r"[0-9a-f]{%s}" % width.group(1) if width else r"\S+"
    return re.compile(re.escape(forms[0].split("<")[0]) + hole + re.escape(forms[0].split(">", 1)[1]) + r"$")


def test_PR_の型の残りの行は台帳の行の_id_だけ():
    tpl = _r(PR_TPL)
    form = 残りの形(tpl)
    assert not isinstance(form, str), form
    assert form.match("- 台帳の行 d9ba3aedbd20")
    assert not form.match("- 台帳の行 d9ba3aedbd20 行き先: 直す窓")
    # 注入: 行き先の欄を足す・形の行を消す・形を 2 つにすると赤
    line = re.search(r"`(- [^`\n]+)`", tpl).group(1)
    assert isinstance(残りの形(tpl.replace(line, line + " 行き先: <直す窓>")), str)
    assert isinstance(残りの形(tpl.replace("`" + line + "`", line)), str)
    assert isinstance(残りの形(tpl.replace("`" + line + "`", "`" + line + "` か `- 直す窓 <名>`")), str)
