"""決まりの文書（SKILL.md・README・CONTRIBUTING・細目）の値と、それを照らす道具の値が 1 つに揃っているかを見る。

なぜ在るか: 決まりの文書と道具の値が別々に書かれ、片方だけ変えても赤にならなかった（「分からない」の見分け・判定の点ごとの値・
qa-html の長さの上限・guard の既定・差し戻しの回数・変更の記録の札と枝の名・推奨の語）。
直し方は 2 つ: 写しを無くせる所は道具が文書を直に読む（verdict_form の点ごとの値・qa-html のなぜ聞くかの 5 文・changelog の札・
session-watch の「分からない」は guard の ask_shape.is_dunno を直に呼ぶ）。文書と道具の両方に値が要る所は、文書から値を読んで
道具の値と同じかを見る（片方だけ変えると赤）。各組に、値をわざとずらすと拒む注入の試験を置く。
"""
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUARD_SKILL = ROOT / "plugins/guard/skills/guard-rules/SKILL.md"
WATCH_SKILL = ROOT / "plugins/session-watch/skills/watch-log/SKILL.md"
REVIEW_SKILL = ROOT / "plugins/checker/skills/review-pr/SKILL.md"
QA_DIR = ROOT / "plugins/docs-kit/skills/qa-html"
QA_SKILL = QA_DIR / "SKILL.md"
QA_CHECK = QA_DIR / "check.mjs"


