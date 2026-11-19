"""字の形の試験では見分けられない決まりの文の崩れは、名指しでレビューの点（人の関所）が読む。

試験が見分けない崩れ（PR #59 のレビューと原因の台帳の行）:
- 決まりの文を語の差し替えで弱める（語だけを照らす試験は緑のまま。tests/test_rule_holes.py は文を消す注入だけを見る）
- 核と細目の外の決まりの文（skill・CONTRIBUTING・PR の型）を消す・弱める（tests/test_rule_holes.py の照らす範囲の外。
  広げると 9 割を超える文が「判断」の訳で表に載り、表が文の写しになるだけで CI が延びる＝人の関所で読む）
- 片付かない物を、後へ回す言葉の表に無い言い回しで原因の台帳の外へ向ける（tests/test_deferral_ledger.py は表の言葉だけを見る）
- 決まった言い回しで原因の台帳を指した後の句で打ち消す（同じ試験は字の形で見分けない）
どれも review-pr の点 12 が red にする。点の文を消すと、ここが赤（人の関所が黙って外れない）。
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REVIEW = ROOT / "plugins" / "checker" / "skills" / "review-pr" / "SKILL.md"


def _点(n):
    rows = [ln for ln in REVIEW.read_text(encoding="utf-8").splitlines() if re.match(rf"^\| {n} ", ln)]
    assert len(rows) == 1, f"review-pr の点 {n} の行が無い"
    return rows[0]


@pytest.mark.parametrize("clause", [
    "決まりの文（核・振る舞いの既定・細目・skill・CONTRIBUTING・PR の型）を消した・語の差し替えで弱めたのに、PR 本文に理由",
    "核と細目の外の文は消しても赤にならない",
    "核の原則を弱めたのにオーナーの同意の記録が無い",
    "試験の後へ回す言葉の表に無い言い回しで足した",
    "決まった言い回しで台帳を指した後の句で打ち消す",
])
def test_試験が見分けない決まりの文の崩れは_review_pr_の点_12_が_red_にする(clause):
    assert clause in _点(12).split("|")[3], f"点 12 の red になる時に無い: {clause}"


def test_点_12_は依頼に無くても止めてよい点に入る():
    text = REVIEW.read_text(encoding="utf-8")
    m = re.search(r"ただし点 ([\d・]+) は依頼に無くても `\[止める｜…\]` にしてよい", text)
    assert m and "12" in m.group(1).split("・")


@pytest.mark.parametrize("rel", ["tests/test_rule_holes.py", "tests/test_deferral_ledger.py"])
def test_試験の残る穴は_点_12_を名指す(rel):
    """試験の側の残る穴の書き置きが、読む人の関所を指す（指す先の点を消すと上の試験が赤）。"""
    assert "点 12" in (ROOT / rel).read_text(encoding="utf-8")
