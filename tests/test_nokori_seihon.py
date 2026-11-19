"""PR 本文の「残り」の欄の書き方の正本は細目 §3 の 1 つ。型（.github/pull_request_template.md）は見本の 1 行と細目 §3 を指すだけ。

注入: 型か細目に古い形（行の題と行き先を写す・書き方の説明を型に写す）を入れると拒む。
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / ".github" / "pull_request_template.md"
SAIMOKU = ROOT / "plugins" / "core" / "細目.md"
HEAD = "## 残り（原因の台帳の行）"
FORM = re.compile(r"`(- 台帳の行 <[^`>]+>)` だけ")
COPY = re.compile(r"題と行き先(だけ)?を写す|題・行き先・直す窓は")


def problems(template: str, saimoku: str) -> list[str]:
    bad = []
    m = FORM.search(saimoku.split("## 4.", 1)[0].split("## 3.", 1)[-1])
    if not m:
        return ["細目 §3 に残りの欄の形 `- 台帳の行 <…>` だけ が無い"]
    if COPY.search(saimoku):
        bad.append("細目に題と行き先を写す古い形が残る")
    if HEAD not in template:
        return bad + [f"型に欄 {HEAD} が無い"]
    sec = template.split(HEAD, 1)[1].split("\n## ", 1)[0].split("\n<!--\n", 1)[0]
    lines = [ln for ln in sec.splitlines() if ln.strip() and not ln.startswith("<!--")]
    if lines != [m.group(1)]:
        bad.append(f"型の見本が細目 §3 の形と違う: {lines} != {[m.group(1)]}")
    if "細目 §3" not in sec:
        bad.append("型の欄が細目 §3 を指していない")
    if COPY.search(sec) or "末尾 12 字>` だけ" in sec:
        bad.append("型に書き方の説明の写しが残る")
    return bad


def test_今の型と細目は1つの形で揃う():
    assert problems(TEMPLATE.read_text(encoding="utf-8"), SAIMOKU.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("where,old,new", [
    ("saimoku", "`- 台帳の行 <id 末尾 12 字>` だけ（正本は台帳で写さない）", "行の題と行き先を写すだけ（正本は台帳）"),
    ("saimoku", "`- 台帳の行 <id 末尾 12 字>` だけ", "`- 台帳の行 <id>・題・行き先: 直す窓 <URL>` だけ"),
    ("template", "- 台帳の行 <id 末尾 12 字>\n", "- 台帳の行 <行の id の末尾 12 字>\n"),
    ("template", "- 台帳の行 <id 末尾 12 字>\n", "- <行の題> — 行き先: 直す窓 <URL>\n"),
    ("template", "（ここに書き方を写さない）", "（題・行き先・直す窓は台帳の行が正本＝ここに写さない）"),
    ("template", "書き方の正本は 細目 §3", "書き方は"),
])
def test_古い形と写しを入れると拒む(where, old, new):
    t, s = TEMPLATE.read_text(encoding="utf-8"), SAIMOKU.read_text(encoding="utf-8")
    if where == "saimoku":
        assert old in s
        s = s.replace(old, new)
    else:
        assert old in t
        t = t.replace(old, new)
    assert problems(t, s), (where, new)
