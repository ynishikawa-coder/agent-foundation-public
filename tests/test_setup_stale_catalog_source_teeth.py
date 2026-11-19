"""tests/test_setup_stale_catalog_source.py の字の照らしと動きの照らしが、片方ずつ壊しても別々に赤になるか（注入の試験）。

前の形: 塊を取り出す decide_part が先に「json.dumps が無いか」（字の照らし）を当て、動きの試験もどれもそこを通った。
文書を戻すと全部の試験が同じ字の照らしで止まり、動きの照らし（fork を外すか）が効いているかは結果から読めなかった。
字だけが壊れた（無害な json.dumps が入った）時も、動きの試験が全部赤になって、どちらが壊れたか分からなかった。
今の形: 字の照らしは別の file（test_setup_stale_catalog_source_text.py）の試験 1 本に分け、動きの試験は字を見ない。
ここでは小箱に試験の file と壊した文書を置いて回し、どの試験が赤になったかで照らす。
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEST = "tests/test_setup_stale_catalog_source.py"
TEXT = "tests/test_setup_stale_catalog_source_text.py"
DOC = "docs/核の届け方.md"
NOW = '(s.get("repo") or s.get("url"))!=a[2]'
REMOVE = "2>/dev/null && claude plugin marketplace remove agent-foundation >/dev/null 2>&1 || true"

BROKEN = {
    # 字だけ壊す: 動きは今のまま、外すかの決め方に使わない json.dumps を足す
    "字だけ": (lambda t: t.replace(NOW, f'{NOW} and json.dumps(s) is not None'), {"字"}),
    # 動きだけ壊す: json.dumps を使わずに、名の一部が合えば今の目録と見なす
    "動きだけ": (lambda t: t.replace(NOW, 'a[2] not in str(s)'), {"動き"}),
    # 文書を丸ごと前の形へ戻す: 字も動きも赤
    "丸ごと前の形": (lambda t: t.replace(NOW, 'a[2] not in json.dumps(s)'), {"字", "動き"}),
    # 外す行の書き方だけ変える（動きは同じ）: どの照らしも赤にしない（試験の替え方が行の字に頼らない）
    "外す行の書き方だけ": (lambda t: t.replace(REMOVE, REMOVE.replace(
        "claude plugin marketplace remove agent-foundation", "{ claude plugin marketplace remove agent-foundation; }")), set()),
    # python の書き損じ（SyntaxError は Traceback の見出しを出さない）: 動きが赤
    "python の書き損じ": (lambda t: t.replace(NOW, NOW + ")"), {"動き"}),
}


def run_box(tmp_path, doc_text):
    for rel in [TEST, TEXT]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, tmp_path / rel)
    (tmp_path / DOC).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / DOC).write_text(doc_text, encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider", "-c", "/dev/null",
                        f"--rootdir={tmp_path}", f"--confcutdir={tmp_path}", str(tmp_path / TEST), str(tmp_path / TEXT)],
                       capture_output=True, text=True, cwd=tmp_path, timeout=300)
    out = r.stdout + r.stderr
    red = set()
    ran = 0
    for kind, path in re.findall(r"^(PASSED|FAILED|ERROR) (\S+?)::", out, re.M):
        ran += 1
        if kind != "PASSED":
            red.add("字" if path.endswith(Path(TEXT).name) else "動き")
    return ran, red, out


def test_合格_今の文書では字も動きも緑(tmp_path):
    ran, red, out = run_box(tmp_path, (ROOT / DOC).read_text(encoding="utf-8"))
    assert ran >= 5 and red == set(), out


@pytest.mark.parametrize("name", sorted(BROKEN))
def test_注入_片方ずつ壊すとその照らしだけが赤(tmp_path, name):
    broken, want = BROKEN[name]
    text = (ROOT / DOC).read_text(encoding="utf-8")
    assert NOW in text and REMOVE in text, "文書の外す行の形が変わった（壊し方を合わせる）"
    assert broken(text) != text, f"{name}: 壊し方が文書に当たらない"
    ran, red, out = run_box(tmp_path, broken(text))
    assert ran >= 5 and red == want, f"{name}: 赤になった照らし {red}（求める {want}）\n{out}"