def _load(rel, name=None):
    spec = importlib.util.spec_from_file_location(name or "_doc_tool_" + Path(rel).stem, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _guard(rel):
    import sys
    sys.path.insert(0, str(ROOT / "plugins/guard/scripts"))
    try:
        return _load(rel)
    finally:
        sys.path.pop(0)


AS = _load("plugins/guard/scripts/ask_shape.py")
SW = _load("plugins/session-watch/scripts/session_watch.py")
VF = _load("plugins/checker/scripts/verdict_form.py")
CL = _load("scripts/changelog.py")
PS = _load("scripts/pr_shape.py")
GC = _guard("plugins/guard/scripts/guard_common.py")
PA = _guard("plugins/guard/scripts/prior_ask.py")

need_node = pytest.mark.skipif(shutil.which("node") is None, reason="node が無い所では qa-html の検査（check.mjs）を回せない")


def _node(js):
    r = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _qa_rules():
    return _node('import { RULES } from "%s"; console.log(JSON.stringify(RULES));' % QA_CHECK.as_posix())


def _read(p):
    return Path(p).read_text(encoding="utf-8")


# ── 1 「分からない」の選択肢の見分け（正本は guard の ask_shape.is_dunno・細目 §4）──────────────

def _dunno_word(text):
    m = re.search(r"どの問いにも「(.+?)」の選択肢", text)
    assert m, "細目 §4 の「どの問いにも「分からない」の選択肢」の文が無いか形が変わった"
    return m.group(1)


def _dunno_forms(text):
    m = re.search(r"「分からない」の選択肢（見出しの頭が(.+?)）に在る", text)
    assert m, "guard-rules の「分からない」の選択肢の形の並びが無いか形が変わった"
    return m.group(1).split("・")


def test_細目の分からないは_ask_shape_の見分けに当たる():
    assert AS.is_dunno(_dunno_word(_read(ROOT / "plugins/core/細目.md")))


def test_guard_rules_に書いた分からないの形は全部_ask_shape_の見分けに当たる():
    forms = _dunno_forms(_read(GUARD_SKILL))
    assert len(forms) >= 2 and all(AS.is_dunno(f) for f in forms), forms


@need_node
def test_qa_html_の型が出す分からないの見出しは_ask_shape_の見分けに当たる():
    assert AS.is_dunno(_qa_rules()["unknown"]["label"])


@pytest.mark.parametrize("label", ["分からない", "わからない", "まだ分からない", "分かりません", "Unknown", "知らない",
                                   "A 案で進める", "不明点を先に洗う", "確かめてから決める"])
def test_session_watch_の分からないの見分けは_ask_shape_と同じ(label):
    assert SW.has_idk({"options": [{"label": label}]}) is AS.is_dunno(label)


def test_分からないの見分けの正本が無い時は_session_watch_は見分けたと言わない(monkeypatch):
    """注入の試験: 正本（ask_shape）が見つからない時、写しの見分けで黙って進まず None を返し neighbor の札を出す。"""
    monkeypatch.setitem(SW._loaded, "ask_shape", None)
    assert SW.has_idk({"options": [{"label": "分からない"}]}) is None
    assert not hasattr(SW, "IDK"), "session_watch に「分からない」の写しが戻った"


def test_文の分からないを書き換えると見分けとずれて赤():
    """注入の試験: 細目の言葉を見分けに当たらない語へ替えると、この照らしは赤になる。"""
    bad = "どの問いにも「確かめる」の選択肢（選ぶと…）"
    assert not AS.is_dunno(_dunno_word(bad))


# ── 2 判定の点ごとに選べる値（正本は review-pr の SKILL.md の雛形・verdict_form が直に読む）────────

def test_判定の雛形の点は見る点の表の点と同じ():
    assert sorted(VF.load_values()) == sorted(VF.load_points())


def test_雛形で_pass_fail_だけの点に_N_A_を書くと赤():
    green = _read(ROOT / "tests/test_checker.py").split('GREEN = """', 1)[1].split('"""', 1)[0]
    assert VF.check(green, writer="session_WRITER01") == []
    only = [no for no, vs in VF.load_values().items() if vs == {"pass", "fail"}]
    assert only, "pass／fail だけの点が雛形に無い"
    names = VF.load_points()
    for no in only:
        text = re.sub(r"^- %d %s: .*$" % (no, re.escape(names[no])), "- %d %s: N/A" % (no, names[no]), green, flags=re.M)
        assert any("点 %d の値" % no in e for e in VF.check(text, writer="session_WRITER01")), no


def test_選べる値は雛形の行から読む(tmp_path):
    """注入の試験: 雛形の点 1 の値を書き換えると、道具の選べる値も変わる（写しが無い）。雛形が無ければ止まる。"""
    text = _read(REVIEW_SKILL)
    p = tmp_path / "SKILL.md"
    p.write_text(text.replace("- 1 依頼の充足: pass/fail（", "- 1 依頼の充足: pass/fail/N/A（"), encoding="utf-8")
    assert VF.load_values(p)[1] == {"pass", "fail", "N/A"}
    p.write_text(text.replace("\n## 点\n", "\n## 点の欄\n"), encoding="utf-8")
    with pytest.raises(ValueError):
        VF.load_values(p)


# ── 3 qa-html の宛先・問いの形・長さの上限の表（正本は check.mjs・SKILL.md は `--table` の出力をそのまま置く）──────

QA_TABLES = ("dests", "kinds", "limits")


def _skill_table(text, name):
    """SKILL.md の `<!-- check.mjs --table 名 … -->` と `<!-- /check.mjs --table 名 -->` の間（1 か所だけ）。"""
    m = re.findall(r"<!-- check\.mjs --table %s [^\n]*-->\n(.*?)\n<!-- /check\.mjs --table %s -->" % (name, name), text, re.S)
    assert len(m) == 1, f"SKILL.md に --table {name} の囲みが 1 つでない（{len(m)}）"
    return m[0]


def _qa_table(name):
    r = subprocess.run(["node", str(QA_CHECK), "--table", name], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    return r.stdout.rstrip("\n")


@need_node
@pytest.mark.parametrize("name", QA_TABLES)
def test_qa_html_の表は_check_の出力と一字違わず同じ(name):
    assert _skill_table(_read(QA_SKILL), name) == _qa_table(name)


@need_node
def test_qa_html_の表の写しを_1_字変えると照らしが割れる():
    """注入の試験: SKILL.md の表の 40 字を 41 字にする・行を足すと、check.mjs の出力と合わなくなる。"""
    text = _read(QA_SKILL)
    bad = text.replace("| 問い（legend） | 1 行・40 字 |", "| 問い（legend） | 1 行・41 字 |")
    assert bad != text and _skill_table(bad, "limits") != _qa_table("limits")
    bad = text.replace("| `copy`（写す） |", "| `mail`（送る） | 作り物 | 作り物 |\n| `copy`（写す） |")
    assert _skill_table(bad, "dests") != _qa_table("dests")


@need_node
def test_qa_html_の上限の鍵は表の行でちょうど_1_度使う():
    """注入の試験: RULES.limits に行の無い鍵を足す・鍵を消すと、表を作れずに投げる（表から黙って欠けない）。"""
    js = ('import { tables, RULES } from "%s"; const out = {};'
          'for (const [n, l] of [["extra", { ...RULES.limits, "作り物": 1 }], ["less", (({ rec_chars, ...r }) => r)(RULES.limits)]]) {'
          '  try { tables(l); out[n] = "通った"; } catch (e) { out[n] = e.message; } }'
          'console.log(JSON.stringify(out));') % QA_CHECK.as_posix()
    out = _node(js)
    assert "行が無い: 作り物" in out["extra"], out
    assert "知らない鍵 rec_chars" in out["less"], out


def test_qa_html_の値の表の鍵の行は_1_つずつ():
    rows = re.findall(r"^\| `(docs-kit\.qa-html\.[\w.*]+)`", _read(QA_SKILL), re.M)
    assert len(rows) == len(set(rows)), [k for k in rows if rows.count(k) > 1]


# ── 4 qa-html のなぜ聞くかの 5 文（正本は SKILL.md の表・check.mjs が直に読む）──────────────────

@need_node
def test_なぜ聞くかの_5_文は_SKILL_の表から読む():
    table = dict(re.findall(r"^\| `(\w+)` \| ([^|]+?) \|", _read(QA_SKILL).split("なぜ聞くかの決まった 5 文", 1)[1], re.M)[:5])
    assert _qa_rules()["why"] == table and len(table) == 5


@need_node
def test_なぜ聞くかの表を書き換えると検査の文も変わり_表が無いと止まる():
    """注入の試験: 表の文を替えると検査の文も替わる（写しが無い）。表が読めなければ検査は動かない。"""
    text = _read(QA_SKILL)
    js = ('import { loadWhy } from "%s"; const t = %s; const out = {};'
          'out.why = loadWhy(t.replace("今回だけの事を確かめます", "作り物の文"));'
          'try { loadWhy(t.replace("なぜ聞くかの決まった 5 文", "別の見出し")); out.threw = false; } catch { out.threw = true; }'
          'console.log(JSON.stringify(out));') % (QA_CHECK.as_posix(), json.dumps(text))
    out = _node(js)
    assert out["why"]["once"] == "作り物の文" and out["threw"] is True


# ── 5 guard の既定の値（guard_common.DEFAULTS ↔ guard-rules の SKILL.md）────────────────────

def _skill_defaults(text):
    said = {k: int(v) for k, v in re.findall(r"`(\w+)`[^`（〔]{0,4}[（〔]既定 (\d+)[）〕]", text)}
    block = json.loads(text.split("## 値の表", 1)[1].split("```json", 1)[1].split("```", 1)[0])["guard"]
    nums = {k: v for k, v in block.items() if isinstance(v, int) and not isinstance(v, bool)}
    return said, nums


def test_guard_の既定の数は_SKILL_の値と同じ():
    said, nums = _skill_defaults(_read(GUARD_SKILL))
    ints = {k: v for k, v in GC.DEFAULTS.items() if isinstance(v, int) and not isinstance(v, bool)}
    assert said and all(GC.DEFAULTS.get(k) == v for k, v in said.items()), said
    assert nums == ints, "値の表の例の数と guard の既定の数が違う（片方だけ変えた）"


def test_SKILL_の既定を書き換えると_guard_の既定とずれて赤():
    """注入の試験。"""
    text = _read(GUARD_SKILL).replace("（既定 60）", "（既定 61）").replace('"context_limit": 300000', '"context_limit": 300001')
    said, nums = _skill_defaults(text)
    assert said["ask_question_max_chars"] != GC.DEFAULTS["ask_question_max_chars"]
    assert nums["context_limit"] != GC.DEFAULTS["context_limit"]


# ── 6 差し戻し・止める回数（session_watch ↔ watch-log、prior_ask ↔ guard-rules）─────────────────

def _watch_stop(text):
    line = next(ln for ln in text.splitlines() if "は、Stop の hook" in ln)
    codes = re.findall(r"`(\w+)`", line.split("は、Stop の hook", 1)[0])
    m = re.search(r"同じターンで (\d+) 回まで", line)
    return tuple(codes), int(m.group(1)) if m else None


def _prior_max(text):
    row = next(ln for ln in text.splitlines() if ln.startswith("| prior_ask"))
    m = re.search(r"同じ頼みの中で (\d+) 回まで", row)
    return int(m.group(1)) if m else None


def test_Stop_で差し戻す札と回数は_watch_log_の文と同じ():
    codes, most = _watch_stop(_read(WATCH_SKILL))
    assert codes == SW.STOP_CODES and most == SW.STOP_MAX


def test_聞く前に引いた跡で止める回数は_guard_rules_の文と同じ():
    assert _prior_max(_read(GUARD_SKILL)) == PA.ASK_PRIOR_MAX


def test_回数と札を書き換えると道具とずれて赤():
    """注入の試験。"""
    w = _read(WATCH_SKILL).replace("同じターンで 2 回まで", "同じターンで 3 回まで").replace("・`neighbor` は、Stop", " は、Stop")
    codes, most = _watch_stop(w)
    assert codes != SW.STOP_CODES and most != SW.STOP_MAX
    assert _prior_max(_read(GUARD_SKILL).replace("同じ頼みの中で 2 回まで", "同じ頼みの中で 5 回まで")) != PA.ASK_PRIOR_MAX


# ── 7 変更の記録の札（正本は CHANGELOG.d/README.md・changelog が直に読む）と枝の名（CONTRIBUTING ↔ pr_shape）──

def test_変更の記録の札は_README_から読む(tmp_path):
    """注入の試験: README の札を替えると道具の札も替わる（写しが無い）。札の行が無ければ止まる。"""
    text = _read(ROOT / "CHANGELOG.d/README.md")
    assert CL.load_cards() == CL.CARDS and CL.LINE_RE.match("- %s: 何か" % CL.CARDS[-1])
    p = tmp_path / "README.md"
    p.write_text(text.replace("`畳んだ` のどれか", "`畳んだ`・`作り物` のどれか"), encoding="utf-8")
    assert CL.load_cards(p)[-1] == "作り物"
    p.write_text(text.replace("札は", "印は"), encoding="utf-8")
    with pytest.raises(ValueError):
        CL.load_cards(p)


def _branch_rule(text):
    m = re.search(r"枝の名は `(\w+)/<日付>-<話題>`。日付は `(Y+M+D+)`（例: `([^`]+)`）", text)
    assert m, "CONTRIBUTING の枝の名の文が無いか形が変わった"
    return m.group(1), len(m.group(2)), m.group(3)


def test_枝の名の決まりと_pr_shape_の枝の形は同じ():
    prefix, digits, example = _branch_rule(_read(ROOT / "CONTRIBUTING.md"))
    assert PS.BRANCH.match(example), example
    assert PS.BRANCH.pattern.startswith("^%s/(\\d{%d}-" % (prefix, digits))
    m = PS.BRANCH.match(example)
    assert CL.NAME_RE.match(m.group(1) + ".txt"), "枝から決まる変更の記録の断片の名が、記録の名の形に合わない"


def test_枝の名の決まりを書き換えると_pr_shape_とずれて赤():
    """注入の試験: 日付の桁や頭の名を替えた決まりは、道具の形と合わない。"""
    text = _read(ROOT / "CONTRIBUTING.md")
    prefix, digits, _ = _branch_rule(text.replace("日付は `YYYYMMDD`", "日付は `YYMMDD`"))
    assert not PS.BRANCH.pattern.startswith("^%s/(\\d{%d}-" % (prefix, digits))
    _, _, ex = _branch_rule(text.replace("（例: `claude/20261111-hone`）", "（例: `ai/20261111-hone`）"))
    assert not PS.BRANCH.match(ex)


# ── 8 推奨の語（ask_shape の _REC_WORD ↔ check.mjs の recommend ↔ guard-rules の SKILL.md）──────────

def _skill_rec_words(text):
    m = re.search(r"推奨の語（([^。）]+)", text)
    assert m, "guard-rules の推奨の語の並びが無いか形が変わった"
    return {w.lower() for w in m.group(1).split("・")}


def _alts(pattern):
    return {w.lower() for w in pattern.split("|")}


@need_node
def test_推奨の語は_3_か所で同じ():
    tool = _alts(AS._REC_WORD.pattern)
    assert AS._REC_WORD.flags & re.I, "選択肢の画面の見張りは大小を問わない"
    assert _alts(_qa_rules()["recommend"]) == tool, "確認ページの検査の推奨の語が選択肢の画面の見張りと違う"
    assert _skill_rec_words(_read(GUARD_SKILL)) == tool, "guard-rules の推奨の語の並びが見張りと違う"


def test_推奨の語を_1_つ抜くと赤():
    """注入の試験。"""
    bad = _read(GUARD_SKILL).replace("・おススメ・", "・")
    assert _skill_rec_words(bad) != _alts(AS._REC_WORD.pattern)
