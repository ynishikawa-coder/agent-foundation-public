"""決まりの文書（SKILL.md・README・CONTRIBUTING・細目）の値と、それを照らす道具の値が 1 つに揃っているかを見る。

意図: 決まりの文書と道具の値が片方だけ変わったら赤にする（「分からない」の見分け・判定の点ごとの値・
qa-html の長さの上限・guard の既定・差し戻しの回数・変更の記録の札と枝の名・推奨の語）。
課題: 片方だけ変えても赤にならなかった。
原因: 決まりの文書と道具の値が別々に書かれていた。
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
from saimoku import 全文 as 細目の全文
import test_doc_tool_values_okiba as OK

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
    word = OK.分からないの語(text)
    assert word, "細目 §4 の「選ぶ問いと開いた問い」の欄に「どの問いにも「分からない」の選択肢」の文が無いか形が変わった"
    return word


def _dunno_forms(text):
    forms = OK.分からないの形(text)
    assert forms, "guard-rules の見張りの表の ask_shape の行に「分からない」の選択肢の形の並びが無いか形が変わった"
    return forms


def test_細目の分からないは_ask_shape_の見分けに当たる():
    assert AS.is_dunno(_dunno_word(細目の全文()))


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
    """注入の試験: 細目 §4 の欄の言葉を見分けに当たらない語へ替えると、この照らしは赤になる（読んだ語から置き換えを作る）。"""
    t = 細目の全文()
    word = _dunno_word(t)
    bad = t.replace(f"どの問いにも「{word}」の選択肢", "どの問いにも「確かめる」の選択肢", 1)
    assert _dunno_word(bad) == "確かめる" and not AS.is_dunno(_dunno_word(bad))


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


# ── 3 qa-html の長さの上限（SKILL.md の表 ↔ check.mjs の RULES.limits）──────────────────────

# 鍵 → (表の「所」の頭, 「上限」の欄から数を取る形)
LIMIT_ROWS = {
    "question_chars": ("問い（legend）", r"(\d+) 字"),
    "glead_chars": ("まとまりの 1 行", r"(\d+) 字"),
    "about_tags": ("何について", r"札 (\d+) つ"),
    "known_lines": ("見つけた事", r"文 (\d+) 行"),
    "known_line_chars": ("見つけた事", r"1 行 (\d+) 字"),
    "known_table_rows": ("見つけた事", r"表 (\d+) 行"),
    "clips": ("切り抜き", r"1 問 (\d+) 枚"),
    "evidence": ("根拠", r"1 問 (\d+) つ"),
    "where_chars": ("根拠", r"場所 (\d+) 字"),
    "quote_chars": ("根拠", r"引用 (\d+) 字"),
    "reading_lines": ("AI の読み", r"1〜(\d+) 行"),
    "reading_line_chars": ("AI の読み", r"1 行 (\d+) 字"),
    "estimate_chars": ("AI の今の見込み", r"中身 (\d+) 字"),
    "basis_chars": ("AI の今の見込み", r"根拠 (\d+) 字"),
    "rec_chars": ("推す理由", r"(\d+) 字"),
    "more_lines": ("くわしく", r"(\d+) 行"),
    "option_chars": ("選択肢の見出し", r"(\d+) 字"),
    "change_chars": ("この答えで変わる事", r"(\d+) 字"),
    "option_detail_chars": ("選択肢の添え書き", r"(\d+) 字"),
    "questions_per_page": ("1 枚の問いの数", r"(\d+) 問"),
}


def _skill_limits(text):
    body = OK.名の頭で節(text, "長さの上限")
    assert body is not None, "qa-html に「長さの上限」の節が 1 つでない"
    rows = [[c.strip() for c in ln.strip("|").split("|")] for ln in body.splitlines() if ln.startswith("| ") and "---" not in ln]
    out = {}
    for key, (head, pat) in LIMIT_ROWS.items():
        cells = [r[1] for r in rows if len(r) >= 2 and r[0].startswith(head)]
        assert len(cells) == 1, f"長さの上限の表に「{head}」の行が 1 つでない"
        m = re.search(pat, cells[0])
        assert m, f"「{head}」の上限 {cells[0]} から {key} が読めない"
        out[key] = int(m.group(1))
    return out


@need_node
def test_qa_html_の長さの上限の表と検査の上限は同じ():
    limits = _qa_rules()["limits"]
    assert set(limits) == set(LIMIT_ROWS), "検査の上限の鍵が表との対応（LIMIT_ROWS）と違う＝表に書いていない上限がある"
    assert _skill_limits(_read(QA_SKILL)) == limits


def test_長さの上限の表の数を書き換えると読み取りが変わる():
    """注入の試験: 表の問いの字数を 1 つ増やすと、読んだ上限が変わる（検査の値と合わなくなり上の試験が赤）。
    置き換えは読んだ値と LIMIT_ROWS の行の名から作る（表の 1 行や数を写さない）。表の外に同じ行を置いても読まない。"""
    text = _read(QA_SKILL)
    n = _skill_limits(text)["question_chars"]
    head, pat = LIMIT_ROWS["question_chars"]
    row = next(ln for ln in text.splitlines() if ln.startswith(f"| {head}"))
    bumped = re.sub(pat, lambda m: m.group(0).replace(m.group(1), str(n + 1)), row, count=1)
    assert _skill_limits(text.replace(row, bumped, 1))["question_chars"] == n + 1
    first = next(ln for ln in text.splitlines() if ln.startswith("## "))
    assert _skill_limits(text.replace(first, bumped + "\n\n" + first, 1))["question_chars"] == n


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
    nums = OK.値の表の数(text)
    assert nums is not None, "guard-rules の「値の表」の節に json の囲いが 1 つでない"
    return OK.書いた既定(text), nums


def test_guard_の既定の数は_SKILL_の値と同じ():
    said, nums = _skill_defaults(_read(GUARD_SKILL))
    ints = {k: v for k, v in GC.DEFAULTS.items() if isinstance(v, int) and not isinstance(v, bool)}
    assert said and all(GC.DEFAULTS.get(k) == v for k, v in said.items()), said
    assert nums == ints, "値の表の例の数と guard の既定の数が違う（片方だけ変えた）"


def test_SKILL_の既定を書き換えると_guard_の既定とずれて赤():
    """注入の試験: 読んだ鍵と値から置き換えを作る（「（既定 60）」や json の行を写さない）。"""
    text = _read(GUARD_SKILL)
    said, nums = _skill_defaults(text)
    k, v = next(iter(said.items()))
    row = next(ln for ln in text.splitlines() if ln.startswith("| ") and f"`{k}`" in ln and "既定" in ln)
    bad = text.replace(row, re.sub(rf"(`{k}`[^`（〔]{{0,4}}[（〔]既定 ){v}", lambda m: f"{m.group(1)}{v + 1}", row, count=1), 1)
    assert _skill_defaults(bad)[0][k] != GC.DEFAULTS[k]
    nk, nv = next(iter(nums.items()))
    bad = text.replace(f'"{nk}": {nv}', f'"{nk}": {nv + 1}', 1)
    assert _skill_defaults(bad)[1][nk] != GC.DEFAULTS[nk]


# ── 6 知らせる札・止める回数（session_watch ↔ watch-log、prior_ask ↔ guard-rules）─────────────────

def _watch_stop(text):
    return OK.Stopの札(text)


def _prior_max(text):
    return OK.止める回数(text)


def test_Stop_で知らせる札は_watch_log_の文と同じ():
    assert _watch_stop(_read(WATCH_SKILL)) == SW.STOP_CODES


def test_聞く前に引いた跡で止める回数は_guard_rules_の文と同じ():
    assert _prior_max(_read(GUARD_SKILL)) == PA.ASK_PRIOR_MAX


def test_回数と札を書き換えると道具とずれて赤():
    """注入の試験: 読んだ札・回数から置き換えを作る（札の名や「2 回」を写さない）。"""
    w = _read(WATCH_SKILL)
    last = _watch_stop(w)[-1]
    assert _watch_stop(w.replace(f"・`{last}` は、Stop", " は、Stop", 1)) != SW.STOP_CODES
    g = _read(GUARD_SKILL)
    n = _prior_max(g)
    bad = re.sub(rf"(同じ頼みの中で ){n}( 回まで)", lambda m: f"{m.group(1)}{n + 3}{m.group(2)}", g, count=1)
    assert _prior_max(bad) != PA.ASK_PRIOR_MAX


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
    rule = OK.枝の決まり(text)
    assert rule, "CONTRIBUTING の「1. 枝と PR」の節に枝の名の文が 1 つでないか形が変わった"
    return rule


def test_枝の名の決まりと_pr_shape_の枝の形は同じ():
    prefix, digits, example = _branch_rule(_read(ROOT / "CONTRIBUTING.md"))
    assert PS.BRANCH.match(example), example
    assert PS.BRANCH.pattern.startswith("^%s/(\\d{%d}-" % (prefix, digits))
    m = PS.BRANCH.match(example)
    assert CL.NAME_RE.match(m.group(1) + ".txt"), "枝から決まる変更の記録の断片の名が、記録の名の形に合わない"


def test_枝の名の決まりを書き換えると_pr_shape_とずれて赤():
    """注入の試験: 日付の桁や頭の名を替えた決まりは、道具の形と合わない（置き換えは読んだ決まりから作る）。"""
    text = _read(ROOT / "CONTRIBUTING.md")
    line = next(ln for ln in text.splitlines() if OK.BRANCH_RE.search(ln))
    date = OK.BRANCH_RE.search(line).group(2)
    prefix, digits, _ = _branch_rule(text.replace(line, line.replace(f"`{date}`", f"`{date[2:]}`", 1), 1))
    assert not PS.BRANCH.pattern.startswith("^%s/(\\d{%d}-" % (prefix, digits))
    _, _, ex = _branch_rule(text)
    _, _, ex = _branch_rule(text.replace(f"`{ex}`", "`ai/%s`" % ex.split("/", 1)[1], 1))
    assert not PS.BRANCH.match(ex)


# ── 8 推奨の語（ask_shape の _REC_WORD ↔ check.mjs の recommend ↔ guard-rules の SKILL.md）──────────

def _skill_rec_words(text):
    words = OK.推奨の語の並び(text)
    assert words, "guard-rules の見張りの表の ask_shape の行に推奨の語の並びが無いか形が変わった"
    return words


def _alts(pattern):
    return {w.lower() for w in pattern.split("|")}


@need_node
def test_推奨の語は_3_か所で同じ():
    tool = _alts(AS._REC_WORD.pattern)
    assert AS._REC_WORD.flags & re.I, "選択肢の画面の見張りは大小を問わない"
    assert _alts(_qa_rules()["recommend"]) == tool, "確認ページの検査の推奨の語が選択肢の画面の見張りと違う"
    assert _skill_rec_words(_read(GUARD_SKILL)) == tool, "guard-rules の推奨の語の並びが見張りと違う"


def test_推奨の語を_1_つ抜くと赤():
    """注入の試験: 読んだ並びの 2 つ目を抜く（語を写さない）。"""
    text = _read(GUARD_SKILL)
    row = next(ln for ln in text.splitlines() if "推奨の語（" in ln and ln.startswith("| "))
    words = re.search(r"推奨の語（([^。）]+)", row).group(1).split("・")
    bad = text.replace("・".join(words), "・".join(words[:1] + words[2:]), 1)
    assert _skill_rec_words(bad) != _alts(AS._REC_WORD.pattern)
