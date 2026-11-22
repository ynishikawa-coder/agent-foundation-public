"""qa-html の宛先・問いの形・長さの上限の表（正本は check.mjs の DEST_TABLE・RULES.kinds・LIMIT_ROWS）。

SKILL.md の表は `node check.mjs --table <dests|kinds|limits>` の出力を `<!-- check.mjs --table 名 … -->` の囲みの間に
そのまま置き、ここで一字違わず照らす（前は文書と道具に別々に書き、長さの上限だけを正規表現で読み合わせていた）。
各組に、写しを 1 字ずらす・鍵を足し引きすると拒む注入の試験を置く。
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


def _read(path):
    return path.read_text(encoding="utf-8")


def _node(js):
    r = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


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
