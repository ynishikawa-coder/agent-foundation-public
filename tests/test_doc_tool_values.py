"""決まりの文書と、それを照らす道具の値が 1 つに揃っているかを見る（qa-html の長さの上限・なぜ聞くかの 5 文）。

写しを無くせる所は道具が文書を直に読む（なぜ聞くかの 5 文）。文書と道具の両方に値が要る所は、文書から値を読んで
道具の値と同じかを見る（片方だけ変えると赤）。各組に、値をわざとずらすと拒む注入の試験を置く。
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
QA_DIR = ROOT / "plugins/docs-kit/skills/qa-html"
QA_SKILL = QA_DIR / "SKILL.md"
QA_CHECK = QA_DIR / "check.mjs"
need_node = pytest.mark.skipif(shutil.which("node") is None, reason="node が無い所では qa-html の検査（check.mjs）を回せない")


def _node(js):
    r = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _qa_rules():
    return _node('import { RULES } from "%s"; console.log(JSON.stringify(RULES));' % QA_CHECK.as_posix())


def _read(p):
    return Path(p).read_text(encoding="utf-8")


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
    body = text.split("## 長さの上限", 1)[1].split("\n## ", 1)[0]
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
    """注入の試験: 表の 40 字を 41 字にすると、読んだ上限が変わる（検査の値と合わなくなり上の試験が赤）。"""
    text = _read(QA_SKILL)
    bad = text.replace("| 問い（legend） | 1 行・40 字 |", "| 問い（legend） | 1 行・41 字 |")
    assert bad != text and _skill_limits(bad)["question_chars"] != _skill_limits(text)["question_chars"]


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
