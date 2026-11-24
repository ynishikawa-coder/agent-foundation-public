"""問いのデータ（JSON）の問いごとに、聞く前に引いた記録の所と版（"引いた物"）が無ければ検査が赤にする。

意図: 確認ページと送る文面の問いが、オーナーが 1 問ずつ見直さなくても「聞く前に引いた」問いだけになる（細目 §4）。
課題: 値の表に prior_check_cmd が無い repo では、引かずに作った問いの JSON が検査を黙って通り、答え済み・資料で決まる事が
問いに混ざっていた。
原因: 引いたかどうかが問いのデータに載らず、検査は値の表の命令が有る時しか前の答えを見ない形だった。
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECK = ROOT / "plugins" / "docs-kit" / "skills" / "qa-html" / "check.mjs"
GOOD = ROOT / "tests" / "docs_kit" / "good.json"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node が無い（qa-html の検査は node で動く）")
HOW = '聞く前に決定の記録と問いの表を引き、引いた記録の所と版を "引いた物": [{"所": …, "版": …}] で持たせる（細目 §4）'


def _red(tmp_path, mutate):
    """good.json の 1 問目を mutate で崩し、値の表の無い所で検査して赤の行を返す。"""
    data = json.loads(GOOD.read_text(encoding="utf-8"))
    q = data["questions"][0]
    mutate(q)
    page = tmp_path / "q.json"
    page.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    res = subprocess.run([NODE, str(CHECK), str(page), "--json"], capture_output=True, text=True, cwd=tmp_path)
    assert res.returncode in (0, 1), res.stderr
    out = json.loads(res.stdout)
    return q["key"], out["red"]


def test_引いた物を持つ問いのデータは緑(tmp_path):
    _, red = _red(tmp_path, lambda q: None)
    assert red == []


@pytest.mark.parametrize("mutate, why", [
    (lambda q: q.pop("引いた物"), "無い"),
    (lambda q: q.update({"引いた物": []}), "空"),
    (lambda q: q.update({"引いた物": "決定の記録"}), "配列でない"),
])
def test_引いた物が無い_空_配列でないと_値の表の命令が無くても赤(tmp_path, mutate, why):
    key, red = _red(tmp_path, mutate)
    assert red == [f'問い {key}: 引いた物（"引いた物"）が{why}: {HOW}']


@pytest.mark.parametrize("entry, want", [
    ("決定の記録", "が {\"所\", \"版\"} の形でない"),
    ({"所": "決定の記録 3 行目"}, "の「版」が無い・空（文字で書く）"),
    ({"所": " ", "版": "2026-11-13"}, "の「所」が無い・空（文字で書く）"),
    ({"所": "決定の記録 3 行目", "版": "2026-11-13", "答え": "済"}, "に知らない鍵「答え」（\"所\" と \"版\" だけ）"),
])
def test_引いた物の形が崩れていれば赤(tmp_path, entry, want):
    key, red = _red(tmp_path, lambda q: q.update({"引いた物": [entry]}))
    assert red == [f"問い {key}: 引いた物の 1 つ目{want}"]
