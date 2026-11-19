"""review-pr の跡の残らない手順の点（跡の残らない手順）が、オーナーの決定 2026-11-19 で「機械で照らさず、レビューで見る」とした手順を全部名指すか。

1 つでも消すと、その手順を照らす所がどこにも無くなる（台帳の行は「直さない＝レビューの点で見る」になっている）。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "plugins" / "checker" / "skills" / "review-pr" / "SKILL.md"

# 台帳の行（直さない＝レビューの点で見る）ごとの、跡の残らない手順の点 が名指す手順の言葉
STEPS = [
    "原因の 1 文だけを渡したか",
    "終わりの報告の前に台帳を引いた結果を付けたか",
    "オーナーの同意を取り、注入の試験を置いたか",
    "原因の段から直したか",
    "受けた申告（引き継ぎ・完了報告）を正本で確かめたか",
    "「ほんまにできる表」が埋まる前に実装へ進んでいないか",
    "オーナーが読めない番号・id を中の言葉として出していないか",
]


def _row():
    rows = [l for l in SKILL.read_text(encoding="utf-8").splitlines() if (l.startswith("| ") and l.split("|")[1].strip().split(" ", 1)[-1] =="跡の残らない手順")]
    assert len(rows) == 1, "見る点の表に跡の残らない手順の点 の行がちょうど 1 つ無い"
    return rows[0]


def test_点が跡の残らない手順を全部名指す():
    row = _row()
    missing = [s for s in STEPS if s not in row]
    assert not missing, missing


def test_点は判定の形にも在り_verdict_form_が読む():
    spec = importlib.util.spec_from_file_location("vf", ROOT / "plugins" / "checker" / "scripts" / "verdict_form.py")
    vf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vf)
    no = {v: k for k, v in vf.load_points().items()}.get("跡の残らない手順")
    assert no, "verdict_form が跡の残らない手順を読まない"
    assert "- %d 跡の残らない手順: pass/fail/N/A" % no in SKILL.read_text(encoding="utf-8")
