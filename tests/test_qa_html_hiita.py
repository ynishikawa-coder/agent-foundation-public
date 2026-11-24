"""問いのデータ（JSON）の問いごとに、聞く前に引いた記録の所と版（"引いた物"）が無ければ検査が赤にする。

意図: 確認ページと送る文面の問いが、オーナーが 1 問ずつ見直さなくても「聞く前に引いた」問いだけになる（細目 §4）。
課題: 値の表に prior_check_cmd が無い repo では、引かずに作った問いの JSON が検査を黙って通り、答え済み・資料で決まる事が
問いに混ざっていた。
原因: 引いたかどうかが問いのデータに載らず、検査は値の表の命令が有る時しか前の答えを見ない形だった。
"""
import json
import shutil
import subprocess
import sys
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
    ({"所": "決定の記録 3 行目", "版": "2026-11-13", "メモ": "済"}, "に知らない鍵「メモ」（\"所\"・\"版\" と、答えを見つけた時の \"鍵\"・\"答え\" だけ）"),
    ({"所": "決定の記録 3 行目", "版": "2026-11-13", "答え": "月末"}, "に「答え」があって「鍵」（答えた問いの鍵）が無い"),
])
def test_引いた物の形が崩れていれば赤(tmp_path, entry, want):
    key, red = _red(tmp_path, lambda q: q.update({"引いた物": [entry]}))
    assert red == [f"問い {key}: 引いた物の 1 つ目{want}"]


def test_引いた物にこの問いの鍵の答えが在れば答え済みとして赤(tmp_path):
    """細目 §4 ①: 答え済みの問いは聞かない。引いた記録に同じ問いの鍵の答えが在るのに問いを残すと、検査が拒む。"""
    found = {"所": "問いの表 12 行目", "版": "2026-11-20", "鍵": None, "答え": "月末で締める"}
    key, red = _red(tmp_path, lambda q: q.update({"引いた物": [dict(found, 鍵=q["key"])]}))
    assert red == [f"問い {key}: 引いた物の 1 つ目（問いの表 12 行目）で答え済み（月末で締める）＝問いから外し、その答えで進める（細目 §4）"]


@pytest.mark.parametrize("found", [
    {"所": "問いの表 12 行目", "版": "2026-11-20", "鍵": "other_key", "答え": "月末で締める"},
    {"所": "問いの表 12 行目", "版": "2026-11-20", "鍵": "__SAME__", "答え": " "},
])
def test_ほかの問いの答えか_答えが空なら答え済みにしない(tmp_path, found):
    def mutate(q):
        q["引いた物"] = [dict(found, 鍵=q["key"] if found["鍵"] == "__SAME__" else found["鍵"])]
    _, red = _red(tmp_path, mutate)
    assert red == []


# ── HTML のページ（send・copy・artifact）: 引いた物はページに載せず、隣の <名>.prior.json に問いの鍵ごとに持つ
def _html_red(tmp_path, side, dest="send", values=None):
    """型を埋めた HTML のページの隣に side（None なら置かない）を書いて検査し、赤の行を返す。"""
    from test_docs_kit import filled_template, write_values
    page = tmp_path / "確認.html"
    page.write_text(filled_template(dest), encoding="utf-8")
    if side is not None:
        (tmp_path / "確認.prior.json").write_text(json.dumps(side, ensure_ascii=False), encoding="utf-8")
    if values is not None:
        write_values(tmp_path, values)
    res = subprocess.run([NODE, str(CHECK), str(page), "--json"], capture_output=True, text=True, cwd=tmp_path)
    assert res.returncode in (0, 1), res.stderr
    return json.loads(res.stdout)["red"]


SIDE = {k: [{"所": "決定の記録 3 行目", "版": "2026-11-13"}] for k in ("q1", "q2", "q3", "q4")}


def test_HTML_の隣の引いた物にこの問いの答えが在れば答え済みとして赤(tmp_path):
    side = {**SIDE, "q2": [{"所": "問いの表 12 行目", "版": "2026-11-20", "鍵": "q2", "答え": "月末で締める"}]}
    assert _html_red(tmp_path, {"引いた物": side}) == [
        "問い q2: 引いた物の 1 つ目（問いの表 12 行目）で答え済み（月末で締める）＝問いから外し、その答えで進める（細目 §4）"]


@pytest.mark.parametrize("hiita, want", [
    (["決定の記録"], '"引いた物" は {"問いの鍵": [{"所", "版"}]} の形で書く'),
    ({**SIDE, "q1": [{"所": "決定の記録 3 行目"}]}, "問い q1: 引いた物の 1 つ目の「版」が無い・空（文字で書く）"),
])
def test_HTML_の隣の引いた物の形が崩れていれば赤(tmp_path, hiita, want):
    red = _html_red(tmp_path, {"引いた物": hiita})
    assert len(red) == 1 and want in red[0], red


def test_問いの_JSON_の引いた物を隣の_file_に書くと赤(tmp_path):
    """置き場は形ごとに 1 つ。JSON の問いは問いの中に持ち、隣の file に別の写しを置かない。"""
    page = tmp_path / "q.json"
    page.write_text(GOOD.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "q.prior.json").write_text(json.dumps({"引いた物": SIDE}, ensure_ascii=False), encoding="utf-8")
    res = subprocess.run([NODE, str(CHECK), str(page), "--json"], capture_output=True, text=True, cwd=tmp_path)
    red = json.loads(res.stdout)["red"]
    assert red == [f'問いの JSON の引いた物は JSON の問いの "引いた物" に書く（{tmp_path / "q.prior.json"} に書かない・置き場は 1 つ）'], red


def test_run_prior_の命令が_HTML_の引いた物を返さなければ問いごとに赤(tmp_path):
    from test_docs_kit import filled_template, write_values
    page = tmp_path / "確認.html"
    page.write_text(filled_template("send"), encoding="utf-8")
    tool = tmp_path / "old_tool.py"  # 引いた物を返さない古い命令
    tool.write_text("import json, sys\nd = json.load(sys.stdin)\n"
                    "print(json.dumps({'checked': {q['key']: 'x' for q in d['questions']}}))\n", encoding="utf-8")
    write_values(tmp_path, {"prior_check_cmd": f"{sys.executable} {tool}"})
    res = subprocess.run([NODE, str(CHECK), str(page), "--json", "--run-prior"], capture_output=True, text=True, cwd=tmp_path)
    red = json.loads(res.stdout)["red"]
    assert [r.split(":")[0] for r in red] == [f"問い {k}" for k in SIDE] and all('引いた物（"引いた物"）が無い' in r for r in red), red
