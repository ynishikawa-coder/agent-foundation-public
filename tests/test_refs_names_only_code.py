"""土台の md でない file（コード・試験・schema・設定）も土台の節を番号だけで指さない（refs.py を当てる）。

意図: 土台が節を足す・並べ替えても、指しが黙って別の節にならない（名で指す）。
課題: md は試験が照らしていたが、コードの注釈・出力の文・schema の説明・試験の頭の文は番号だけ（細目 §<番号>）のまま 120 余り残り、
新しく書く物も番号で入れられた。
原因: 照らす試験が md だけを読み、同じ指しを持つほかの file を数えていなかった（照らす範囲を file の形で切っていた）。
番号の形そのものを試す見本は、行に「番号の見本」と書いた時だけ外す（照らしの試験の材料・核.md の本文の引き）。
"""
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "core" / "scripts" / "refs.py"
_spec = importlib.util.spec_from_file_location("af_refs_names_only_code", TOOL)
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)
MARK = "番号の見本"
NUMBER_ONLY = "番号だけで指している"


def _code_files():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.splitlines()
            if not p.endswith(".md") and not p.startswith("CHANGELOG") and (ROOT / p).is_file()]


def number_only(c, text):
    """番号だけの指しの (行, 文)。「番号の見本」と書いた行は外す。"""
    lines = text.split("\n")
    return [(n, m) for n, m in R.check_all(c, text, numbers_ok=False)[0]
            if NUMBER_ONLY in m and MARK not in lines[n - 1]]


def test_md_でない_file_も土台の節を番号だけで指さない():
    c = R.contract(ROOT)
    bad = []
    for p in _code_files():
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "§" not in text:
            continue
        bad += [f"{p.relative_to(ROOT)}:{n} {m}" for n, m in number_only(c, text)]
    assert not bad, "\n".join(bad)


def test_注入_コードの注釈と出力の文に番号だけの指しを入れると赤():
    """注入: コードの注釈・文字列・schema の説明に番号だけの指しを置く → 拾う。名で指せば通る。印の行だけ外す。"""
    c = R.contract(ROOT)
    for planted in ('# 中身は細目 §3 が正本\n', 'print("核 §4 に従う")\n', '{"description": "CONTRIBUTING.md §8 を見る"}\n'):  # 番号の見本
        assert number_only(c, planted), planted
    assert number_only(c, '# 中身は細目「直すは根治」が正本\n') == []
    assert number_only(c, 'x = "細目 §3"  # 番号の見本\n') == []
    assert number_only(c, 'x = "細目 §3"\ny = 1  # 番号の見本\n')            # 印は同じ行だけ（隣の行を外さない）


def test_試験の範囲は_md_でない物を含む():
    """注入: 照らす範囲を md だけに戻すと、ここで数えるコード・schema・試験の file が 0 になる。"""
    files = {p.suffix for p in _code_files()}
    assert {".py", ".json"} <= files
